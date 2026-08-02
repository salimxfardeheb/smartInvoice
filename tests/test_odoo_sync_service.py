"""Tests unitaires du service de synchronisation Odoo (phase 5).

Le client Odoo est remplacé par un bouchon contrôlant les enregistrements
renvoyés pour chaque modèle. On vérifie : la résolution du fournisseur par
nom (introuvable / multiple / correspondance exacte), celle du bon de
commande par référence (introuvable / multiple / annulé / scopé fournisseur),
et le chargement idempotent des lignes de BC.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.exceptions import (
    MultiplePurchaseOrdersError,
    MultipleSuppliersFoundError,
    PurchaseOrderCancelledError,
    PurchaseOrderNotFoundError,
    SupplierNotFoundError,
)
from app.models.purchase_order import PurchaseOrder
from app.models.supplier import Supplier
from app.repositories import (
    PurchaseOrderLineRepository,
    PurchaseOrderRepository,
    SupplierRepository,
)
from app.services.odoo_service import OdooSyncService
from tests.conftest import make_supplier


class FakeOdooClient:
    """Bouchon du client Odoo : joue les enregistrements par modèle."""

    def __init__(
        self,
        *,
        partners: list[dict] | None = None,
        purchase_orders: list[dict] | None = None,
        lines: list[dict] | None = None,
        products: list[dict] | None = None,
    ) -> None:
        self.partners = list(partners or [])
        self.purchase_orders = list(purchase_orders or [])
        self.lines = list(lines or [])
        self.products = list(products or [])
        self.calls: list[tuple] = []

    def search_read(self, model, domain, fields, *, limit=None, offset=0) -> list[dict]:
        self.calls.append((model, domain, fields, limit, offset))
        table = {
            "res.partner": self.partners,
            "purchase.order": self.purchase_orders,
            "purchase.order.line": self.lines,
            "product.product": self.products,
        }[model]
        return list(table)


def make_service(session, **rows) -> OdooSyncService:
    """Service de test branché sur la session et le client bouchon."""
    return OdooSyncService(session, FakeOdooClient(**rows))


def _partner(odoo_id: int, name: str, **extra) -> dict:
    return {"id": odoo_id, "name": name, **extra}


def _po(odoo_id: int, reference: str, partner_id: int, **extra) -> dict:
    return {
        "id": odoo_id,
        "name": reference,
        "partner_id": (partner_id, "ACME SAS"),
        "state": "purchase",
        "date_order": "2026-01-10",
        "amount_total": 1500.0,
        "currency_id": (1, "EUR"),
        **extra,
    }


class TestSyncSupplier:
    def test_found_and_cached(self, session) -> None:
        service = make_service(
            session,
            partners=[
                _partner(
                    42, "ACME SAS", vat="FR12345678901",
                    street="12 rue des Lilas", zip="75011", city="Paris",
                )
            ],
        )
        supplier = service.sync_supplier_from_name("ACME SAS")

        assert isinstance(supplier, Supplier)
        assert supplier.odoo_id == 42
        assert supplier.name == "ACME SAS"
        assert supplier.vat == "FR12345678901"
        assert supplier.address == "12 rue des Lilas, 75011, Paris"

        # Persisté dans le cache local, retrouvable par odoo_id.
        cached = SupplierRepository(session).get_by_odoo_id(42)
        assert cached is supplier

        # La recherche interroge bien les fournisseurs de res.partner.
        model, domain, fields, limit, _ = service.client.calls[0]
        assert model == "res.partner"
        assert ["name", "ilike", "ACME SAS"] in domain
        assert ["supplier_rank", ">", 0] in domain
        assert "vat" in fields

    def test_updates_existing_supplier(self, session) -> None:
        make_supplier(session, odoo_id=42, name="Ancien nom")
        session.commit()
        service = make_service(session, partners=[_partner(42, "ACME SAS")])

        supplier = service.sync_supplier_from_name("ACME SAS")

        assert supplier.odoo_id == 42
        assert supplier.name == "ACME SAS"
        assert SupplierRepository(session).count() == 1

    def test_not_found_raises(self, session) -> None:
        service = make_service(session, partners=[])
        with pytest.raises(SupplierNotFoundError):
            service.sync_supplier_from_name("Inexistant")

    def test_empty_name_raises(self, session) -> None:
        service = make_service(session)
        with pytest.raises(SupplierNotFoundError):
            service.sync_supplier_from_name("   ")

    def test_multiple_matches_raises(self, session) -> None:
        service = make_service(
            session,
            partners=[
                _partner(1, "ACME France"),
                _partner(2, "ACME Europe"),
            ],
        )
        with pytest.raises(MultipleSuppliersFoundError):
            service.sync_supplier_from_name("ACME")

    def test_exact_match_is_preferred(self, session) -> None:
        service = make_service(
            session,
            partners=[
                _partner(1, "ACME SAS"),
                _partner(2, "ACME SAS International"),
            ],
        )
        supplier = service.sync_supplier_from_name("ACME SAS")
        assert supplier.odoo_id == 1


class TestFindPurchaseOrder:
    def test_found_and_cached(self, session) -> None:
        make_supplier(session, odoo_id=42, name="ACME SAS")
        session.commit()
        service = make_service(
            session,
            purchase_orders=[_po(100, "PO-2026-001", 42)],
        )
        supplier = SupplierRepository(session).get_by_odoo_id(42)

        po = service.find_purchase_order("PO-2026-001", supplier=supplier)

        assert isinstance(po, PurchaseOrder)
        assert po.odoo_id == 100
        assert po.reference == "PO-2026-001"
        assert po.state == "purchase"
        assert po.supplier_id == supplier.id
        assert po.total_amount == Decimal("1500.0")

        cached = PurchaseOrderRepository(session).get_by_reference("PO-2026-001")
        assert cached is po

    def test_scoped_by_supplier(self, session) -> None:
        make_supplier(session, odoo_id=42, name="ACME SAS")
        session.commit()
        service = make_service(session, purchase_orders=[_po(100, "PO-2026-001", 42)])
        supplier = SupplierRepository(session).get_by_odoo_id(42)

        service.find_purchase_order("PO-2026-001", supplier=supplier)

        _, domain, _, _, _ = service.client.calls[0]
        assert ["partner_id", "=", 42] in domain

    def test_not_found_raises(self, session) -> None:
        service = make_service(session, purchase_orders=[])
        with pytest.raises(PurchaseOrderNotFoundError):
            service.find_purchase_order("PO-0000")

    def test_multiple_matches_raise(self, session) -> None:
        service = make_service(
            session,
            purchase_orders=[_po(1, "PO-X", 42), _po(2, "PO-X", 43)],
        )
        with pytest.raises(MultiplePurchaseOrdersError):
            service.find_purchase_order("PO-X")

    def test_cancelled_order_raises(self, session) -> None:
        service = make_service(
            session,
            purchase_orders=[_po(100, "PO-CANCEL", 42, state="cancel")],
        )
        with pytest.raises(PurchaseOrderCancelledError):
            service.find_purchase_order("PO-CANCEL")

    def test_requires_synced_supplier(self, session) -> None:
        service = make_service(
            session,
            purchase_orders=[_po(100, "PO-2026-001", 999)],
        )
        with pytest.raises(SupplierNotFoundError):
            service.find_purchase_order("PO-2026-001")

    def test_empty_reference_raises(self, session) -> None:
        service = make_service(session)
        with pytest.raises(PurchaseOrderNotFoundError):
            service.find_purchase_order("   ")

    def test_supplier_resolved_from_order_when_synced(self, session) -> None:
        make_supplier(session, odoo_id=42, name="ACME SAS")
        session.commit()
        service = make_service(
            session,
            purchase_orders=[_po(100, "PO-2026-001", 42)],
        )

        po = service.find_purchase_order("PO-2026-001")

        assert po.supplier_id == SupplierRepository(session).get_by_odoo_id(42).id

    def test_existing_order_is_updated(self, session) -> None:
        supplier = make_supplier(session, odoo_id=42, name="ACME SAS")
        po = PurchaseOrderRepository(session).create(
            odoo_id=100, reference="PO-VIEUX", supplier_id=supplier.id,
            state="draft",
        )
        session.commit()
        service = make_service(
            session,
            purchase_orders=[_po(100, "PO-2026-001", 42)],
        )

        updated = service.find_purchase_order("PO-2026-001")

        assert updated.id == po.id
        assert updated.reference == "PO-2026-001"
        assert updated.state == "purchase"
        assert PurchaseOrderRepository(session).count() == 1


class TestLoadPurchaseOrderLines:
    def _po(self, session) -> PurchaseOrder:
        supplier = make_supplier(session, odoo_id=42, name="ACME SAS")
        return PurchaseOrderRepository(session).create(
            odoo_id=100, reference="PO-2026-001", supplier_id=supplier.id
        )

    def test_lines_loaded_and_cached(self, session) -> None:
        po = self._po(session)
        service = make_service(
            session,
            lines=[
                {
                    "id": 1, "order_id": 100, "sequence": 10,
                    "product_id": (5, "Câble HDMI"), "name": "Câble HDMI",
                    "product_qty": 2.0, "product_uom": (1, "Unités"),
                    "price_unit": 8.5, "discount": 0.0, "price_subtotal": 17.0,
                },
                {
                    "id": 2, "order_id": 100, "sequence": 20,
                    "product_id": (6, "Écran LED"), "name": "Écran LED",
                    "product_qty": 1.0, "product_uom": (1, "Unités"),
                    "price_unit": 149.0, "discount": 0.0, "price_subtotal": 149.0,
                },
            ],
            products=[
                {"id": 5, "default_code": "CBL-001"},
                {"id": 6, "default_code": "SCR-24"},
            ],
        )

        lines = service.load_purchase_order_lines(po)

        assert len(lines) == 2
        first = lines[0]
        assert first.line_number == 10
        assert first.product_ref == "CBL-001"
        assert first.name == "Câble HDMI"
        assert first.quantity == Decimal("2.0")
        assert first.unit == "Unités"
        assert first.amount == Decimal("17.0")

        cached = PurchaseOrderLineRepository(session).list_by_purchase_order(po.id)
        assert len(cached) == 2
        assert cached[0].line_number == 10

    def test_lines_load_is_idempotent(self, session) -> None:
        po = self._po(session)
        service = make_service(
            session,
            lines=[{
                "id": 1, "order_id": 100, "sequence": 10,
                "product_id": (5, "Câble"), "name": "Câble",
                "product_qty": 2.0, "product_uom": (1, "Unités"),
                "price_unit": 8.5, "discount": 0.0, "price_subtotal": 17.0,
            }],
            products=[{"id": 5, "default_code": "CBL-001"}],
        )

        service.load_purchase_order_lines(po)
        service.load_purchase_order_lines(po)

        cached = PurchaseOrderLineRepository(session).list_by_purchase_order(po.id)
        assert len(cached) == 1

    def test_empty_lines_return_empty_list(self, session) -> None:
        po = self._po(session)
        service = make_service(session, lines=[], products=[])
        assert service.load_purchase_order_lines(po) == []

    def test_no_product_id_leaves_no_ref(self, session) -> None:
        po = self._po(session)
        service = make_service(
            session,
            lines=[{
                "id": 1, "order_id": 100, "sequence": 10,
                "product_id": False, "name": "Service",
                "product_qty": 1.0, "product_uom": (1, "Unités"),
                "price_unit": 100.0, "discount": 0.0, "price_subtotal": 100.0,
            }],
        )
        lines = service.load_purchase_order_lines(po)
        assert lines[0].product_ref is None
        # Aucun appel product.product si aucune ligne ne porte de produit.
        models = [call[0] for call in service.client.calls]
        assert "product.product" not in models


class TestConversionHelpers:
    """Branches des helpers de conversion (nom, devise, décimal, date)."""

    def test_name_of_non_tuple_returns_none(self) -> None:
        assert OdooSyncService._name_of(42) is None
        assert OdooSyncService._name_of(("x",)) is None
        assert OdooSyncService._name_of(("x", "")) is None

    def test_as_decimal_passthrough(self) -> None:
        assert OdooSyncService._as_decimal(None) is None
        value = Decimal("1.5")
        assert OdooSyncService._as_decimal(value) is value

    def test_as_decimal_invalid_returns_none(self) -> None:
        assert OdooSyncService._as_decimal("pas-un-nombre") is None

    def test_as_date_handles_every_type(self) -> None:
        from datetime import date, datetime, timedelta

        assert OdooSyncService._as_date(None) is None
        day = date(2026, 1, 10)
        assert OdooSyncService._as_date(day) is day
        assert OdooSyncService._as_date(datetime(2026, 1, 10, 12, 30)) == datetime(2026, 1, 10, 12, 30)
        assert OdooSyncService._as_date("2026-01-10T00:00:00") == day
        assert OdooSyncService._as_date("pas-une-date") is None
        assert OdooSyncService._as_date(12345) is None
        assert OdooSyncService._as_date(timedelta(days=1)) is None
