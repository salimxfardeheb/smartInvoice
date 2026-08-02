"""Extraction des champs généraux et financiers d'une facture.

Travaille sur les lignes de texte *nettoyées* issues de l'OCR. La stratégie
est à base de libellés (français et anglais) : chaque champ est recherché
après son libellé, sur la même ligne ou sur la ligne suivante, puis normalisé
via :mod:`app.ocr.cleaners`. Le parseur de lignes de facture est dans
:mod:`app.ocr.lines`.
"""

from __future__ import annotations

import re

from app.ocr.cleaners import clean_text, detect_currency, find_amounts, normalize_date
from app.ocr.schema import OcrFinancialFields, OcrGeneralFields

# Libellés reconnus (minuscules) pour chaque champ.
_INVOICE_NUMBER_LABELS = (
    "numéro de facture",
    "numero de facture",
    "n° facture",
    "no facture",
    "facture n",
    "invoice number",
    "invoice no",
    "invoice #",
    "n°",
    "nº",
)
_ISSUE_DATE_LABELS = (
    "date d'émission",
    "date d'emission",
    "date emission",
    "émise le",
    "emise le",
    "issue date",
    "invoice date",
)
_DUE_DATE_LABELS = (
    "échéance",
    "echeance",
    "due date",
    "date limite",
    "payment due",
)
_PO_LABELS = (
    "bon de commande",
    "numéro de commande",
    "numero de commande",
    "purchase order",
    "commande n",
    "n° bc",
    "no bc",
    "po number",
)
_SUPPLIER_REF_LABELS = (
    "référence fournisseur",
    "reference fournisseur",
    "votre référence",
    "votre reference",
    "réf. fournisseur",
    "ref fournisseur",
    "our reference",
    "our ref",
)
_SUPPLIER_LABELS = (
    "fournisseur",
    "supplier",
    "vendeur",
    "vendor",
    "émetteur",
    "emetteur",
    "facturé par",
    "facture par",
)

_TOTAL_HT_LABELS = (
    "total ht",
    "sous-total",
    "subtotal",
    "total hors taxe",
    "total hors taxes",
    "total h.t",
)
_TAX_LABELS = ("tva", "taxe", "tax")
_TOTAL_TTC_LABELS = (
    "total ttc",
    "montant total",
    "total à payer",
    "total a payer",
    "grand total",
    "net à payer",
    "net a payer",
    "total",
)
_DISCOUNT_LABELS = ("remise", "discount", "rabais")
_SHIPPING_LABELS = (
    "frais de livraison",
    "frais de port",
    "livraison",
    "shipping",
    "transport",
)

_IDENTIFIER_RE = re.compile(r"[A-Za-z]{0,6}[-_\s/]?\d{2,}[A-Za-z0-9\-_/.]*")
_DATE_IN_TEXT_RE = re.compile(
    r"\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}"
    r"|\d{4}-\d{1,2}-\d{1,2}"
    r"|[0-9]{1,2}(?:er|ème|eme)?\s+[a-zà-ÿ]+\s+\d{4}",
    re.IGNORECASE,
)
_ADDRESS_KEYWORDS = (
    "rue",
    "avenue",
    "bd ",
    "boulevard",
    "place",
    "impasse",
    "chemin",
    "route",
    "cedex",
    "lieu-dit",
    "code postal",
    "street",
    "road",
    "avenue",
    "city",
    "zip",
    "postal",
)


class FieldExtractor:
    """Extrait les champs généraux et financiers à partir des lignes OCR."""

    def extract(
        self, lines: list[str]
    ) -> tuple[OcrGeneralFields, OcrFinancialFields]:
        """Retourne ``(champs_généraux, champs_financiers)``.

        Les champs absents ou illisibles sont ``None``.
        """
        full_text = " ".join(lines)
        supplier_name, supplier_address = self._extract_supplier(lines)
        general = OcrGeneralFields(
            supplier_name=supplier_name,
            supplier_address=supplier_address,
            invoice_number=self._value_after_label(
                lines, _INVOICE_NUMBER_LABELS, self._find_identifier
            ),
            issue_date=self._value_after_label(
                lines, _ISSUE_DATE_LABELS, self._find_date
            ),
            due_date=self._value_after_label(lines, _DUE_DATE_LABELS, self._find_date),
            currency=detect_currency(full_text),
            purchase_order_reference=self._value_after_label(
                lines, _PO_LABELS, self._find_identifier
            ),
            supplier_reference=self._value_after_label(
                lines, _SUPPLIER_REF_LABELS, self._find_identifier
            ),
        )
        financial = self._extract_financial(lines)
        return general, financial

    # --- Helpers génériques ---------------------------------------------------

    def _value_after_label(
        self, lines: list[str], labels: tuple[str, ...], getter
    ):
        """Valeur capturée après un libellé, même ligne ou ligne suivante."""
        for i, line in enumerate(lines):
            lowered = line.lower()
            for label in labels:
                pos = lowered.find(label)
                if pos == -1:
                    continue
                rest = line[pos + len(label):].strip(" :;–—|,.")
                if rest:
                    value = getter(rest)
                    if value is not None:
                        return value
                if i + 1 < len(lines):
                    value = getter(lines[i + 1])
                    if value is not None:
                        return value
        return None

    @staticmethod
    def _find_identifier(text: str) -> str | None:
        """Premier identifiant façon « FAC-2026-001 » trouvé dans ``text``."""
        match = _IDENTIFIER_RE.search(text)
        return clean_text(match.group(0)) if match else None

    @staticmethod
    def _find_date(text: str):
        """Première date trouvée dans ``text``, normalisée (``None`` sinon)."""
        match = _DATE_IN_TEXT_RE.search(text)
        return normalize_date(match.group(0)) if match else None

    # --- Fournisseur & adresse -------------------------------------------------

    def _extract_supplier(self, lines: list[str]) -> tuple[str | None, str | None]:
        """Retourne ``(nom, adresse)`` du fournisseur (``None`` si absent)."""
        name: str | None = None
        address: str | None = None
        name_on_next = False
        for i, line in enumerate(lines):
            lowered = line.lower()
            if any(lb in lowered for lb in _SUPPLIER_REF_LABELS):
                continue  # « Réf fournisseur : » n'est pas le nom
            matched = next((lb for lb in _SUPPLIER_LABELS if lb in lowered), None)
            if not matched:
                continue
            after = line[lowered.find(matched) + len(matched):].strip(" :;–—|,.")
            if after and not self._looks_like_label(after):
                name = clean_text(after)
            elif i + 1 < len(lines):
                name = clean_text(lines[i + 1])
                name_on_next = True
            if name:
                address = self._collect_address(
                    lines, i + (2 if name_on_next else 1)
                )
            break
        return name, address

    @staticmethod
    def _collect_address(lines: list[str], start: int) -> str | None:
        """Rassemble les lignes d'adresse suivant le nom du fournisseur."""
        collected: list[str] = []
        for j in range(start, min(len(lines), start + 3)):
            candidate = clean_text(lines[j])
            if not candidate or FieldExtractor._looks_like_label(candidate):
                break
            if FieldExtractor._looks_like_address(candidate):
                collected.append(candidate)
            elif collected:
                break
        return ", ".join(collected) if collected else None

    @staticmethod
    def _looks_like_label(text: str) -> bool:
        """Indique si un texte ressemble à un libellé (pas une donnée)."""
        lowered = text.lower()
        if ":" in text and not any(ch.isdigit() for ch in text):
            return True
        return any(
            lb in lowered
            for lb in (
                "adresse",
                "siret",
                "tva",
                "tel",
                "email",
                "fax",
                "date",
                "réf",
                "ref ",
                "client",
                "téléphone",
                "telephone",
            )
        )

    @staticmethod
    def _looks_like_address(text: str) -> bool:
        """Indique si un texte ressemble à une adresse postale."""
        lowered = text.lower()
        if any(keyword in lowered for keyword in _ADDRESS_KEYWORDS):
            return True
        return bool(re.search(r"\d", text))

    # --- Champs financiers ------------------------------------------------------

    def _extract_financial(self, lines: list[str]) -> OcrFinancialFields:
        """Extrait les totaux (HT, TVA, TTC, remise, livraison)."""
        ht = tax = ttc = discount = shipping = None
        for i, line in enumerate(lines):
            lowered = line.lower()
            amounts = find_amounts(line)

            if ht is None and any(lb in lowered for lb in _TOTAL_HT_LABELS):
                ht = self._amount_or_next(line, lines, i, amounts)
            elif discount is None and any(lb in lowered for lb in _DISCOUNT_LABELS):
                discount = self._amount_or_next(line, lines, i, amounts)
            elif shipping is None and any(lb in lowered for lb in _SHIPPING_LABELS):
                shipping = self._amount_or_next(line, lines, i, amounts)
            elif tax is None and any(lb in lowered for lb in _TAX_LABELS):
                tax = self._amount_or_next(line, lines, i, amounts)
            elif ttc is None and any(lb in lowered for lb in _TOTAL_TTC_LABELS):
                if not any(lb in lowered for lb in _TOTAL_HT_LABELS):
                    ttc = self._amount_or_next(line, lines, i, amounts)

        return OcrFinancialFields(
            total_excl_tax=ht,
            tax_amount=tax,
            total_incl_tax=ttc,
            discount=discount,
            shipping_fees=shipping,
        )

    @staticmethod
    def _amount_or_next(line, lines, i, amounts):
        """Dernier montant de la ligne, ou de la ligne suivante (avec prudence)."""
        if amounts:
            return amounts[-1]
        # Une ligne qui contient déjà un nombre (ex. « TVA 20% : ») mais aucun
        # montant exploitable ne doit pas rabattre sur la ligne suivante.
        if any(ch.isdigit() for ch in line):
            return None
        for j in range(i + 1, min(len(lines), i + 4)):
            next_amounts = find_amounts(lines[j])
            if next_amounts:
                return next_amounts[-1]
        return None
