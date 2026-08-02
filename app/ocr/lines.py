"""Parseur des lignes de facture à partir des textes OCR.

Méthode heuristique pour le MVP : une ligne est considérée comme une ligne de
facture si elle contient des montants exploitables et n'est ni un libellé
d'en-tête de tableau ni une ligne de totaux. La répartition « quantité, prix
unitaire, montant » repose sur le nombre de montants présents. Ce parseur
cible des factures au format tabulaire classique.
"""

from __future__ import annotations

import re

from app.ocr.cleaners import (
    clean_text,
    find_amounts,
    find_amounts_with_spans,
    normalize_amount,
)
from app.ocr.schema import OcrLineItem

# Lignes exclues : totaux et en-têtes de tableau.
_TOTAL_KEYWORDS = (
    "total",
    "sous-total",
    "subtotal",
    "remise",
    "discount",
    "livraison",
    "shipping",
    "transport",
    "tva",
    "taxe",
    "net à payer",
    "net a payer",
    "arrondi",
    "acompte",
    "avoir",
)
_HEADER_KEYWORDS = (
    "désignation",
    "designation",
    "description",
    "libellé",
    "libelle",
    "référence",
    "reference",
    "réf",
    "ref ",
    "quantité",
    "quantite",
    "qté",
    "qte",
    "prix",
    "montant",
    "unité",
    "unite",
    "code",
    "article",
    "produit",
)
_ADDRESS_KEYWORDS = (
    "rue",
    "avenue",
    "boulevard",
    "cedex",
    "street",
    "road",
    "city",
    "zip",
    "postal",
    "siret",
    "email",
    "tel",
    "téléphone",
    "telephone",
    "adresse",
    "address",
)

# Unités usuelles (abrégées) apparaissant juste après la quantité.
_UNITS = (
    "u",
    "unité",
    "unite",
    "pc",
    "pcs",
    "pce",
    "pièce",
    "piece",
    "kg",
    "g",
    "l",
    "m",
    "m²",
    "m2",
    "m3",
    "ml",
    "h",
    "hre",
    "hres",
    "hr",
    "heure",
    "heures",
    "boîte",
    "boite",
    "carton",
    "cartons",
    "sac",
    "sachet",
    "lot",
    "forfait",
    "jour",
    "jours",
)

_PERCENT_RE = re.compile(r"(\d{1,3}(?:[,.]\d{1,2})?)\s*%")
_PRODUCT_REF_RE = re.compile(r"^([A-Za-z]{1,6}[-_/]\d{2,}[A-Za-z0-9\-_/]*)\b")


class InvoiceLineParser:
    """Parse les lignes de facture depuis les lignes de texte OCR."""

    def parse(self, lines: list[str]) -> list[OcrLineItem]:
        """Retourne les lignes de facture reconnues (numérotées à partir de 1)."""
        items: list[OcrLineItem] = []
        for line in lines:
            if not self._is_item_line(line):
                continue
            item = self._parse_line(line, len(items) + 1)
            if item is not None:
                items.append(item)
        return items

    # --- Filtrage ---------------------------------------------------------------

    def _is_item_line(self, line: str) -> bool:
        """Indique si une ligne ressemble à une ligne de facture."""
        lowered = line.lower()
        if any(keyword in lowered for keyword in _TOTAL_KEYWORDS):
            return False
        if any(keyword in lowered for keyword in _HEADER_KEYWORDS):
            return False

        amounts = find_amounts(line)
        if len(amounts) >= 2:
            return True
        if len(amounts) == 1 and amounts[0] != amounts[0].to_integral_value():
            # Montant unique avec décimales : ligne plausible, sauf si le texte
            # ressemble à une adresse ou à un libellé.
            if not any(keyword in lowered for keyword in _ADDRESS_KEYWORDS):
                return True
        return False

    # --- Parsing ----------------------------------------------------------------

    def _parse_line(self, line: str, line_number: int) -> OcrLineItem | None:
        """Décompose une ligne en quantité, prix, montant, description, unité."""
        spans = find_amounts_with_spans(line)
        if not spans:
            return None
        amounts = [value for _, _, value in spans]

        percentage = _PERCENT_RE.search(line)
        tax_rate = normalize_amount(percentage.group(1)) if percentage else None

        if len(amounts) >= 3:
            quantity, unit_price, amount = amounts[0], amounts[-2], amounts[-1]
        elif len(amounts) == 2:
            quantity, unit_price, amount = None, amounts[0], amounts[-1]
        else:
            quantity = unit_price = None
            amount = amounts[0]

        unit = self._extract_unit(line, spans, quantity)
        description, product_ref = self._split_description(
            self._strip_amount_tokens(line, spans), unit
        )

        return OcrLineItem(
            line_number=line_number,
            description=description,
            product_ref=product_ref,
            quantity=quantity,
            unit=unit,
            unit_price=unit_price,
            tax_rate=tax_rate,
            amount=amount,
        )

    @staticmethod
    def _extract_unit(
        line: str, spans: list[tuple[int, int, object]], quantity
    ) -> str | None:
        """Retourne l'unité placée juste après la quantité (``None`` sinon)."""
        if quantity is None or not spans:
            return None
        tail = line[spans[0][1]:].strip(" :;|,.")
        match = re.match(r"^([^\s\d:;|,.]{1,8})", tail)
        if match and match.group(1).lower() in _UNITS:
            return match.group(1)
        return None

    @staticmethod
    def _strip_amount_tokens(
        line: str, spans: list[tuple[int, int, object]]
    ) -> str:
        """Retire les montants et les pourcentages d'une ligne."""
        parts: list[str] = []
        last = 0
        for start, end, _ in spans:
            parts.append(line[last:start])
            last = end
        parts.append(line[last:])
        stripped = "".join(parts)
        stripped = _PERCENT_RE.sub("", stripped)
        return clean_text(stripped)

    @staticmethod
    def _split_description(
        stripped: str, unit: str | None
    ) -> tuple[str, str | None]:
        """Sépare la référence produit de la désignation."""
        text = stripped
        if unit and text.lower().startswith(unit.lower()):
            text = text[len(unit):].strip()
        product_ref: str | None = None
        match = _PRODUCT_REF_RE.match(text)
        if match:
            product_ref = match.group(1)
            text = text[match.end():].strip()
        description = clean_text(text)
        if not description:
            description = product_ref or "(ligne non libellée)"
        return description, product_ref
