"""Schéma initial SmartInvoice

Création des tables : users, suppliers, purchase_orders, invoices,
invoice_lines, anomalies.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-08-02
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Utilisateurs -------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=50), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=150), nullable=True),
        sa.Column(
            "role",
            sa.Enum(
                "Comptable",
                "Acheteur",
                "Administrateur",
                name="user_role",
                native_enum=False,
            ),
            nullable=False,
            server_default="Comptable",
        ),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "role IN ('Comptable', 'Acheteur', 'Administrateur')",
            name="ck_users_role",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    # --- Fournisseurs (cache local du res.partner Odoo) ---------------------
    op.create_table(
        "suppliers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("odoo_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("vat", sa.String(length=50), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_suppliers"),
        sa.UniqueConstraint("vat", name="uq_suppliers_vat"),
    )
    op.create_index("ix_suppliers_odoo_id", "suppliers", ["odoo_id"], unique=True)
    op.create_index("ix_suppliers_name", "suppliers", ["name"], unique=False)

    # --- Bons de commande (cache local du purchase.order Odoo) --------------
    op.create_table(
        "purchase_orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("odoo_id", sa.BigInteger(), nullable=False),
        sa.Column("reference", sa.String(length=64), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=True),
        sa.Column(
            "currency",
            sa.String(length=3),
            nullable=False,
            server_default="EUR",
        ),
        sa.Column("date_order", sa.Date(), nullable=True),
        sa.Column("total_amount", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["supplier_id"],
            ["suppliers.id"],
            name="fk_purchase_orders_supplier_id_suppliers",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_purchase_orders"),
        sa.UniqueConstraint("odoo_id", name="uq_purchase_orders_odoo_id"),
    )
    op.create_index(
        "ix_purchase_orders_reference", "purchase_orders", ["reference"], unique=True
    )
    op.create_index(
        "ix_purchase_orders_supplier_id",
        "purchase_orders",
        ["supplier_id"],
        unique=False,
    )

    # --- Factures -----------------------------------------------------------
    op.create_table(
        "invoices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("invoice_number", sa.String(length=100), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("purchase_order_id", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "Déposée",
                "En cours d'analyse",
                "À vérifier",
                "Validée",
                "Vendor Bill créée",
                "Rejetée",
                "Erreur système",
                name="invoice_status",
                native_enum=False,
            ),
            nullable=False,
            server_default="Déposée",
        ),
        sa.Column("issue_date", sa.Date(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column(
            "currency",
            sa.String(length=3),
            nullable=False,
            server_default="EUR",
        ),
        sa.Column("total_excl_tax", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("tax_amount", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("total_incl_tax", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("discount", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("shipping_fees", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("ocr_confidence_score", sa.Float(), nullable=True),
        sa.Column("matching_score", sa.Float(), nullable=True),
        sa.Column("vendor_bill_id", sa.BigInteger(), nullable=True),
        sa.Column("file_path", sa.String(length=500), nullable=True),
        sa.Column(
            "extracted_data",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=True,
        ),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "is_duplicate", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "status IN ('Déposée', 'En cours d''analyse', 'À vérifier', "
            "'Validée', 'Vendor Bill créée', 'Rejetée', 'Erreur système')",
            name="ck_invoices_status",
        ),
        sa.CheckConstraint(
            "ocr_confidence_score >= 0 AND ocr_confidence_score <= 1",
            name="ck_invoices_ocr_score_range",
        ),
        sa.CheckConstraint(
            "matching_score >= 0 AND matching_score <= 1",
            name="ck_invoices_matching_score_range",
        ),
        sa.ForeignKeyConstraint(
            ["supplier_id"],
            ["suppliers.id"],
            name="fk_invoices_supplier_id_suppliers",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["purchase_order_id"],
            ["purchase_orders.id"],
            name="fk_invoices_purchase_order_id_purchase_orders",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_invoices"),
        sa.UniqueConstraint(
            "supplier_id",
            "invoice_number",
            name="uq_invoice_supplier_invoice_number",
        ),
    )
    op.create_index("ix_invoices_supplier_id", "invoices", ["supplier_id"])
    op.create_index("ix_invoices_issue_date", "invoices", ["issue_date"])
    op.create_index(
        "ix_invoices_status_issue_date", "invoices", ["status", "issue_date"]
    )

    # --- Lignes de facture --------------------------------------------------
    op.create_table(
        "invoice_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("invoice_id", sa.Integer(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("product_ref", sa.String(length=100), nullable=True),
        sa.Column("quantity", sa.Numeric(precision=14, scale=3), nullable=True),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("unit_price", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("tax_rate", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("discount", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("purchase_order_line_odoo_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["invoice_id"],
            ["invoices.id"],
            name="fk_invoice_lines_invoice_id_invoices",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_invoice_lines"),
        sa.UniqueConstraint(
            "invoice_id", "line_number", name="uq_invoice_lines_invoice_line"
        ),
    )
    op.create_index("ix_invoice_lines_invoice_id", "invoice_lines", ["invoice_id"])

    # --- Anomalies ----------------------------------------------------------
    op.create_table(
        "anomalies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("invoice_id", sa.Integer(), nullable=False),
        sa.Column(
            "category",
            sa.Enum(
                "montant",
                "tva",
                "quantite",
                "produit_absent",
                "doublon",
                "fournisseur",
                "bon_commande",
                "autre",
                name="anomaly_category",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "severity",
            sa.Enum(
                "info",
                "warning",
                "critical",
                name="anomaly_severity",
                native_enum=False,
            ),
            nullable=False,
            server_default="warning",
        ),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("expected_value", sa.Text(), nullable=True),
        sa.Column("actual_value", sa.Text(), nullable=True),
        sa.Column(
            "resolved", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "category IN ('montant', 'tva', 'quantite', 'produit_absent', "
            "'doublon', 'fournisseur', 'bon_commande', 'autre')",
            name="ck_anomalies_category",
        ),
        sa.CheckConstraint(
            "severity IN ('info', 'warning', 'critical')", name="ck_anomalies_severity"
        ),
        sa.ForeignKeyConstraint(
            ["invoice_id"],
            ["invoices.id"],
            name="fk_anomalies_invoice_id_invoices",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_anomalies"),
    )
    op.create_index("ix_anomalies_invoice_id", "anomalies", ["invoice_id"])
    op.create_index("ix_anomalies_category", "anomalies", ["category"])


def downgrade() -> None:
    """Inverse complètement le schéma initial (ordre inverse des FKs)."""
    op.drop_index("ix_anomalies_category", table_name="anomalies")
    op.drop_index("ix_anomalies_invoice_id", table_name="anomalies")
    op.drop_table("anomalies")

    op.drop_index("ix_invoice_lines_invoice_id", table_name="invoice_lines")
    op.drop_table("invoice_lines")

    op.drop_index("ix_invoices_status_issue_date", table_name="invoices")
    op.drop_index("ix_invoices_issue_date", table_name="invoices")
    op.drop_index("ix_invoices_supplier_id", table_name="invoices")
    op.drop_table("invoices")

    op.drop_index("ix_purchase_orders_supplier_id", table_name="purchase_orders")
    op.drop_index("ix_purchase_orders_reference", table_name="purchase_orders")
    op.drop_table("purchase_orders")

    op.drop_index("ix_suppliers_name", table_name="suppliers")
    op.drop_index("ix_suppliers_odoo_id", table_name="suppliers")
    op.drop_table("suppliers")

    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
