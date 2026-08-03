"""Nettoyage et normalisation des données extraites par l'OCR.

Fonctions pures et sans état : nettoyage de texte, normalisation des dates,
des montants, détection de la devise. Elles sont utilisées par l'extracteur
de champs et le parseur de lignes.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation

# --- Texte ------------------------------------------------------------------

_WHITESPACE_RE = re.compile(r"\s+")


def clean_text(value: str) -> str:
    """Réduit les espaces multiples et supprime les espaces de bordure."""
    return _WHITESPACE_RE.sub(" ", value).strip(" \t\r\n:;,|")


# --- Montants ---------------------------------------------------------------

_CURRENCY_TOKEN_RE = re.compile(
    r"\s*[€$£¥]|\s*\b(?:EUR|USD|GBP|CHF|CAD|MAD|CNY|SEK|NOK|DKK|PLN|DH)\b",
    flags=re.IGNORECASE,
)

# Candidat nombre : groupes de milliers + décimales, signe et parenthèses.
# Les milliers ne sont reconnus qu'avec un séparateur typographique français
# (espace insécable U+00A0 ou espace fine U+202F) ou « , »/« . » : l'espace
# ASCII simple (U+0020) sépare des colonnes (« 1 149,00 » = quantité et prix),
# pas des milliers. Le regard négatif précédent exclut tout nombre accolé à un
# identifiant (« XLR-500 », « FAC-2026-001 ») : il interdit une lettre, un
# chiffre, un point ou un trait d'union juste avant le nombre. Le regard
# négatif suivant exclut les pourcentages (« 20 % »), les nombres suivis d'une
# lettre ou d'un chiffre (« 2 » dans « 2m ») et les dates numériques
# (« 15/01/2026 », « 15.02.2026 », « 15-01-2026 »).
_AMOUNT_CANDIDATE_RE = re.compile(
    r"(?<![\w.\-−])\(?(-|−)?("
    r"(?:\d{1,3}(?:[\u00a0\u202f.,]\d{3}){1,}|\d+)"
    r"(?:[,.]\d{1,2})?"
    r"|[,.]\d{1,2})"
    r"\)?(?!(?:\s*%|[A-Za-z0-9]|[./\-−]\d))"
)

# Magnitude maximale d'un montant « plausible » : au-delà, la valeur est
# considérée comme du bruit OCR (numéro de téléphone, identifiant, etc.).
_MAX_AMOUNT = Decimal("1000000000000.00")


def normalize_amount(raw: str) -> Decimal | None:
    """Normalise un montant OCR en ``Decimal``, ou ``None`` si illisible.

    Gère les conventions française (« 1 234,56 », « 1234,56 ») et anglaise
    (« 1,234.56 »), les symboles monétaires, les signes négatifs « - »,
    « − » et les parenthèses « (25,00) ». Un champ non numérique (ou une
    date) retourne ``None``.
    """
    if not raw:
        return None
    s = raw.strip()
    if not s:
        return None

    negative = (
        s.startswith("-")
        or s.startswith("−")
        or (s.startswith("(") and s.endswith(")"))
    )
    s = s.strip("()").lstrip("-−").strip()
    s = _CURRENCY_TOKEN_RE.sub("", s)
    s = s.replace("\u202f", "").replace("\u00a0", "")
    if not s or not re.fullmatch(r"[\d.,\s]+", s):
        return None
    s = s.replace(" ", "")

    dots, commas = s.count("."), s.count(",")
    try:
        if dots == 0 and commas == 0:
            value = Decimal(s)
        elif dots == 0:
            value = _parse_with_separator(s, ",")
        elif commas == 0:
            value = _parse_with_separator(s, ".")
        else:
            value = _parse_with_both(s)
    except InvalidOperation:
        return None

    value = -value if negative else value
    if abs(value) > _MAX_AMOUNT:
        return None
    return value


def _parse_with_separator(s: str, sep: str) -> Decimal:
    """Parse un nombre avec un seul type de séparateur.

    Séparateur décimal si la partie finale a 1-2 chiffres, séparateur de
    milliers (groupes de 3) sinon.
    """
    parts = s.split(sep)
    if len(parts) == 2 and len(parts[1]) in (1, 2):
        return Decimal(f"{parts[0]}.{parts[1]}")
    if len(parts) >= 2 and len(parts[0]) <= 3 and all(
        len(p) == 3 for p in parts[1:]
    ):
        return Decimal("".join(parts))
    raise InvalidOperation(s)


def _parse_with_both(s: str) -> Decimal:
    """Parse un nombre contenant à la fois « , » et « . ».

    Le dernier séparateur rencontré est le séparateur décimal.
    """
    if s.rfind(",") > s.rfind("."):
        integer, decimal = s.rsplit(",", 1)
        if len(decimal) not in (1, 2):
            raise InvalidOperation(s)
        return Decimal(f"{integer.replace('.', '')}.{decimal}")
    integer, decimal = s.rsplit(".", 1)
    if len(decimal) not in (1, 2):
        raise InvalidOperation(s)
    return Decimal(f"{integer.replace(',', '')}.{decimal}")


def find_amounts(text: str) -> list[Decimal]:
    """Retourne les montants normalisés présents dans ``text``, dans l'ordre."""
    return [value for _, _, value in find_amounts_with_spans(text)]


def find_amounts_with_spans(text: str) -> list[tuple[int, int, Decimal]]:
    """Retourne ``(début, fin, valeur)`` des montants de ``text``."""
    out: list[tuple[int, int, Decimal]] = []
    for match in _AMOUNT_CANDIDATE_RE.finditer(text):
        value = normalize_amount(match.group(0))
        if value is not None:
            out.append((match.start(), match.end(), value))
    return out


# --- Dates ------------------------------------------------------------------

_FRENCH_MONTHS: dict[str, int] = {
    "janvier": 1,
    "février": 2,
    "fevrier": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "août": 8,
    "aout": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "décembre": 12,
    "decembre": 12,
}

_DATE_ISO_RE = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")
_DATE_NUMERIC_RE = re.compile(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})")
_DATE_TEXTUAL_RE = re.compile(
    r"(\d{1,2})(?:er|ème|eme)?\s+([a-zàâäéèêëîïôöùûüçœ]+)\s+(\d{4})",
    re.IGNORECASE,
)


def normalize_date(raw: str) -> date | None:
    """Normalise une date OCR en ``date``, ou ``None`` si illisible.

    Formats acceptés : ISO (AAAA-MM-JJ), JJ/MM/AAAA, JJ-MM-AAAA, JJ.MM.AAAA
    et français textuel (« 15 janvier 2026 », « 1er février 2026 »). Les
    dates invalides (ex. 31/02) retournent ``None``.
    """
    if not raw:
        return None
    s = raw.strip().strip(".")
    if not s:
        return None

    match = _DATE_ISO_RE.fullmatch(s)
    if match:
        return _build_date(int(match.group(2)), int(match.group(3)), int(match.group(1)))

    match = _DATE_NUMERIC_RE.fullmatch(s)
    if match:
        day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
        if year < 100:
            year += 2000 if year < 70 else 1900
        return _build_date(month, day, year)

    match = _DATE_TEXTUAL_RE.fullmatch(s)
    if match:
        month = _FRENCH_MONTHS.get(match.group(2).lower())
        if month is None:
            return None
        return _build_date(month, int(match.group(1)), int(match.group(3)))
    return None


def _build_date(month: int, day: int, year: int) -> date | None:
    """Construit une date valide (``None`` si le couple jour/mois est invalide)."""
    try:
        return date(year, month, day)
    except ValueError:
        return None


# --- Devise -----------------------------------------------------------------

_CURRENCY_SYMBOLS: dict[str, str] = {
    "€": "EUR",
    "EUR": "EUR",
    "$": "USD",
    "USD": "USD",
    "US$": "USD",
    "£": "GBP",
    "GBP": "GBP",
    "CHF": "CHF",
    "CAD": "CAD",
    "MAD": "MAD",
    "DH": "MAD",
    "¥": "JPY",
}


def detect_currency(text: str) -> str | None:
    """Détecte la devise d'un texte (premier symbole/libellé rencontré)."""
    lowered = text.lower()
    for symbol, code in _CURRENCY_SYMBOLS.items():
        if symbol.lower() in lowered:
            return code
    return None
