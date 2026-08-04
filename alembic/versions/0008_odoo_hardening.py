"""Durcissement de l'intégration Odoo (devises, taxes, retry Vendor Bill).

- crée la table ``currency_rates`` (taux de change par code devise vers une
  devise de référence, ex. EUR) — supporte le matching multi-devises ;
- ajoute la colonne ``tax_rate`` aux ``purchase_order_lines`` (référencement
  de la TVA lue dans Odoo ``account.tax``) ;
- ajoute aux ``invoices`` les colonnes de suivi des tentatives de création
  d'une Vendor Bill Odoo : ``vendor_bill_attempts`` (nombre de tentatives) et
  ``vendor_bill_error`` (dernier message d'échec).

Revision ID: 0008_odoo_hardening
Revises: 0007_tasks_settings_version
Create Date: 2026-08-04
"""

from alembic import op
import sqlalchemy as sa

revision = "0008_odoo_hardening"
down_revision = "0007_tasks_settings_version"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "currency_rates",
        sa.Column("code", sa.String(3), primary_key=True),
        sa.Column("base_currency", sa.String(3), nullable=False, server_default="EUR"),
        sa.Column("rate", sa.Numeric(16, 8), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    with op.batch_alter_table("purchase_order_lines") as batch_op:
        batch_op.add_column(
            sa.Column("tax_rate", sa.Numeric(14, 4), nullable=True)
        )

    with op.batch_alter_table("invoices") as batch_op:
        batch_op.add_column(
            sa.Column(
                "vendor_bill_attempts",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.add_column(
            sa.Column("vendor_bill_error", sa.Text(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("invoices") as batch_op:
        batch_op.drop_column("vendor_bill_error")
        batch_op.drop_column("vendor_bill_attempts")
    with op.batch_alter_table("purchase_order_lines") as batch_op:
        batch_op.drop_column("tax_rate")
    op.drop_table("currency_rates")