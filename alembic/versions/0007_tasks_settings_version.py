"""Tâches asynchrones, réglages persistants et pessimiste locking des factures.

- crée la table ``tasks`` (jobs OCR asynchrones, avec statut observable) ;
- crée la table ``settings`` (réglages clé/valeur persistants) ;
- ajoute la colonne ``version`` aux ``invoices`` (optimistic locking / CAS).

La colonne ``version`` est initialisée à 0 pour les factures existantes : le
premier write (CAS) acceptera une valeur attendue de 0, cohérent avec une
version courante initiale.

Revision ID: 0007_tasks_settings_version
Revises: 0006_add_audit_actions
Create Date: 2026-08-03
"""

from alembic import op
import sqlalchemy as sa

revision = "0007_tasks_settings_version"
down_revision = "0006_add_audit_actions"
branch_labels = None
depends_on = None

_TASK_STATES = ("en attente", "en cours", "réussi", "échoué")
_TASK_KINDS = ("ocr",)


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "kind",
            sa.Enum(*_TASK_KINDS, name="task_kind", native_enum=False),
            nullable=False,
        ),
        sa.Column(
            "state",
            sa.Enum(*_TASK_STATES, name="task_state", native_enum=False),
            nullable=False,
            server_default="en attente",
        ),
        sa.Column(
            "invoice_id",
            sa.Integer(),
            sa.ForeignKey("invoices.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
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
    op.create_index("ix_tasks_state_created_at", "tasks", ["state", "created_at"])
    op.create_index("ix_tasks_invoice_id", "tasks", ["invoice_id"])

    op.create_table(
        "settings",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("value", sa.String(255), nullable=False),
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

    with op.batch_alter_table("invoices") as batch_op:
        batch_op.add_column(
            sa.Column("version", sa.Integer(), nullable=False, server_default="0")
        )


def downgrade() -> None:
    with op.batch_alter_table("invoices") as batch_op:
        batch_op.drop_column("version")
    op.drop_table("settings")
    op.drop_index("ix_tasks_invoice_id", table_name="tasks")
    op.drop_index("ix_tasks_state_created_at", table_name="tasks")
    op.drop_table("tasks")