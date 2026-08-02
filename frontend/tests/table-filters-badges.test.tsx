/** Tests des composants de table, filtres et badges. */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { InvoiceTable } from "@/components/invoices/InvoiceTable";
import { InvoiceFilters } from "@/components/invoices/InvoiceFilters";
import { StatusBadge, ScoreBadge } from "@/components/ui/badges";
import { makeInvoice } from "./fixtures";

describe("InvoiceTable", () => {
  test("affiche les factures et lie chaque numéro à sa vue OCR", () => {
    render(<InvoiceTable invoices={[makeInvoice(), makeInvoice({ id: 2, invoice_number: "FAC-2" })]} />);

    expect(screen.getByText("FAC-2026-001")).toBeInTheDocument();
    expect(screen.getByText("FAC-2")).toBeInTheDocument();
    expect(screen.getAllByText("ACME SAS")).toHaveLength(2);

    const link = screen.getByRole("link", { name: "FAC-2026-001" });
    expect(link).toHaveAttribute("href", "/invoices/1/ocr");
  });

  test("affiche un état vide quand il n'y a aucune facture", () => {
    render(<InvoiceTable invoices={[]} />);
    expect(screen.getByText("Aucune facture trouvée")).toBeInTheDocument();
  });
});

describe("InvoiceFilters", () => {
  test("remonte le changement de statut et réinitialise", async () => {
    const user = userEvent.setup();
    const onChange = jest.fn();
    render(<InvoiceFilters filters={{}} suppliers={[{ id: 42, name: "ACME SAS" }]} onChange={onChange} />);

    await user.selectOptions(screen.getByLabelText("Statut"), "Rejetée");
    expect(onChange).toHaveBeenLastCalledWith({ status: "Rejetée" });

    await user.selectOptions(screen.getByLabelText("Fournisseur"), "42");
    expect(onChange).toHaveBeenLastCalledWith({ supplier_id: 42 });

    await user.click(screen.getByRole("button", { name: "Réinitialiser les filtres" }));
    expect(onChange).toHaveBeenLastCalledWith({});
  });
});

describe("badges", () => {
  test("affiche le statut français", () => {
    render(<StatusBadge status="À vérifier" />);
    expect(screen.getByText("À vérifier")).toBeInTheDocument();
  });

  test("convertit un score 0..1 en pourcentage", () => {
    render(<ScoreBadge score={0.92} label="Score OCR" />);
    expect(screen.getByText("92 %")).toBeInTheDocument();
  });

  test("affiche un tiret quand le score est absent", () => {
    render(<ScoreBadge score={null} label="Score" />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});
