"""Endpoints « documents » : dépôt, historique, consultation et statuts.

L'upload manuel (multipart/form-data) accepte les formats PDF, JPG, JPEG et
PNG, valide le format et la lisibilité du document, puis stocke le fichier et
crée la facture liée au fournisseur fourni.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile

from app.api.deps import (
    get_anomaly_repository,
    get_audit_log_repository,
    get_invoice_service,
    get_matching_service,
    get_ocr_service,
    get_validation_service,
    require_permissions,
)
from app.core.exceptions import DocumentNotFoundError
from app.core.permissions import Permission
from app.models.enums import InvoiceStatus
from app.models.user import User
from app.repositories import AnomalyRepository, AuditLogRepository
from app.schemas.invoice import InvoiceListResponse, InvoiceRead, InvoiceStatusUpdate
from app.schemas.matching import MatchingAnomalyRead, MatchingLineRead, MatchingRead
from app.schemas.ocr import OcrResultRead
from app.schemas.summary import DashboardSummary, PendingAnomaly
from app.schemas.validation import (
    AuditLogRead,
    InvoiceCorrection,
    InvoiceReject,
)
from app.services.invoice_service import InvoiceService
from app.services.matching_service import MatchingService
from app.services.ocr_service import OcrService
from app.services.validation_service import ValidationService

router = APIRouter()

InvoiceServiceDep = Annotated[InvoiceService, Depends(get_invoice_service)]
OcrServiceDep = Annotated[OcrService, Depends(get_ocr_service)]
MatchingServiceDep = Annotated[MatchingService, Depends(get_matching_service)]
ValidationServiceDep = Annotated[ValidationService, Depends(get_validation_service)]
AuditLogRepoDep = Annotated[AuditLogRepository, Depends(get_audit_log_repository)]
AnomalyRepoDep = Annotated[AnomalyRepository, Depends(get_anomaly_repository)]
InvoiceReadPerm = Annotated[
    object, Depends(require_permissions(Permission.INVOICE_READ))
]
InvoiceDepositPerm = Annotated[
    object, Depends(require_permissions(Permission.INVOICE_DEPOSIT))
]
InvoiceValidatePerm = Annotated[
    object, Depends(require_permissions(Permission.INVOICE_VALIDATE))
]


def _filename_header(filename: str) -> str:
    """En-tête Content-Disposition sûr (ASCII fallback + encodage RFC 5987)."""
    ascii_name = filename.encode("ascii", errors="replace").decode()
    encoded = quote(filename)
    if encoded == ascii_name:
        return f'attachment; filename="{ascii_name}"'
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded}"


@router.post(
    "",
    response_model=InvoiceRead,
    status_code=201,
    summary="Déposer une facture (upload manuel)",
)
def deposit_invoice(
    file: Annotated[UploadFile, File(description="Document : PDF, JPG, JPEG, PNG")],
    invoice_number: Annotated[str, Form(description="Numéro de la facture")],
    supplier_id: Annotated[int, Form(description="Identifiant du fournisseur")],
    issue_date: Annotated[
        date | None, Form(description="Date d'émission (AAAA-MM-JJ)")
    ] = None,
    service: InvoiceServiceDep = None,
    _: InvoiceDepositPerm = None,
) -> object:
    """Dépose une facture : validation du document, stockage et création."""
    return service.deposit(
        filename=file.filename or "document",
        content=file.file.read(),
        invoice_number=invoice_number,
        supplier_id=supplier_id,
        issue_date=issue_date,
    )


@router.get(
    "",
    response_model=InvoiceListResponse,
    summary="Historique des factures (tri et filtres)",
)
def list_invoices(
    status: InvoiceStatus | None = Query(default=None, description="Filtrer par statut"),
    supplier_id: int | None = Query(default=None, description="Filtrer par fournisseur"),
    issue_date_from: date | None = Query(default=None, description="Émise à partir de"),
    issue_date_to: date | None = Query(default=None, description="Émise jusqu'à"),
    created_from: datetime | None = Query(default=None, description="Déposée à partir de"),
    created_to: datetime | None = Query(default=None, description="Déposée jusqu'à"),
    sort: str = Query(default="created_at_desc", description="Mode de tri"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    service: InvoiceServiceDep = None,
    _: InvoiceReadPerm = None,
) -> InvoiceListResponse:
    """Liste paginée des factures, avec filtres combinables et tri."""
    items, total = service.list_invoices(
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
    return InvoiceListResponse(items=items, total=total)


@router.get(
    "/summary",
    response_model=DashboardSummary,
    summary="Synthèse du tableau de bord (comptes par statut, anomalies)",
)
def invoice_summary(
    service: InvoiceServiceDep = None,
    anomalies: AnomalyRepoDep = None,
    _: InvoiceReadPerm = None,
) -> DashboardSummary:
    """Retourne le nombre de factures par statut et les anomalies non résolues.

    Utilisé par le tableau de bord : comptage par statut via la pagination et
    liste des anomalies en attente (priorité aux plus anciennes).
    """
    by_status = {
        status.value: service.list_invoices(status=status, limit=1)[1]
        for status in InvoiceStatus
    }
    pending = [
        PendingAnomaly(
            id=anomaly.id,
            invoice_id=anomaly.invoice_id,
            invoice_number=anomaly.invoice.invoice_number,
            supplier_name=anomaly.invoice.supplier.name,
            category=anomaly.category,
            severity=anomaly.severity,
            message=anomaly.message,
            expected_value=anomaly.expected_value,
            actual_value=anomaly.actual_value,
            created_at=anomaly.created_at,
        )
        for anomaly in anomalies.list_unresolved(limit=100)
    ]
    return DashboardSummary(by_status=by_status, pending_anomalies=pending)


@router.get(
    "/{invoice_id}",
    response_model=InvoiceRead,
    summary="Consulter une facture (métadonnées)",
)
def get_invoice(
    invoice_id: int,
    service: InvoiceServiceDep = None,
    _: InvoiceReadPerm = None,
) -> object:
    """Retourne les métadonnées d'une facture."""
    return service.get_invoice(invoice_id)


@router.get(
    "/{invoice_id}/file",
    summary="Télécharger le fichier source d'une facture",
)
def get_invoice_file(
    invoice_id: int,
    service: InvoiceServiceDep = None,
    _: InvoiceReadPerm = None,
) -> Response:
    """Retourne le fichier original déposé (PDF ou image)."""
    invoice = service.get_invoice(invoice_id)
    content = service.get_source_file(invoice)
    if invoice.content_type is None:
        raise DocumentNotFoundError("Le type du fichier source est inconnu.")
    return Response(
        content=content,
        media_type=invoice.content_type,
        headers={
            "Content-Disposition": _filename_header(
                invoice.original_filename or f"facture-{invoice.id}"
            )
        },
    )


@router.post(
    "/{invoice_id}/process",
    response_model=OcrResultRead,
    summary="Lancer l'analyse OCR d'une facture",
)
def process_invoice(
    invoice_id: int,
    service: InvoiceServiceDep = None,
    ocr: OcrServiceDep = None,
    _: InvoiceDepositPerm = None,
) -> OcrResultRead:
    """Exécute le pipeline OCR (chargement, reconnaissance, structuration).

    La facture doit être « Déposée » ou « Erreur système ». En cas de succès
    elle passe « À vérifier » ; sinon « Erreur système » avec le message.
    """
    invoice = service.get_invoice(invoice_id)
    ocr.process(invoice)
    return OcrResultRead(
        invoice_id=invoice.id,
        status=invoice.status,
        ocr_confidence_score=invoice.ocr_confidence_score,
        error_message=invoice.error_message,
        extracted_data=invoice.extracted_data,
    )


@router.post(
    "/{invoice_id}/match",
    response_model=MatchingRead,
    summary="Rapprocher une facture à son bon de commande (matching)",
)
def match_invoice(
    invoice_id: int,
    service: InvoiceServiceDep = None,
    matching: MatchingServiceDep = None,
    _: InvoiceReadPerm = None,
) -> MatchingRead:
    """Exécute le rapprochement facture ↔ bon de commande (phase 6).

    Compare le fournisseur, rapproche les lignes (produit, quantité, prix),
    compare les montants et la TVA, puis calcule et persiste le score de
    matching global sur la facture. Les anomalies détectées sont enregistrées
    par catégorie (montant, TVA, quantité, produit absent, doublon...).
    """
    invoice = service.get_invoice(invoice_id)
    result = matching.match(invoice)

    extracted = (invoice.extracted_data or {}).get("general") or {}
    reference = (
        extracted.get("purchase_order_reference")
        if isinstance(extracted, dict)
        else None
    )
    return MatchingRead(
        invoice_id=result.invoice_id,
        purchase_order_reference=reference,
        supplier_match=result.supplier_match,
        duplicate_found=result.duplicate_found,
        score=result.score,
        lines=[
            MatchingLineRead(
                line_number=line.invoice_line.line_number,
                description=line.invoice_line.description,
                product_ref=line.invoice_line.product_ref,
                quantity=line.invoice_line.quantity,
                unit_price=line.invoice_line.unit_price,
                purchase_order_line_odoo_id=line.invoice_line.purchase_order_line_odoo_id,
                quantity_matched=line.quantity_matched,
                unit_price_matched=line.unit_price_matched,
                quantity_delta=line.quantity_delta,
                unit_price_delta=line.unit_price_delta,
            )
            for line in result.line_matches
        ],
        anomalies=[
            MatchingAnomalyRead(
                category=anomaly.category,
                severity=anomaly.severity,
                message=anomaly.message,
                expected_value=anomaly.expected_value,
                actual_value=anomaly.actual_value,
            )
            for anomaly in result.anomalies
        ],
    )


@router.post(
    "/{invoice_id}/status",
    response_model=InvoiceRead,
    summary="Changer le statut d'une facture (transitions validées)",
)
def update_invoice_status(
    invoice_id: int,
    payload: InvoiceStatusUpdate,
    service: InvoiceServiceDep = None,
    _: InvoiceValidatePerm = None,
) -> object:
    """Applique une transition de statut si elle est valide (409 sinon)."""
    invoice = service.get_invoice(invoice_id)
    return service.transition_status(invoice, payload.status, reason=payload.reason)


@router.post(
    "/{invoice_id}/validate",
    response_model=InvoiceRead,
    summary="Valider une facture",
)
def validate_invoice(
    invoice_id: int,
    service: InvoiceServiceDep = None,
    validation: ValidationServiceDep = None,
    user: User = Depends(require_permissions(Permission.INVOICE_VALIDATE)),
) -> object:
    """Valide une facture « À vérifier » (action tracée dans le journal d'audit)."""
    invoice = service.get_invoice(invoice_id)
    return validation.validate(invoice, user)


@router.post(
    "/{invoice_id}/reject",
    response_model=InvoiceRead,
    summary="Rejeter une facture (motif obligatoire)",
)
def reject_invoice(
    invoice_id: int,
    payload: InvoiceReject,
    service: InvoiceServiceDep = None,
    validation: ValidationServiceDep = None,
    user: User = Depends(require_permissions(Permission.INVOICE_VALIDATE)),
) -> object:
    """Rejette une facture avec un motif obligatoire (tracé dans l'audit)."""
    invoice = service.get_invoice(invoice_id)
    return validation.reject(invoice, user, payload.reason)


@router.put(
    "/{invoice_id}/correct",
    response_model=InvoiceRead,
    summary="Corriger manuellement les données extraites d'une facture",
)
def correct_invoice(
    invoice_id: int,
    payload: InvoiceCorrection,
    service: InvoiceServiceDep = None,
    validation: ValidationServiceDep = None,
    user: User = Depends(require_permissions(Permission.INVOICE_CORRECT)),
) -> object:
    """Corrige les champs et/ou les lignes d'une facture « À vérifier »."""
    invoice = service.get_invoice(invoice_id)
    return validation.correct(invoice, user, payload)


@router.post(
    "/{invoice_id}/vendor-bill",
    response_model=InvoiceRead,
    summary="Créer la Vendor Bill Odoo (account.move) d'une facture validée",
)
def create_vendor_bill(
    invoice_id: int,
    service: InvoiceServiceDep = None,
    validation: ValidationServiceDep = None,
    user: User = Depends(require_permissions(Permission.INVOICE_VALIDATE)),
) -> object:
    """Génère l'``account.move`` Odoo et lie le ``move_id`` à la facture."""
    invoice = service.get_invoice(invoice_id)
    return validation.create_vendor_bill(invoice, user)


@router.get(
    "/{invoice_id}/audit-logs",
    response_model=list[AuditLogRead],
    summary="Journal d'audit d'une facture",
)
def list_audit_logs(
    invoice_id: int,
    service: InvoiceServiceDep = None,
    audit_logs: AuditLogRepoDep = None,
    _: object = Depends(require_permissions(Permission.JOURNAL_READ)),
) -> list[AuditLogRead]:
    """Retourne l'historique des actions (qui, quand, quoi) sur une facture."""
    service.get_invoice(invoice_id)  # 404 si la facture n'existe pas
    return audit_logs.list_by_invoice(invoice_id)
