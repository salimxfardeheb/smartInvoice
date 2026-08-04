/** Tests du panneau de synchronisation Odoo. */

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { OdooSyncPanel } from "@/components/odoo/OdooSyncPanel";
import { api } from "@/lib/api-client";
import type { SupplierRead, PurchaseOrderRead } from "@/types";

jest.mock("@/lib/api-client", () => ({
  api: {
    syncSuppliers: jest.fn(),
    syncPurchaseOrders: jest.fn(),
  },
}));

const mockedApi = api as jest.Mocked<typeof api>;

const supplier: SupplierRead = {
  id: 1,
  odoo_id: 1001,
  name: "ACME SAS",
  vat: "FR12345678901",
  email: "contact@acme.fr",
  phone: null,
  address: null,
  is_active: true,
};

const purchaseOrder: PurchaseOrderRead = {
  id: 2,
  odoo_id: 2002,
  reference: "BC-2026-010",
  supplier_id: 1,
  state: "confirmed",
  currency: "EUR",
  date_order: "2026-01-10",
  total_amount: "1200.00",
  supplier,
};

describe("OdooSyncPanel", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test("synchronise un fournisseur et affiche le résultat", async () => {
    const user = userEvent.setup();
    mockedApi.syncSuppliers.mockResolvedValue({ synced: true, supplier });

    render(<OdooSyncPanel />);
    const supplierForm = screen.getByLabelText("Nom du fournisseur").closest("form");
    await user.type(screen.getByLabelText("Nom du fournisseur"), "ACME SAS");
    await user.click(within(supplierForm as HTMLElement).getByRole("button", { name: "Synchroniser" }));

    await waitFor(() => {
      expect(mockedApi.syncSuppliers).toHaveBeenCalledWith("ACME SAS");
    });
    expect(await screen.findByText("Fournisseur synchronisé")).toBeInTheDocument();
    expect(screen.getByText("ACME SAS")).toBeInTheDocument();
  });

  test("affiche une erreur si la synchronisation fournisseur échoue", async () => {
    const user = userEvent.setup();
    mockedApi.syncSuppliers.mockRejectedValue(new Error("Fournisseur introuvable."));

    render(<OdooSyncPanel />);
    const supplierForm = screen.getByLabelText("Nom du fournisseur").closest("form");
    await user.type(screen.getByLabelText("Nom du fournisseur"), "INCONNU");
    await user.click(within(supplierForm as HTMLElement).getByRole("button", { name: "Synchroniser" }));

    expect(await screen.findByText("Fournisseur introuvable.")).toBeInTheDocument();
  });

  test("synchronise un bon de commande par référence", async () => {
    const user = userEvent.setup();
    mockedApi.syncPurchaseOrders.mockResolvedValue({ synced: true, purchase_order: purchaseOrder });

    render(<OdooSyncPanel />);
    const poForm = screen.getByLabelText("Référence du bon de commande (BC)").closest("form");
    await user.type(screen.getByLabelText("Référence du bon de commande (BC)"), "BC-2026-010");
    await user.click(within(poForm as HTMLElement).getByRole("button", { name: "Synchroniser" }));

    await waitFor(() => {
      expect(mockedApi.syncPurchaseOrders).toHaveBeenCalledWith("BC-2026-010");
    });
    expect(await screen.findByText("Bon de commande synchronisé")).toBeInTheDocument();
    expect(screen.getByText(/BC-2026-010/)).toBeInTheDocument();
  });

  test("désactive le bouton tant que la saisie est vide", () => {
    render(<OdooSyncPanel />);
    expect(screen.getAllByRole("button", { name: "Synchroniser" })[0]).toBeDisabled();
    expect(screen.getAllByRole("button", { name: "Synchroniser" })[1]).toBeDisabled();
  });
});