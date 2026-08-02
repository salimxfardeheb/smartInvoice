/** Tests des hooks d'accès aux données des factures. */

import { act, renderHook, waitFor } from "@testing-library/react";

import { api } from "@/lib/api-client";
import { ApiError } from "@/lib/errors";
import type { Invoice } from "@/types";
import {
  useAuditLogs,
  useInvoice,
  useInvoiceActions,
  useInvoices,
  useSummary,
} from "@/hooks/useInvoices";

import {
  makeAuditLogs,
  makeInvoice,
  makeMatchingResult,
  makeSummary,
} from "./fixtures";

jest.mock("@/lib/api-client", () => ({
  api: {
    listInvoices: jest.fn(),
    getInvoice: jest.fn(),
    summary: jest.fn(),
    auditLogs: jest.fn(),
    validateInvoice: jest.fn(),
    rejectInvoice: jest.fn(),
    correctInvoice: jest.fn(),
    createVendorBill: jest.fn(),
  },
}));

const mockedApi = api as jest.Mocked<typeof api>;

beforeEach(() => {
  jest.clearAllMocks();
});

describe("useInvoices", () => {
  test("liste les factures avec filtres et pagination", async () => {
    mockedApi.listInvoices.mockResolvedValue({ items: [makeInvoice()], total: 1 });

    const { result } = renderHook(() =>
      useInvoices({ status: "À vérifier" }, 20, 0),
    );

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.invoices).toHaveLength(1);
    expect(result.current.total).toBe(1);
    expect(result.current.error).toBeNull();

    expect(mockedApi.listInvoices).toHaveBeenCalledWith(
      { status: "À vérifier" },
      20,
      0,
    );
  });

  test("retourne une liste vide sans données", async () => {
    mockedApi.listInvoices.mockResolvedValue({ items: [], total: 0 });

    const { result } = renderHook(() => useInvoices({}, 20, 0));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.invoices).toEqual([]);
    expect(result.current.total).toBe(0);
  });

  test("reload recharge la liste", async () => {
    mockedApi.listInvoices
      .mockResolvedValueOnce({ items: [], total: 0 })
      .mockResolvedValueOnce({ items: [makeInvoice()], total: 1 });

    const { result } = renderHook(() => useInvoices({}, 20, 0));
    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => result.current.reload());
    await waitFor(() => expect(result.current.invoices).toHaveLength(1));
    expect(mockedApi.listInvoices).toHaveBeenCalledTimes(2);
  });
});

describe("useInvoice", () => {
  test("charge une facture par id", async () => {
    mockedApi.getInvoice.mockResolvedValue(makeInvoice({ id: 7 }));

    const { result } = renderHook(() => useInvoice(7));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.invoice?.id).toBe(7);
  });

  test("ne charge pas quand id <= 0", async () => {
    const { result } = renderHook(() => useInvoice(0));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(mockedApi.getInvoice).not.toHaveBeenCalled();
    expect(result.current.invoice).toBeNull();
  });

  test("setInvoice met à jour la facture affichée", async () => {
    mockedApi.getInvoice.mockResolvedValue(makeInvoice({ id: 7 }));

    const { result } = renderHook(() => useInvoice(7));
    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => result.current.setInvoice(makeInvoice({ id: 8 })));
    expect(result.current.invoice?.id).toBe(8);
  });
});

describe("useSummary", () => {
  test("charge le résumé du tableau de bord", async () => {
    mockedApi.summary.mockResolvedValue(makeSummary());

    const { result } = renderHook(() => useSummary());

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.summary).not.toBeNull();
    expect(result.current.summary?.pending_anomalies).toHaveLength(1);
  });
});

describe("useAuditLogs", () => {
  test("charge les entrées d'audit", async () => {
    mockedApi.auditLogs.mockResolvedValue(makeAuditLogs());

    const { result } = renderHook(() => useAuditLogs(1));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.logs).toHaveLength(2);
  });

  test("ne charge pas quand id <= 0", async () => {
    const { result } = renderHook(() => useAuditLogs(0));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(mockedApi.auditLogs).not.toHaveBeenCalled();
    expect(result.current.logs).toEqual([]);
  });
});

describe("useInvoiceActions", () => {
  test("valide une facture et notifie le parent", async () => {
    const invoice = makeInvoice({ status: "Validée" });
    mockedApi.validateInvoice.mockResolvedValue(invoice);
    const onDone = jest.fn();

    const { result } = renderHook(() => useInvoiceActions(onDone));
    let returned: Invoice | null = null;
    await act(async () => {
      returned = await result.current.validate.run(1);
    });

    expect(returned).toBe(invoice);
    expect(mockedApi.validateInvoice).toHaveBeenCalledWith(1);
    expect(onDone).toHaveBeenCalledWith(invoice);
  });

  test("rejette une facture avec la raison", async () => {
    const invoice = makeInvoice({ status: "Rejetée" });
    mockedApi.rejectInvoice.mockResolvedValue(invoice);

    const { result } = renderHook(() => useInvoiceActions(jest.fn()));
    let returned: Invoice | null = null;
    await act(async () => {
      returned = await result.current.reject.run(1, "Doublon");
    });

    expect(returned).toBe(invoice);
    expect(mockedApi.rejectInvoice).toHaveBeenCalledWith(1, "Doublon");
  });

  test("corrige une facture", async () => {
    const invoice = makeInvoice();
    mockedApi.correctInvoice.mockResolvedValue(invoice);

    const { result } = renderHook(() => useInvoiceActions(jest.fn()));
    const payload = { currency: "USD" };
    let returned: Invoice | null = null;
    await act(async () => {
      returned = await result.current.correct.run(1, payload);
    });

    expect(returned).toBe(invoice);
    expect(mockedApi.correctInvoice).toHaveBeenCalledWith(1, payload);
  });

  test("crée la vendor bill", async () => {
    const invoice = makeInvoice({ status: "Vendor Bill créée" });
    mockedApi.createVendorBill.mockResolvedValue(invoice);

    const { result } = renderHook(() => useInvoiceActions(jest.fn()));
    let returned: Invoice | null = null;
    await act(async () => {
      returned = await result.current.createVendorBill.run(1);
    });

    expect(returned).toBe(invoice);
    expect(mockedApi.createVendorBill).toHaveBeenCalledWith(1);
  });

  test("une action en échec expose busy et error", async () => {
    mockedApi.validateInvoice.mockRejectedValue(new ApiError(409, "Transition impossible"));

    const { result } = renderHook(() => useInvoiceActions(jest.fn()));
    await act(async () => {
      await result.current.validate.run(1);
    });

    expect(result.current.validate.error).toBe("Transition impossible");
    expect(result.current.validate.busy).toBe(false);
  });
});
