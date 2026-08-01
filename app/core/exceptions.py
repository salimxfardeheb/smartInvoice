"""Exceptions métier de l'application.

Elles sont traduites en réponses HTTP par des exception handlers dans
``app.main`` :
- :class:`AuthenticationError` (et ses sous-classes) → HTTP 401 ;
- :class:`PermissionDeniedError` → HTTP 403 ;
- :class:`UserAlreadyExistsError` → HTTP 409.
"""

from __future__ import annotations


class SmartInvoiceError(Exception):
    """Erreur de base de l'application."""


class AuthenticationError(SmartInvoiceError):
    """Erreur d'authentification (jeton absent/invalide, identifiants)."""


class InvalidCredentialsError(AuthenticationError):
    """Identifiants (nom/email + mot de passe) incorrects."""


class InvalidTokenError(AuthenticationError):
    """Jeton JWT invalide (signature, type ou revendications)."""


class ExpiredTokenError(AuthenticationError):
    """Jeton JWT expiré."""


class UserInactiveError(AuthenticationError):
    """Le compte de l'utilisateur est désactivé."""


class PermissionDeniedError(SmartInvoiceError):
    """L'utilisateur ne dispose pas de la permission requise."""


class UserAlreadyExistsError(SmartInvoiceError):
    """Un utilisateur avec ce nom d'utilisateur ou cet email existe déjà."""
