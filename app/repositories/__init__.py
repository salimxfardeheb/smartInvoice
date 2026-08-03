"""Couche d'accès aux données (repository pattern).

Chaque repository encapsule les requêtes SQLAlchemy relatives à un agrégat
métier. Le CRUD générique est fourni par :class:`BaseRepository` ; les
repositories spécialisés ajoutent des méthodes typées de création et de
filtrage.
"""

from app.repositories.anomaly_repository import AnomalyRepository
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.base import BaseRepository
from app.repositories.invoice_line_repository import InvoiceLineRepository
from app.repositories.invoice_repository import InvoiceRepository
from app.repositories.purchase_order_line_repository import PurchaseOrderLineRepository
from app.repositories.purchase_order_repository import PurchaseOrderRepository
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.setting_repository import SettingRepository
from app.repositories.supplier_repository import SupplierRepository
from app.repositories.task_repository import TaskRepository
from app.repositories.user_repository import UserRepository

__all__ = [
    "AnomalyRepository",
    "AuditLogRepository",
    "BaseRepository",
    "InvoiceLineRepository",
    "InvoiceRepository",
    "PurchaseOrderLineRepository",
    "PurchaseOrderRepository",
    "RefreshTokenRepository",
    "SettingRepository",
    "SupplierRepository",
    "TaskRepository",
    "UserRepository",
]
