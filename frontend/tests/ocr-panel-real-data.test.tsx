/**
 * Rendu du panneau OCR à partir d'un résultat **réel** du pipeline.
 *
 * La charge utile ci-dessous est celle produite par le vrai moteur PaddleOCR
 * sur `datasets/fr_invoice.png` (parcours complet : dépôt → /process → tâche →
 * « À vérifier »). Elle sert de garde-fou : l'interface doit afficher les
 * champs, les montants, les lignes et le score tels que le backend les produit
 * désormais, y compris les valeurs `null` (champs non localisés).
 */

import { render, screen, within } from "@testing-library/react";
import { OcrPanel } from "@/components/invoices/OcrPanel";
import type { Invoice, OcrExtractedData } from "@/types";
import { makeInvoice } from "./fixtures";

jest.mock("@/lib/api-client", () => ({
  api: { processInvoice: jest.fn(), retryInvoice: jest.fn(), getTask: jest.fn() },
}));

jest.mock("@/hooks/useTask", () => ({
  useTaskPolling: () => ({ task: null, running: false }),
}));

/** Sortie réelle de l'OCR sur datasets/fr_invoice.png (score global 0,994). */
const REAL_EXTRACTED_DATA: OcrExtractedData = {
  general: {
    supplier_name: null,
    supplier_address: null,
    invoice_number: "FAC-2026-0042",
    issue_date: "2026-03-15",
    due_date: "2026-04-15",
    currency: "EUR",
    purchase_order_reference: "PO-2026-0123",
    supplier_reference: null,
  },
  financial: {
    total_excl_tax: "397.90",
    tax_amount: "79.58",
    total_incl_tax: "477.48",
    discount: "10.00",
    shipping_fees: "5.90",
  },
  lines: [
    {
      line_number: 1,
      description: "Câble HDMI 2m",
      product_ref: null,
      quantity: "8",
      unit: "u",
      unit_price: "8.50",
      tax_rate: null,
      discount: null,
      amount: "68.00",
    },
    {
      line_number: 2,
      description: 'Écran LED " u',
      product_ref: null,
      quantity: "27",
      unit: null,
      unit_price: "149.00",
      tax_rate: null,
      discount: null,
      amount: "298.00",
    },
    {
      line_number: 3,
      description: "Câble audio",
      product_ref: "XLR-500",
      quantity: "3",
      unit: "u",
      unit_price: "12.00",
      tax_rate: null,
      discount: null,
      amount: "36.00",
    },
  ],
};

function realInvoice(overrides: Partial<Invoice> = {}): Invoice {
  return makeInvoice({
    invoice_number: "FAC-2026-0042",
    status: "À vérifier",
    ocr_confidence_score: 0.994,
    total_excl_tax: "397.90",
    tax_amount: "79.58",
    total_incl_tax: "477.48",
    discount: "10.00",
    shipping_fees: "5.90",
    extracted_data: REAL_EXTRACTED_DATA,
    ...overrides,
  });
}

describe("OcrPanel avec des données OCR réelles", () => {
  test("affiche les champs généraux extraits", () => {
    render(<OcrPanel invoice={realInvoice()} onProcessed={jest.fn()} />);

    expect(screen.getByText("FAC-2026-0042")).toBeInTheDocument();
    expect(screen.getByText("2026-03-15")).toBeInTheDocument();
    expect(screen.getByText("2026-04-15")).toBeInTheDocument();
    expect(screen.getByText("PO-2026-0123")).toBeInTheDocument();
    expect(screen.getByText("EUR")).toBeInTheDocument();
  });

  test("affiche « — » pour les champs non localisés par l'extracteur", () => {
    render(<OcrPanel invoice={realInvoice()} onProcessed={jest.fn()} />);

    const supplier = screen.getByText("Fournisseur").closest("div");
    expect(within(supplier as HTMLElement).getByText("—")).toBeInTheDocument();
  });

  test("affiche les montants, TVA comprise", () => {
    render(<OcrPanel invoice={realInvoice()} onProcessed={jest.fn()} />);

    const amounts = screen.getByText("Montants").closest("div") as HTMLElement;
    const rendered = amounts.textContent ?? "";
    for (const value of ["397,90", "79,58", "477,48", "10,00", "5,90"]) {
      expect(rendered).toContain(value);
    }
  });

  test("affiche les trois lignes d'articles extraites", () => {
    render(<OcrPanel invoice={realInvoice()} onProcessed={jest.fn()} />);

    expect(screen.getByText("Câble HDMI 2m")).toBeInTheDocument();
    expect(screen.getByText("Câble audio")).toBeInTheDocument();
    expect(screen.getByText("XLR-500")).toBeInTheDocument();
    expect(screen.queryByText("Aucune ligne extraite.")).not.toBeInTheDocument();
  });

  test("affiche le score OCR", () => {
    render(<OcrPanel invoice={realInvoice()} onProcessed={jest.fn()} />);

    expect(screen.getByText(/Score OCR/)).toBeInTheDocument();
  });

  test("signale l'absence de données tant que l'OCR n'a pas tourné", () => {
    render(
      <OcrPanel
        invoice={realInvoice({ status: "Déposée", extracted_data: null })}
        onProcessed={jest.fn()}
      />,
    );

    expect(
      screen.getByText(/Aucune donnée extraite pour le moment/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Lancer l'analyse OCR" }),
    ).toBeInTheDocument();
  });
});
