"""Modèles SQLAlchemy de SmartInvoice.

L'import de ce module enregistre l'intégralité des tables dans
``app.db.base.Base.metadata`` (nécessaire pour Alembic autogenerate).
"""

from app.models.anomaly import Anomaly
from app.models.audit_log import AuditLog
from app.models.invoice import Invoice
from app.models.invoice_line import InvoiceLine
from app.models.purchase_order import PurchaseOrder
from app.models.purchase_order_line import PurchaseOrderLine
from app.models.refresh_token import RefreshToken
from app.models.setting import Setting
from app.models.supplier import Supplier
from app.models.task import Task
from app.models.user import User

__all__ = [
    "Anomaly",
    "AuditLog",
    "Invoice",
    "InvoiceLine",
    "PurchaseOrder",
    "PurchaseOrderLine",
    "RefreshToken",
    "Setting",
    "Supplier",
    "Task",
    "User",
]
