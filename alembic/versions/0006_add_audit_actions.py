"""Extension du journal d'audit (nouvelles actions).

Ajoute les actions « confirmation_acheteur » (confirmation des
quantités/produits par l'acheteur) et « re_analyse » (relance d'une facture
en « Erreur système ») à l'énumération et à la contrainte CHECK de
``audit_logs.action``.

Revision ID: 0006_add_audit_actions
Revises: 0005_add_audit_logs
Create Date: 2026-08-03
"""

from alembic import op
import sqlalchemy as sa

revision = "0006_add_audit_actions"
down_revision = "0005_add_audit_logs"
branch_labels = None
depends_on = None

_AUDIT_ACTIONS = (
    "validation",
    "correction",
    "rejet",
    "vendor_bill_créée",
    "confirmation_acheteur",
    "re_analyse",
)


def upgrade() -> None:
    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.alter_column(
            "action",
            type_=sa.Enum(*_AUDIT_ACTIONS, name="audit_action", native_enum=False),
        )
        batch_op.drop_constraint("ck_audit_logs_action", type_="check")
        batch_op.create_check_constraint(
            "ck_audit_logs_action",
            "action IN " + _assert_list(),
        )


def downgrade() -> None:
    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.alter_column(
            "action",
            type_=sa.Enum(
                "validation", "correction", "rejet", "vendor_bill_créée",
                name="audit_action", native_enum=False,
            ),
        )
        batch_op.drop_constraint("ck_audit_logs_action", type_="check")
        batch_op.create_check_constraint(
            "ck_audit_logs_action",
            "action IN ('validation', 'correction', 'rejet', 'vendor_bill_créée')",
        )


def _assert_list() -> str:
    """Expression SQL de la liste des actions autorisées."""
    return "(" + ", ".join(f"'{a}'" for a in _AUDIT_ACTIONS) + ")"