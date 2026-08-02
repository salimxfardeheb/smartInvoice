/** Tests du panneau de matching (appels API mockés). */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MatchingPanel } from "@/components/invoices/MatchingPanel";
import { api } from "@/lib/api-client";
import { makeInvoice, makeMatchingResult } from "./fixtures";

jest.mock("@/lib/api-client", () => ({
  api: {
    matchInvoice: jest.fn(),
  },
}));

const mockedApi = api as jest.Mocked<typeof api>;

describe("MatchingPanel", () => {
  beforeEach(() => {
    mockedApi.matchInvoice.mockReset();
  });

  test("lance le matching puis affiche score, lignes et anomalies", async () => {
    const user = userEvent.setup();
    mockedApi.matchInvoice.mockResolvedValue(makeMatchingResult());
    const onMatched = jest.fn();

    render(<MatchingPanel invoice={makeInvoice()} onMatched={onMatched} />);
    await user.click(screen.getByRole("button", { name: "Lancer le matching" }));

    await waitFor(() => {
      expect(mockedApi.matchInvoice).toHaveBeenCalledWith(1);
      expect(onMatched).toHaveBeenCalled();
    });

    expect(screen.getByText(/Score : 85 %/)).toBeInTheDocument();
    expect(screen.getByText(/BC-2026-010/)).toBeInTheDocument();
    expect(screen.getByText("Câble HDMI 2m")).toBeInTheDocument();
    expect(screen.getByText("+5.0 %")).toBeInTheDocument();
    expect(screen.getByText("Quantité différente du bon de commande.")).toBeInTheDocument();
    expect(screen.getByText("Fournisseur conforme")).toBeInTheDocument();
  });

  test("affiche l'erreur renvoyée par l'API", async () => {
    const user = userEvent.setup();
    mockedApi.matchInvoice.mockRejectedValue(new Error("Fournisseur introuvable."));

    render(<MatchingPanel invoice={makeInvoice()} onMatched={jest.fn()} />);
    await user.click(screen.getByRole("button", { name: "Lancer le matching" }));

    expect(await screen.findByText("Fournisseur introuvable.")).toBeInTheDocument();
  });

  test("affiche le score déjà calculé sur la facture avant de relancer", () => {
    render(<MatchingPanel invoice={makeInvoice({ matching_score: 0.75 })} onMatched={jest.fn()} />);
    expect(screen.getByText(/Score : 75 %/)).toBeInTheDocument();
  });
});
