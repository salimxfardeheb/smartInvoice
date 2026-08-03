"""Génère des jeux de données d'exemple pour la démo / validation OCR.

Produit des factures *fictives* au format image (PNG/JPG) reconnues par le
pipeline, dans plusieurs langues et devises, et une variante PDF (chaque image
étant embarquée dans une page PDF valide). Ces fichiers sont des jeux de
données d'exemple dans ``datasets/`` — générés, non considérés comme des
sources de vérité.

Usage :
    python datasets/generate_samples.py
"""

from __future__ import annotations

import io
import os

from PIL import Image, ImageDraw, ImageFont

OUT = os.path.dirname(os.path.abspath(__file__))
W, H = 1240, 1754  # ~ A4 @150dpi

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
    "Désignation            Qté     PU         Montant",
    "Câble HDMI 2m          8       8,50 €     68,00 €",
    "Écran LED 27\"         2       149,00 €   298,00 €",
    "XLR-500 Câble audio    3       12,00 €    36,00 €",
    "",
    "Livraison                          5,90 €",
    "Total HT                           402,90 €",
    "TVA 20%                            80,58 €",
    "Total TTC                          483,48 €",
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


def _font(size: int) -> ImageFont.ImageFont:
    return ImageFont.load_default(size=size)


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


def _jpeg_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def to_pdf(images: list[Image.Image]) -> bytes:
    """Embarque des images JPEG dans un PDF valide (une page par image).

    PDF minimal (flux images DCTDecode) lisible par pypdfium2 via
    :class:`app.ocr.document.DocumentLoader`.
    """
    chunks: list[bytes] = [b"%PDF-1.4\n"]
    total_objects = 2 + 3 * len(images)
    offsets: list[int] = [0] * (total_objects + 1)

    def emit(number: int, body: bytes) -> None:
        offsets[number] = len(b"".join(chunks))
        chunks.append(f"{number} 0 obj\n".encode())
        chunks.append(body)
        chunks.append(b"\nendobj\n")

    emit(1, b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = [f"{3 + i * 3} 0 R" for i in range(len(images))]
    emit(
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
        emit(
            page_no,
            (
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] "
                b"/Resources << /XObject << /Im0 %d 0 R >> >> /Contents %d 0 R >>"
            )
            % (pw, ph, image_no, stream_no),
        )
        emit(
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
        emit(stream_no, b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream")

    xref_offset = len(b"".join(chunks))
    chunks.append(b"xref\n0 %d\n" % (total_objects + 1))
    chunks.append(b"0000000000 65535 f \n")
    for n in range(1, total_objects + 1):
        chunks.append(b"%010d 00000 n \n" % offsets[n])
    chunks.append(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (total_objects + 1, xref_offset))
    return b"".join(chunks)


def main() -> None:
    img_fr = _make_page(FR_LINES)
    img_fr.save(os.path.join(OUT, "fr_invoice.png"), format="PNG")
    img_en = _make_page(EN_LINES)
    img_en.save(os.path.join(OUT, "en_invoice.jpg"), format="JPEG", quality=90)
    img_usd = _make_page(USD_LINES)
    img_usd.save(os.path.join(OUT, "multi_currency_invoice.jpg"), format="JPEG", quality=90)
    img_annex = _make_page(ANNEX_LINES, page_label="Page 2/2")
    with open(os.path.join(OUT, "fr_invoice_multi.pdf"), "wb") as handle:
        handle.write(to_pdf([img_fr, img_annex]))
    with open(os.path.join(OUT, "en_invoice.pdf"), "wb") as handle:
        handle.write(to_pdf([img_en]))
    print("Generated datasets in", OUT)


if __name__ == "__main__":
    main()