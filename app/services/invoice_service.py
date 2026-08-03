"""Service « factures » : dépôt, historique, consultation et statuts (phase 3).

Orchestre la couche de stockage (:mod:`app.storage`) et les repositories pour
le cycle de vie d'un document : dépôt (avec validation), liste/filtres,
consultation (métadonnées + fichier source) et transitions de statut.
"""

from __future__ import annotations

import os
from datetime import date, datetime
from unicodedata import normalize

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import (
    ConcurrentModificationError,
    DocumentNotFoundError,
    DuplicateInvoiceError,
    InvalidInvoiceNumberError,
    InvalidStatusTransitionError,
    NotFoundError,
    SupplierNotFoundError,
)
from app.models.enums import InvoiceStatus
from app.models.invoice import Invoice
from app.repositories import InvoiceRepository, SupplierRepository
from app.services.document_service import DocumentValidator
from app.storage.base import Storage

# Transitions de statut valides (graphe du cycle de vie d'une facture).
#
#   Déposée → En cours d'analyse → À vérifier → Validée → Vendor Bill créée
#                                              ↘ Rejetée
#
# « Erreur système » est atteignable depuis toute étape ; la reprise se fait
# en ré-engageant la facture (retour « Déposée »).
VALID_TRANSITIONS: dict[InvoiceStatus, set[InvoiceStatus]] = {
    InvoiceStatus.SUBMITTED: {
        InvoiceStatus.ANALYZING,
        InvoiceStatus.SYSTEM_ERROR,
    },
    InvoiceStatus.ANALYZING: {
        InvoiceStatus.TO_REVIEW,
        InvoiceStatus.SYSTEM_ERROR,
    },
    InvoiceStatus.TO_REVIEW: {
        InvoiceStatus.VALIDATED,
        InvoiceStatus.REJECTED,
        InvoiceStatus.SYSTEM_ERROR,
    },
    InvoiceStatus.VALIDATED: {
        InvoiceStatus.VENDOR_BILL_CREATED,
        InvoiceStatus.SYSTEM_ERROR,
    },
    InvoiceStatus.REJECTED: {InvoiceStatus.SYSTEM_ERROR},
    InvoiceStatus.VENDOR_BILL_CREATED: {InvoiceStatus.SYSTEM_ERROR},
    InvoiceStatus.SYSTEM_ERROR: {InvoiceStatus.SUBMITTED},
}


class InvoiceService:
    """Opérations du cycle de vie d'une facture."""

    def __init__(self, db: Session, storage: Storage) -> None:
        self.db = db
        self.storage = storage
        self.invoices = InvoiceRepository(db)
        self.suppliers = SupplierRepository(db)
        self.validator = DocumentValidator()

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        """Ne garde que la base d'un nom de fichier (assainissement du chemin)."""
        return os.path.basename(normalize("NFKC", filename)).strip()

    @staticmethod
    def _sanitize_invoice_number(value: str) -> str:
        """Normalise un numéro de facture : sans espace superflu, taille bornée."""
        value = normalize("NFKC", value).strip()
        if not value:
            raise InvalidInvoiceNumberError("Le numéro de facture est vide.")
        if len(value) > 100:
            raise InvalidInvoiceNumberError(
                "Le numéro de facture est trop long (100 caractères max)."
            )
        return value

    # --- Dépôt --------------------------------------------------------------

    def deposit(
        self,
        *,
        filename: str,
        content: bytes,
        invoice_number: str,
        supplier_id: int,
        issue_date: date | None = None,
    ) -> Invoice:
        """Dépose une nouvelle facture (statut initial « Déposée »).

        1. valide le document (format + lisibilité) ;
        2. vérifie le fournisseur et l'absence de doublon ;
        3. stocke le fichier et crée la facture liée.

        Lève :class:`InvalidDocumentError`, :class:`SupplierNotFoundError` ou
        :class:`DuplicateInvoiceError` en cas de rejet.
        """
        suffix, mime_type = self.validator.validate(filename, content)
        filename = self._sanitize_filename(filename)
        invoice_number = self._sanitize_invoice_number(invoice_number)

        supplier = self.suppliers.get(supplier_id)
        if supplier is None:
            raise SupplierNotFoundError("Fournisseur introuvable.")

        if self.invoices.exists_duplicate(supplier_id, invoice_number):
            raise DuplicateInvoiceError(
                "Une facture portant le même numéro existe déjà pour ce "
                "fournisseur."
            )

        file_path = self.storage.save(content, suffix=suffix)
        try:
            return self.invoices.create(
                invoice_number=invoice_number,
                supplier_id=supplier_id,
                status=InvoiceStatus.SUBMITTED,
                issue_date=issue_date,
                file_path=file_path,
                original_filename=filename,
                content_type=mime_type,
                file_size=len(content),
            )
        except IntegrityError as exc:
            # Course sur le couple (fournisseur, numéro) : une autre requête a
            # inséré la même facture entre le SELECT de contrôle et l'INSERT.
            # La contrainte d'unicité lève → on traduit en doublon propre.
            self.db.rollback()
            raise DuplicateInvoiceError(
                "Une facture portant le même numéro existe déjà pour ce "
                "fournisseur."
            ) from exc
        except Exception:
            self.storage.delete(file_path)
            raise

    # --- Historique & consultation -------------------------------------------

    def list_invoices(
        self,
        *,
        status: InvoiceStatus | None = None,
        supplier_id: int | None = None,
        issue_date_from: date | None = None,
        issue_date_to: date | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        sort: str = "created_at_desc",
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Invoice], int]:
        """Retourne ``(factures, total)`` selon les filtres fournis."""
        invoices = self.invoices.filter(
            status=status,
            supplier_id=supplier_id,
            issue_date_from=issue_date_from,
            issue_date_to=issue_date_to,
            created_from=created_from,
            created_to=created_to,
            sort=sort,
            limit=limit,
            offset=offset,
        )
        total = self.invoices.count(
            status=status,
            supplier_id=supplier_id,
            issue_date_from=issue_date_from,
            issue_date_to=issue_date_to,
            created_from=created_from,
            created_to=created_to,
        )
        return invoices, total

    def get_invoice(self, invoice_id: int) -> Invoice:
        """Retourne une facture par identifiant, ou lève 404."""
        invoice = self.invoices.get(invoice_id)
        if invoice is None:
            raise NotFoundError("Facture introuvable.")
        return invoice

    def get_source_file(self, invoice: Invoice) -> bytes:
        """Retourne le contenu binaire du fichier source d'une facture.

        Lève :class:`DocumentNotFoundError` si la facture n'a pas de fichier
        ou si le fichier stocké est introuvable.
        """
        if invoice.file_path is None:
            raise DocumentNotFoundError(
                "Aucun fichier n'est associé à cette facture."
            )
        if not self.storage.exists(invoice.file_path):
            raise DocumentNotFoundError(
                "Le fichier source de la facture est introuvable."
            )
        return self.storage.open(invoice.file_path)

    # --- Statuts --------------------------------------------------------------

    def transition_status(
        self, invoice: Invoice, new_status: InvoiceStatus, *, reason: str | None = None
    ) -> Invoice:
        """Fait passer une facture vers ``new_status`` si la transition est
        valide. Lève :class:`InvalidStatusTransitionError` sinon.

        Le motif optionnel est conservé dans ``rejection_reason`` (rejet) ou
        ``error_message`` (erreur système).

        La mise à jour est effectuée en **optimistic locking** (compare-and-swap
        sur ``invoice.version``) : si une autre opération a modifié la facture
        entre la lecture et l'écriture, :class:`ConcurrentModificationError`
        est levée au lieu d'écraser silencieusement l'état concurrent.
        """
        allowed = VALID_TRANSITIONS.get(invoice.status, set())
        if new_status not in allowed:
            raise InvalidStatusTransitionError(
                f"Transition invalide : « {invoice.status.value} » → "
                f"« {new_status.value} »."
            )

        updates: dict = {"status": new_status}
        if new_status is InvoiceStatus.REJECTED:
            updates["rejection_reason"] = reason
        elif new_status is InvoiceStatus.SYSTEM_ERROR:
            updates["error_message"] = reason

        expected_version = invoice.version
        applied = self.invoices.update_cas(
            invoice.id, expected_version, **updates
        )
        if not applied:
            raise ConcurrentModificationError(
                "La facture a été modifiée entre-temps ; merci de recharger."
            )
        # Ré-aligne l'objet en session (l'UPDATE bulk ne l'expire pas) afin que
        # les attributs lus immédiatement après reflètent l'écriture.
        for key, value in updates.items():
            setattr(invoice, key, value)
        invoice.version = expected_version + 1
        return invoice
