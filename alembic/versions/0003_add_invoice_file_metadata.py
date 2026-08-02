"""Métadonnées de fichier sur les factures (phase 3 - documents)

Revision ID: 0003_add_invoice_file_metadata
Revises: 0002_add_refresh_tokens
Create Date: 2026-08-02
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_add_invoice_file_metadata"
down_revision = "0002_add_refresh_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "invoices",
        sa.Column("original_filename", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "invoices",
        sa.Column("content_type", sa.String(length=100), nullable=True),
    )
    op.add_column("invoices", sa.Column("file_size", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("invoices", "file_size")
    op.drop_column("invoices", "content_type")
    op.drop_column("invoices", "original_filename")
