"""Génère des jeux de données d'exemple pour la démo / validation OCR.

Produit des factures *fictives* au format image (PNG/JPG) reconnues par le
pipeline, dans plusieurs langues et devises, une variante PDF « scannée »
(chaque image étant embarquée dans une page PDF valide) et une variante PDF
« numérique » (texte vectoriel, sans passer par une image). Ces fichiers sont
des jeux de données d'exemple dans ``datasets/`` — générés, non considérés
comme des sources de vérité.

La police est choisie parmi les polices TrueType du système et **vérifiée**
pour la couverture des caractères accentués : la police par défaut de Pillow
(Aileron) ne contient pas « é », « è », « à », « ç » et rendait des carrés
« tofu » que l'OCR lisait « Numøro », « Dsignation », « chance ». Les libellés
français étaient alors introuvables par l'extracteur.

Usage :
    python datasets/generate_samples.py
"""

from __future__ import annotations

import io
import os
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = os.path.dirname(os.path.abspath(__file__))
W, H = 1240, 1754  # ~ A4 @150dpi

# Polices TrueType candidates (macOS, Linux), essayées dans l'ordre.
_FONT_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/Library/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "DejaVuSans.ttf",
)

# Caractères accentués que la police doit savoir rendre.
_ACCENTS = "éèêàçÉÀÈ"

FR_LINES = [
    "ACME SAS",
    "12 rue des Lilas",
    "75011 Paris",
    "",
    "FACTURE",
    "Numéro de facture : FAC-2026-0042",
    "Date d'émission : 15/03/2026",
    "Échéance : 15/04/2026",
    "Bon de commande : PO-2026-0123",
    "",
    "Désignation            Qté   U    PU          Montant",
    "Câble HDMI 2m          8     u    8,50 €      68,00 €",
    "Écran LED 27\"          2     u    149,00 €    298,00 €",
    "XLR-500 Câble audio    3     u    12,00 €     36,00 €",
    "",
    "Remise commerciale                            10,00 €",
    "Livraison                                      5,90 €",
    "Total HT                                     397,90 €",
    "TVA 20%                                       79,58 €",
    "Total TTC                                    477,48 €",
]

# Variante « fournisseur explicitement libellé » : l'extraction du nom et de
# l'adresse du fournisseur est fondée sur les libellés (voir FieldExtractor).
FR_DIGITAL_LINES = [
    "FACTURE",
    "",
    "Fournisseur : NORDTEC INDUSTRIE SARL",
    "48 avenue de la Gare",
    "69003 Lyon",
    "",
    "Numéro de facture : FAC-2026-0188",
    "Date d'émission : 02/04/2026",
    "Échéance : 02/05/2026",
    "Bon de commande : PO-2026-0456",
    "Référence fournisseur : NT-CLI-2291",
    "",
    "Désignation             Qté   U    PU          Montant",
    "Disque SSD 1 To         4     u    72,00 €     288,00 €",
    "RJ45-120 Cordon 3m     12     u    4,25 €       51,00 €",
    "Onduleur 650 VA         1     u    119,00 €    119,00 €",
    "",
    "Remise commerciale                             8,00 €",
    "Frais de port                                 14,50 €",
    "Total HT                                     464,50 €",
    "TVA 20%                                       92,90 €",
    "Total TTC                                    557,40 €",
]

EN_LINES = [
    "Global Supply Corp.",
    "55 Market Street",
    "San Francisco, CA 94105",
    "",
    "INVOICE",
    "Invoice number : INV-9012",
    "Issue date : 2026-03-15",
    "Due date : 2026-04-15",
    "Order reference : PO-4431",
    "",
    "Item                     Qty    Unit Price    Amount",
    "Industrial cable 10m     5      12.50         62.50",
    "HDMI adapter            10      3.25          32.50",
    "IDR-700 Router           2      89.00         178.00",
    "",
    "Shipping                             9.99",
    "Subtotal                            273.00",
    "VAT 5%                               13.65",
    "Total                               $286.65",
]

USD_LINES = [
    "Acme Trading Ltd.",
    "Unit 4, Harbor Road",
    "Dublin, Ireland",
    "",
    "INVOICE No. US-7781",
    "Date: 2026-07-01",
    "Terms: Net 30",
    "",
    "Product             Qty     Price       Total",
    "Wrench set 12pcs    4       $22.50      $90.00",
    "Spanner PX-3        6       $7.40       $44.40",
    "",
    "Shipping                        $12.00",
    "Total                           $146.40",
]

ANNEX_LINES = [
    "ANNEXE 1 - CONDITIONS GENERALES DE VENTE",
    "Le retard de paiement entraîne l'application de pénalités.",
    "Le droit applicable est le droit français.",
    "Réserve de propriété jusqu'au paiement intégral.",
]


def _supports_accents(font: ImageFont.FreeTypeFont) -> bool:
    """Indique si la police rend réellement les caractères accentués.

    Un glyphe absent est rendu par le glyphe ``.notdef`` (un carré) : on le
    reconnaît en le comparant au rendu d'un caractère de la zone privée, absent
    de toute police par construction.
    """
    def render(char: str) -> tuple[tuple[int, int], bytes]:
        mask = font.getmask(char, mode="L")
        return mask.size, bytes(mask)

    notdef = render("")
    return all(render(char) != notdef for char in _ACCENTS)


def _resolve_font_path() -> str | None:
    """Retourne le chemin d'une police TrueType couvrant les accents."""
    for path in _FONT_CANDIDATES:
        try:
            font = ImageFont.truetype(path, 30)
        except OSError:
            continue
        if _supports_accents(font):
            return path
    return None


_FONT_PATH = _resolve_font_path()
_FONT_CACHE: dict[int, ImageFont.FreeTypeFont] = {}


def _font(size: int) -> ImageFont.FreeTypeFont:
    """Police de rendu à la taille demandée (mise en cache)."""
    if size not in _FONT_CACHE:
        if _FONT_PATH is None:  # pragma: no cover - dépend du système
            _FONT_CACHE[size] = ImageFont.load_default(size=size)
        else:
            _FONT_CACHE[size] = ImageFont.truetype(_FONT_PATH, size)
    return _FONT_CACHE[size]


def _make_page(text_lines: list[str], page_label: str | None = None) -> Image.Image:
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)
    y = 60
    for line in text_lines:
        size = 36 if line.startswith(("FACTURE", "INVOICE", "ANNEXE")) else 30
        draw.text((60, y), line, fill="black", font=_font(size))
        y += size + 16
    if page_label:
        draw.text((W - 240, H - 80), page_label, fill="black", font=_font(26))
    return img


def _degrade(image: Image.Image, *, seed: int = 7) -> Image.Image:
    """Simule une numérisation médiocre : inclinaison, flou et bruit."""
    rng = random.Random(seed)
    scanned = image.rotate(0.8, resample=Image.BICUBIC, fillcolor="white")
    scanned = scanned.filter(ImageFilter.GaussianBlur(radius=0.6))
    pixels = scanned.load()
    for y in range(0, scanned.height, 3):
        for x in range(0, scanned.width, 3):
            noise = rng.randint(-28, 12)
            r, g, b = pixels[x, y]
            pixels[x, y] = (
                max(0, min(255, r + noise)),
                max(0, min(255, g + noise)),
                max(0, min(255, b + noise)),
            )
    return scanned


def _jpeg_bytes(img: Image.Image, quality: int = 90) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


class _PdfWriter:
    """Assembleur minimal d'objets PDF (table xref + trailer)."""

    def __init__(self) -> None:
        self._chunks: list[bytes] = [b"%PDF-1.4\n"]
        self._offsets: dict[int, int] = {}

    def emit(self, number: int, body: bytes) -> None:
        self._offsets[number] = len(b"".join(self._chunks))
        self._chunks.append(f"{number} 0 obj\n".encode())
        self._chunks.append(body)
        self._chunks.append(b"\nendobj\n")

    def finish(self, total_objects: int, root: int = 1) -> bytes:
        xref_offset = len(b"".join(self._chunks))
        self._chunks.append(b"xref\n0 %d\n" % (total_objects + 1))
        self._chunks.append(b"0000000000 65535 f \n")
        for number in range(1, total_objects + 1):
            self._chunks.append(b"%010d 00000 n \n" % self._offsets.get(number, 0))
        self._chunks.append(
            b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % (total_objects + 1, root, xref_offset)
        )
        return b"".join(self._chunks)


def to_pdf(images: list[Image.Image]) -> bytes:
    """Embarque des images JPEG dans un PDF valide (une page par image).

    PDF minimal (flux images DCTDecode) lisible par pypdfium2 via
    :class:`app.ocr.document.DocumentLoader`. C'est la forme d'un document
    *scanné* : le PDF ne contient aucun texte, seulement des pixels.
    """
    writer = _PdfWriter()
    total_objects = 2 + 3 * len(images)

    writer.emit(1, b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = [f"{3 + i * 3} 0 R" for i in range(len(images))]
    writer.emit(
        2,
        ("<< /Type /Pages /Kids [%s] /Count %d >>" % (" ".join(kids), len(images))).encode(),
    )

    for i, image in enumerate(images):
        jpeg = _jpeg_bytes(image)
        iw, ih = image.size
        pw, ph = int(iw / 150 * 72), int(ih / 150 * 72)
        page_no = 3 + i * 3
        image_no = 4 + i * 3
        stream_no = 5 + i * 3
        writer.emit(
            page_no,
            (
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] "
                b"/Resources << /XObject << /Im0 %d 0 R >> >> /Contents %d 0 R >>"
            )
            % (pw, ph, image_no, stream_no),
        )
        writer.emit(
            image_no,
            (
                b"<< /Type /XObject /Subtype /Image /Width %d /Height %d "
                b"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode "
                b"/Length %d >>\nstream\n"
            )
            % (iw, ih, len(jpeg))
            + jpeg
            + b"\nendstream",
        )
        content = b"q %d 0 0 %d 0 0 cm /Im0 Do Q" % (pw, ph)
        writer.emit(
            stream_no,
            b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
        )

    return writer.finish(total_objects)


def _escape_pdf_text(text: str) -> bytes:
    """Encode un texte pour un littéral PDF (/WinAnsiEncoding)."""
    raw = text.encode("cp1252", errors="replace")
    for char, replacement in ((b"\\", b"\\\\"), (b"(", b"\\("), (b")", b"\\)")):
        raw = raw.replace(char, replacement)
    return raw


def to_text_pdf(text_lines: list[str]) -> bytes:
    """Produit un PDF *numérique* : le texte est vectoriel, pas une image.

    Le pipeline le rastérise malgré tout (``DocumentLoader``), mais le rendu
    reste net à n'importe quelle résolution, contrairement à un scan.
    """
    page_w, page_h = 595, 842  # A4 en points
    parts: list[bytes] = []
    y = page_h - 60
    for line in text_lines:
        if line:
            size = 16 if line.startswith(("FACTURE", "INVOICE")) else 11
            parts.append(
                b"BT /F1 %d Tf %d %d Td (%s) Tj ET\n"
                % (size, 50, y, _escape_pdf_text(line))
            )
        y -= 26

    content = b"".join(parts)
    writer = _PdfWriter()
    writer.emit(1, b"<< /Type /Catalog /Pages 2 0 R >>")
    writer.emit(2, b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    writer.emit(
        3,
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>"
        % (page_w, page_h),
    )
    writer.emit(
        4,
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"endstream",
    )
    writer.emit(
        5,
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
        b"/Encoding /WinAnsiEncoding >>",
    )
    return writer.finish(5)


def main() -> None:
    if _FONT_PATH is None:  # pragma: no cover - dépend du système
        print(
            "ATTENTION : aucune police TrueType accentuée trouvée, repli sur la "
            "police par défaut de Pillow — les accents seront illisibles."
        )
    else:
        print("Police utilisée :", _FONT_PATH)

    img_fr = _make_page(FR_LINES)
    img_fr.save(os.path.join(OUT, "fr_invoice.png"), format="PNG")
    img_en = _make_page(EN_LINES)
    img_en.save(os.path.join(OUT, "en_invoice.jpg"), format="JPEG", quality=90)
    img_usd = _make_page(USD_LINES)
    img_usd.save(os.path.join(OUT, "multi_currency_invoice.jpg"), format="JPEG", quality=90)

    # Document dégradé : scan incliné, flouté et bruité (cas difficile).
    with open(os.path.join(OUT, "fr_invoice_scan.jpg"), "wb") as handle:
        handle.write(_jpeg_bytes(_degrade(img_fr), quality=60))

    img_annex = _make_page(ANNEX_LINES, page_label="Page 2/2")
    with open(os.path.join(OUT, "fr_invoice_multi.pdf"), "wb") as handle:
        handle.write(to_pdf([img_fr, img_annex]))
    with open(os.path.join(OUT, "en_invoice.pdf"), "wb") as handle:
        handle.write(to_pdf([img_en]))
    with open(os.path.join(OUT, "fr_invoice_digital.pdf"), "wb") as handle:
        handle.write(to_text_pdf(FR_DIGITAL_LINES))
    print("Generated datasets in", OUT)


if __name__ == "__main__":
    main()
