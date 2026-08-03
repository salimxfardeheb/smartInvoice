"""Schémas de l'API Validation (phase 7) et du journal d'audit.

Couverture : rejet d'une facture (motif obligatoire), correction manuelle des
données extraites (champs facture et lignes) et lecture du journal d'audit.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AuditAction


class InvoiceReject(BaseModel):
    """Rejet d'une facture : le motif est obligatoire."""

    reason: str = Field(min_length=1, max_length=1000, description="Motif du rejet")


class InvoiceLineConfirm(BaseModel):
    """Confirmation d'une ligne de facture par l'acheteur (quantité/produit)."""

    line_number: int = Field(ge=1, description="Position de la ligne dans la facture")
    confirmed: bool = Field(
        default=True, description="Confirme la ligne telle qu'elle est libérée"
    )
    quantity: Decimal | None = Field(
        default=None, description="Quantité confirmée (écrase la valeur extraite)"
    )
    unit_price: Decimal | None = Field(
        default=None, description="Prix unitaire confirmé (écrase la valeur extraite)"
    )
    product_ref: str | None = Field(
        default=None, max_length=100, description="Référence produit confirmée"
    )


class InvoiceConfirm(BaseModel):
    """Confirmation des quantités/produits d'une facture par l'acheteur."""

    lines: list[InvoiceLineConfirm] = Field(default_factory=list)


class InvoiceLineCorrection(BaseModel):
    """Correction d'une ligne de facture (remplacement complet de la ligne)."""

    line_number: int = Field(ge=1, description="Position de la ligne dans la facture")
    description: str = Field(min_length=1, max_length=500)
    product_ref: str | None = Field(default=None, max_length=100)
    quantity: Decimal | None = None
    unit: str | None = Field(default=None, max_length=32)
    unit_price: Decimal | None = None
    tax_rate: Decimal | None = None
    discount: Decimal | None = None
    amount: Decimal | None = None


class InvoiceCorrection(BaseModel):
    """Correction manuelle des données extraites d'une facture.

    Seuls les champs fournis sont modifiés. Si ``lines`` est fourni, les
    lignes de la facture sont resynchronisées : celles présentes sont mises à
    jour, celles absentes sont supprimées, les nouvelles sont créées.
    """

    invoice_number: str | None = Field(default=None, min_length=1, max_length=100)
    issue_date: date | None = None
    due_date: date | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    total_excl_tax: Decimal | None = None
    tax_amount: Decimal | None = None
    total_incl_tax: Decimal | None = None
    discount: Decimal | None = None
    shipping_fees: Decimal | None = None
    lines: list[InvoiceLineCorrection] | None = None


class AuditUserBrief(BaseModel):
    """Représentation allégée de l'utilisateur à l'origine d'une action."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: str | None = None


class AuditLogRead(BaseModel):
    """Entrée du journal d'audit exposée par l'API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    invoice_id: int
    action: AuditAction
    message: str
    details: dict | None = None
    user: AuditUserBrief | None = None
    created_at: datetime


class AuditLogListResponse(BaseModel):
    """Résultat paginé du journal d'audit d'une facture."""

    items: list[AuditLogRead]
    total: int
