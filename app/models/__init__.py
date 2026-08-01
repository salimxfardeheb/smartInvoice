"""Modèles SQLAlchemy de SmartInvoice.

L'import de ce module enregistre l'intégralité des tables dans
``app.db.base.Base.metadata`` (nécessaire pour Alembic autogenerate).
"""

from app.models.anomaly import Anomaly
from app.models.invoice import Invoice
from app.models.invoice_line import InvoiceLine
from app.models.purchase_order import PurchaseOrder
from app.models.refresh_token import RefreshToken
from app.models.supplier import Supplier
from app.models.user import User

__all__ = [
    "Anomaly",
    "Invoice",
    "InvoiceLine",
    "PurchaseOrder",
    "RefreshToken",
    "Supplier",
    "User",
]
