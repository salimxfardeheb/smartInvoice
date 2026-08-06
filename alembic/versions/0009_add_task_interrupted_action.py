"""Nouvelle action d'audit « tâche_interrompue ».

Ajoute l'action tracée par la reprise au démarrage
(:mod:`app.services.startup_recovery`) : une tâche laissée dans l'état « en
cours » par un arrêt du serveur est neutralisée au démarrage suivant, et la
facture éventuellement bloquée en « En cours d'analyse » repasse en « Erreur
système ». L'entrée d'audit correspondante n'a pas d'utilisateur (``user_id``
NULL) puisqu'elle est produite par le système.

Met à jour l'énumération et la contrainte CHECK de ``audit_logs.action``.

Revision ID: 0009_add_task_interrupted_action
Revises: 0008_odoo_hardening
Create Date: 2026-08-06
"""

from alembic import op
import sqlalchemy as sa

revision = "0009_add_task_interrupted_action"
down_revision = "0008_odoo_hardening"
branch_labels = None
depends_on = None

_PREVIOUS_ACTIONS = (
    "validation",
    "correction",
    "rejet",
    "vendor_bill_créée",
    "confirmation_acheteur",
    "re_analyse",
)

_AUDIT_ACTIONS = _PREVIOUS_ACTIONS + ("tâche_interrompue",)


def _in_list(actions: tuple[str, ...]) -> str:
    """Expression SQL ``IN (...)`` de la liste des actions autorisées."""
    return "(" + ", ".join(f"'{action}'" for action in actions) + ")"


def upgrade() -> None:
    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.alter_column(
            "action",
            type_=sa.Enum(*_AUDIT_ACTIONS, name="audit_action", native_enum=False),
        )
        batch_op.drop_constraint("ck_audit_logs_action", type_="check")
        batch_op.create_check_constraint(
            "ck_audit_logs_action",
            "action IN " + _in_list(_AUDIT_ACTIONS),
        )


def downgrade() -> None:
    # Les entrées produites par la reprise au démarrage n'appartiennent à
    # aucune action antérieure : elles sont supprimées avant de restreindre la
    # contrainte, sans quoi le CHECK échouerait sur les lignes existantes.
    op.execute("DELETE FROM audit_logs WHERE action = 'tâche_interrompue'")
    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.alter_column(
            "action",
            type_=sa.Enum(*_PREVIOUS_ACTIONS, name="audit_action", native_enum=False),
        )
        batch_op.drop_constraint("ck_audit_logs_action", type_="check")
        batch_op.create_check_constraint(
            "ck_audit_logs_action",
            "action IN " + _in_list(_PREVIOUS_ACTIONS),
        )
