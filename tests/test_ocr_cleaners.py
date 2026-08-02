"""Tests unitaires du nettoyage OCR (phase 4).

Couvre : nettoyage de texte, normalisation des montants (conventions
française/anglaise, signes, parenthèses), extraction des montants (avec rejet
des dates, identifiants et pourcentages), dates et détection de devise.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.ocr.cleaners import (
    clean_text,
    detect_currency,
    find_amounts,
    normalize_amount,
    normalize_date,
)


class TestCleanText:
    def test_collapses_spaces(self) -> None:
        assert clean_text("  Total   HT  :   ") == "Total HT"

    def test_strips_trailing_separators(self) -> None:
        assert clean_text("123,45 |") == "123,45"


class TestNormalizeAmount:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("1234,56", Decimal("1234.56")),
            ("1 234,56", Decimal("1234.56")),
            ("1\u202f234,56", Decimal("1234.56")),
            ("1\u00a0234,56", Decimal("1234.56")),
            ("1.234,56", Decimal("1234.56")),
            ("1,234.56", Decimal("1234.56")),
            ("125,00 €", Decimal("125.00")),
            ("12 345,67 €", Decimal("12345.67")),
            ("-25,00", Decimal("-25.00")),
            ("(25,00)", Decimal("-25.00")),
            ("50", Decimal("50")),
            (".75", Decimal("0.75")),
        ],
    )
    def test_parses_valid_amounts(self, raw: str, expected: Decimal) -> None:
        assert normalize_amount(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        ["abc", "15.01.2026", "20 %", "2m", "12-345", "HT", ""],
    )
    def test_rejects_illisible_amounts(self, raw: str) -> None:
        assert normalize_amount(raw) is None


class TestFindAmounts:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("Total HT 1\u202f234,56 €", ["1234.56"]),
            ("Total HT 1 234,56 €", ["1", "234.56"]),
            ("TVA 20% : 25,10 €", ["25.10"]),
            ("Câble HDMI 2m 2 8,50 17,00", ["2", "8.50", "17.00"]),
            ("Écran LED 1 149,00 149,00", ["1", "149.00", "149.00"]),
            ("Livraison 5,90", ["5.90"]),
            ("Remise -25,00", ["-25.00"]),
            ("Montant (25,00)", ["-25.00"]),
            ("Total TTC 206,28.", ["206.28"]),
            ("1\u202f234,56", ["1234.56"]),
            ("aucun montant ici", []),
        ],
    )
    def test_finds_amounts(self, text: str, expected: list[str]) -> None:
        assert [str(value) for value in find_amounts(text)] == expected

    @pytest.mark.parametrize(
        "text",
        [
            "Facture N° FAC-2026-001",
            "Bon de commande : PO-2026-0123",
            "XLR-500 Câble audio",
            "Échéance : 15-02-2026",
            "Paiement dû le 15.02.2026",
        ],
    )
    def test_ignores_identifiers_and_dates(self, text: str) -> None:
        assert find_amounts(text) == []


class TestNormalizeDate:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("15/01/2026", date(2026, 1, 15)),
            ("15-01-2026", date(2026, 1, 15)),
            ("15.01.2026", date(2026, 1, 15)),
            ("15 janvier 2026", date(2026, 1, 15)),
            ("1er février 2026", date(2026, 2, 1)),
            ("2026-01-15", date(2026, 1, 15)),
            ("31/12/1999", date(1999, 12, 31)),
        ],
    )
    def test_normalizes_dates(self, raw: str, expected: date) -> None:
        assert normalize_date(raw) == expected

    @pytest.mark.parametrize("raw", ["31/02/2026", "15/13/2026", "foo", ""])
    def test_rejects_invalid_dates(self, raw: str) -> None:
        assert normalize_date(raw) is None


class TestDetectCurrency:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("Total TTC 1 234,56 €", "EUR"),
            ("Total USD 100", "USD"),
            ("Prix : 45,00 CHF", "CHF"),
            ("Montant en GBP", "GBP"),
        ],
    )
    def test_detects_currency(self, text: str, expected: str) -> None:
        assert detect_currency(text) == expected

    def test_no_currency(self) -> None:
        assert detect_currency("Montant total") is None
