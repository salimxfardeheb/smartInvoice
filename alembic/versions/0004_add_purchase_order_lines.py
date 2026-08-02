"""Ajout des lignes de bon de commande (cache du purchase.order.line Odoo)

Création de la table purchase_order_lines : lignes d'un BC telles que
chargées depuis Odoo (quantité, unité, prix, remise, montant), liées à
purchase_orders et supprimées en cascade avec lui.

Revision ID: 0004_add_purchase_order_lines
Revises: 0003_add_invoice_file_metadata
Create Date: 2026-08-02
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_add_purchase_order_lines"
down_revision = "0003_add_invoice_file_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "purchase_order_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("purchase_order_id", sa.Integer(), nullable=False),
        sa.Column("odoo_id", sa.BigInteger(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("product_ref", sa.String(length=100), nullable=True),
        sa.Column("name", sa.String(length=500), nullable=True),
        sa.Column("quantity", sa.Numeric(precision=14, scale=3), nullable=True),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("unit_price", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("discount", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=True),
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
            ["purchase_order_id"],
            ["purchase_orders.id"],
            name="fk_purchase_order_lines_purchase_order_id_purchase_orders",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_purchase_order_lines"),
        sa.UniqueConstraint(
            "purchase_order_id",
            "odoo_id",
            name="uq_purchase_order_lines_po_odoo",
        ),
    )
    op.create_index(
        "ix_purchase_order_lines_purchase_order_id",
        "purchase_order_lines",
        ["purchase_order_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_purchase_order_lines_purchase_order_id",
        table_name="purchase_order_lines",
    )
    op.drop_table("purchase_order_lines")
