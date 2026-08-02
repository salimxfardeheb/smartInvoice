"""Enums métier utilisés par le schéma SmartInvoice.

Les valeurs stockées en base correspondent exactement aux libellés métier
français (par ex. le statut « En cours d'analyse »). Elles sont pilotées par
:func:`enum_values` passé en ``values_callable`` des colonnes ``Enum``.
"""

from __future__ import annotations

import enum
from typing import TypeVar

TEnum = TypeVar("TEnum", bound=enum.Enum)


def enum_values(enum_cls: type[TEnum]) -> list[str]:
    """Retourne les valeurs à persister pour une classe ``Enum``.

    Permet à SQLAlchemy de stocker ``member.value`` (libellé métier) plutôt
    que ``member.name``.
    """
    return [member.value for member in enum_cls]


class InvoiceStatus(str, enum.Enum):
    """Statut du cycle de vie d'une facture (valeurs exactes exigées).

    Transitions attendues :
    Déposée → En cours d'analyse → À vérifier → Validée/Rejetée
    Validée → Vendor Bill créée
    Erreur système possible à toute étape.
    """

    SUBMITTED = "Déposée"
    ANALYZING = "En cours d'analyse"
    TO_REVIEW = "À vérifier"
    VALIDATED = "Validée"
    VENDOR_BILL_CREATED = "Vendor Bill créée"
    REJECTED = "Rejetée"
    SYSTEM_ERROR = "Erreur système"


class UserRole(str, enum.Enum):
    """Rôle métier d'un utilisateur."""

    ACCOUNTANT = "Comptable"
    BUYER = "Acheteur"
    ADMIN = "Administrateur"


class AnomalyCategory(str, enum.Enum):
    """Catégorie d'une anomalie détectée lors du matching."""

    AMOUNT = "montant"
    TAX = "tva"
    QUANTITY = "quantite"
    PRODUCT_MISSING = "produit_absent"
    DUPLICATE = "doublon"
    SUPPLIER = "fournisseur"
    PURCHASE_ORDER = "bon_commande"
    OTHER = "autre"


class AnomalySeverity(str, enum.Enum):
    """Niveau de gravité d'une anomalie."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AuditAction(str, enum.Enum):
    """Action enregistrée dans le journal d'audit d'une facture (phase 7)."""

    VALIDATED = "validation"
    CORRECTED = "correction"
    REJECTED = "rejet"
    VENDOR_BILL_CREATED = "vendor_bill_créée"
