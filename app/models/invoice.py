"""Modèle « facture » : entité centrale du flux SmartInvoice."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    false,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import InvoiceStatus, enum_values
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:  # pragma: no cover - évite les imports circulaires à runtime
    from app.models.anomaly import Anomaly
    from app.models.audit_log import AuditLog
    from app.models.invoice_line import InvoiceLine
    from app.models.purchase_order import PurchaseOrder
    from app.models.supplier import Supplier
    from app.models.task import Task

# Portabilité : JSONB en production (PostgreSQL), JSON ailleurs (tests SQLite).
JsonType = JSON().with_variant(JSONB(), "postgresql")


class Invoice(Base, TimestampMixin):
    """Facture fournisseur déposée et suivie par SmartInvoice.

    Contrainte métier clé : un couple (fournisseur, numéro de facture) est
    unique — c'est la règle de détection des doublons
    (``uq_invoice_supplier_invoice_number``).
    """

    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint(
            "supplier_id", "invoice_number", name="uq_invoice_supplier_invoice_number"
        ),
        Index("ix_invoices_status_issue_date", "status", "issue_date"),
        CheckConstraint(
            "status IN ('Déposée', 'En cours d''analyse', 'À vérifier', "
            "'Validée', 'Vendor Bill créée', 'Rejetée', 'Erreur système')",
            name="status",
        ),
        CheckConstraint(
            "ocr_confidence_score >= 0 AND ocr_confidence_score <= 1",
            name="ocr_score_range",
        ),
        CheckConstraint(
            "matching_score >= 0 AND matching_score <= 1",
            name="matching_score_range",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_number: Mapped[str] = mapped_column(String(100), nullable=False)
    supplier_id: Mapped[int] = mapped_column(
        ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    purchase_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("purchase_orders.id", ondelete="SET NULL")
    )
    status: Mapped[InvoiceStatus] = mapped_column(
        Enum(
            InvoiceStatus,
            name="invoice_status",
            native_enum=False,
            values_callable=enum_values,
        ),
        nullable=False,
        default=InvoiceStatus.SUBMITTED,
        server_default=InvoiceStatus.SUBMITTED.value,
    )
    issue_date: Mapped[date | None] = mapped_column(Date, index=True)
    due_date: Mapped[date | None] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="EUR", server_default="EUR"
    )
    total_excl_tax: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    tax_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    total_incl_tax: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    discount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    shipping_fees: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    ocr_confidence_score: Mapped[float | None] = mapped_column(Float)
    matching_score: Mapped[float | None] = mapped_column(Float)
    vendor_bill_id: Mapped[int | None] = mapped_column(
        BigInteger
    )  # id de la account.move Odoo (phase 7)
    file_path: Mapped[str | None] = mapped_column(String(500))
    original_filename: Mapped[str | None] = mapped_column(String(255))
    content_type: Mapped[str | None] = mapped_column(String(100))
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    extracted_data: Mapped[dict | None] = mapped_column(JsonType)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    is_duplicate: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    # Optimistic locking : seuls les objets versionnés (factures) réalisent des
    # transitions d'état concurrentes. Chaque écriture incrémente `version` via
    # un update conditionnel (CAS) ; une lecture périmée provoque un
    # `ConcurrentModificationError` au lieu d'un écrasement silencieux.
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    supplier: Mapped[Supplier] = relationship(back_populates="invoices")
    purchase_order: Mapped[PurchaseOrder | None] = relationship(
        back_populates="invoices"
    )
    lines: Mapped[list[InvoiceLine]] = relationship(
        back_populates="invoice",
        cascade="all, delete-orphan",
        order_by="InvoiceLine.line_number",
        passive_deletes=True,
    )
    anomalies: Mapped[list[Anomaly]] = relationship(
        back_populates="invoice",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    audit_logs: Mapped[list[AuditLog]] = relationship(
        back_populates="invoice",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    tasks: Mapped[list[Task]] = relationship(back_populates="invoice")

    @property
    def file_info(self) -> dict | None:
        """Métadonnées du fichier source (None si aucune facture déposée)."""
        if self.original_filename is None:
            return None
        return {
            "original_filename": self.original_filename,
            "content_type": self.content_type,
            "size": self.file_size,
        }

    def __repr__(self) -> str:  # pragma: no cover - aide au debug
        return (
            f"<Invoice id={self.id} number={self.invoice_number!r} "
            f"status={self.status!r}>"
        )
