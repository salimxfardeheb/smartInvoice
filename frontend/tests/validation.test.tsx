/** Tests de l'écran de validation (correction, validation, rejet). */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ValidationPanel } from "@/components/invoices/ValidationPanel";
import { api } from "@/lib/api-client";
import { makeInvoice } from "./fixtures";

jest.mock("@/lib/api-client", () => ({
  api: {
    validateInvoice: jest.fn(),
    rejectInvoice: jest.fn(),
    correctInvoice: jest.fn(),
    createVendorBill: jest.fn(),
  },
}));

const mockedApi = api as jest.Mocked<typeof api>;

describe("ValidationPanel", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test("valide une facture « À vérifier » et notifie le parent", async () => {
    const user = userEvent.setup();
    const validated = makeInvoice({ status: "Validée" });
    mockedApi.validateInvoice.mockResolvedValue(validated);
    const onUpdated = jest.fn();

    render(<ValidationPanel invoice={makeInvoice()} onUpdated={onUpdated} />);
    await user.click(screen.getByRole("button", { name: "Valider la facture" }));

    await waitFor(() => {
      expect(mockedApi.validateInvoice).toHaveBeenCalledWith(1);
      expect(onUpdated).toHaveBeenCalledWith(validated);
    });
  });

  test("rejette avec un motif obligatoire via la modale", async () => {
    const user = userEvent.setup();
    const rejected = makeInvoice({ status: "Rejetée", rejection_reason: "TVA erronée." });
    mockedApi.rejectInvoice.mockResolvedValue(rejected);
    const onUpdated = jest.fn();

    render(<ValidationPanel invoice={makeInvoice()} onUpdated={onUpdated} />);

    await user.click(screen.getByRole("button", { name: "Rejeter la facture" }));
    expect(screen.getByRole("dialog", { name: "Rejeter la facture" })).toBeInTheDocument();

    // Le bouton reste désactivé tant que le motif est vide.
    const confirm = screen.getByRole("button", { name: "Confirmer le rejet" });
    expect(confirm).toBeDisabled();

    await user.type(screen.getByLabelText("Motif obligatoire"), "TVA erronée.");
    await user.click(confirm);

    await waitFor(() => {
      expect(mockedApi.rejectInvoice).toHaveBeenCalledWith(1, "TVA erronée.");
      expect(onUpdated).toHaveBeenCalledWith(rejected);
    });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  test("enregistre les corrections modifiées", async () => {
    const user = userEvent.setup();
    const corrected = makeInvoice({ currency: "USD" });
    mockedApi.correctInvoice.mockResolvedValue(corrected);

    render(<ValidationPanel invoice={makeInvoice()} onUpdated={jest.fn()} />);

    const currency = screen.getByLabelText("Devise");
    await user.clear(currency);
    await user.type(currency, "USD");
    await user.click(screen.getByRole("button", { name: "Enregistrer les corrections" }));

    await waitFor(() => {
      expect(mockedApi.correctInvoice).toHaveBeenCalledWith(
        1,
        expect.objectContaining({ currency: "USD" }),
      );
    });
  });

  test("désactive la validation et propose la Vendor Bill une fois validée", () => {
    render(<ValidationPanel invoice={makeInvoice({ status: "Validée" })} onUpdated={jest.fn()} />);
    expect(screen.getByRole("button", { name: "Valider la facture" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Créer la Vendor Bill Odoo" })).toBeInTheDocument();
  });
});
