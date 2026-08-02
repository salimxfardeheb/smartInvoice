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


class NotFoundError(SmartInvoiceError):
    """Ressource introuvable."""


class SupplierNotFoundError(NotFoundError):
    """Le fournisseur référencé n'existe pas."""


class DocumentNotFoundError(NotFoundError):
    """Le fichier source d'une facture est absent ou introuvable."""


class ConflictError(SmartInvoiceError):
    """Conflit avec l'état actuel de la ressource."""


class DuplicateInvoiceError(ConflictError):
    """Une facture identique (fournisseur + numéro) existe déjà."""


class InvalidStatusTransitionError(ConflictError):
    """Transition de statut non autorisée."""


class InvalidDocumentError(SmartInvoiceError):
    """Document non supporté, corrompu ou illisible."""


class DocumentIllegibleError(SmartInvoiceError):
    """Aucun texte exploitable n'a pu être extrait par l'OCR."""


class OcrEngineError(SmartInvoiceError):
    """Échec du moteur OCR ou du rendu du document."""


class OdooError(SmartInvoiceError):
    """Erreur d'intégration avec le serveur Odoo."""


class OdooNotConfiguredError(OdooError):
    """La configuration Odoo (URL, base, identifiants) est absente/incomplète."""


class OdooConnectionError(OdooError):
    """Impossible de joindre le serveur Odoo (réseau, timeout, protocole)."""


class OdooAuthenticationError(OdooError):
    """Authentification Odoo refusée (identifiants, base ou droits)."""


class OdooModelError(OdooError):
    """Odoo a rejeté l'appel de modèle (modèle ou champ inconnu)."""


class MultipleSuppliersFoundError(ConflictError):
    """Plusieurs fournisseurs correspondent au nom extrait par l'OCR."""


class PurchaseOrderNotFoundError(NotFoundError):
    """Aucun bon de commande ne correspond à la référence extraite."""


class MultiplePurchaseOrdersError(ConflictError):
    """Plusieurs bons de commande correspondent à la référence extraite."""


class PurchaseOrderCancelledError(ConflictError):
    """Le bon de commande correspondant est annulé (state == cancel)."""
