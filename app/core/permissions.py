"""Registre des rôles métier et de leurs permissions.

La matrice des permissions est définie ici de manière centralisée :
chaque rôle (Comptable, Acheteur, Administrateur) dispose d'un ensemble de
permissions exprimées par des chaînes normalisées ``objet:action``.
"""

from __future__ import annotations

import enum

from app.models.enums import UserRole


class Permission(str, enum.Enum):
    """Permissions métier SmartInvoice."""

    # Factures — utilisées à partir de la phase 3
    INVOICE_READ = "invoice:read"
    INVOICE_DEPOSIT = "invoice:deposit"  # Comptable : dépose
    INVOICE_VALIDATE = "invoice:validate"  # Comptable : valide
    INVOICE_CORRECT = "invoice:correct"  # Comptable : corrige
    INVOICE_CONFIRM = "invoice:confirm"  # Acheteur : confirme quantités/produits
    # Utilisateurs
    USER_READ = "user:read"
    USER_WRITE = "user:write"
    USER_DEACTIVATE = "user:deactivate"
    # Configuration & journaux
    CONFIG_READ = "config:read"
    CONFIG_WRITE = "config:write"
    JOURNAL_READ = "journal:read"


_ALL_PERMISSIONS = frozenset(Permission)


ROLE_PERMISSIONS: dict[UserRole, frozenset[Permission]] = {
    UserRole.ADMIN: _ALL_PERMISSIONS,
    UserRole.ACCOUNTANT: frozenset(
        {
            Permission.INVOICE_READ,
            Permission.INVOICE_DEPOSIT,
            Permission.INVOICE_VALIDATE,
            Permission.INVOICE_CORRECT,
            Permission.JOURNAL_READ,
        }
    ),
    UserRole.BUYER: frozenset(
        {
            Permission.INVOICE_READ,
            Permission.INVOICE_CONFIRM,
        }
    ),
}


def permissions_for(role: UserRole) -> frozenset[Permission]:
    """Retourne les permissions accordées à un rôle."""
    return ROLE_PERMISSIONS.get(role, frozenset())


def has_permission(role: UserRole, permission: Permission) -> bool:
    """Indique si un rôle dispose d'une permission donnée."""
    return permission in permissions_for(role)
