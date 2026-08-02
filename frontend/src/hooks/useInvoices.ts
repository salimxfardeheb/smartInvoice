"use client";

/** Hooks d'accès aux données des factures. */

import { useCallback, useMemo } from "react";

import { api } from "@/lib/api-client";
import type {
  AuditLog,
  DashboardSummary,
  Invoice,
  InvoiceFilters,
  InvoiceListResponse,
} from "@/types";
import { useAction, useAsyncData } from "@/hooks/useAsync";

export interface InvoicesState {
  invoices: Invoice[];
  total: number;
  loading: boolean;
  error: string | null;
  reload: () => void;
}

export function useInvoices(
  filters: InvoiceFilters,
  limit: number,
  offset: number,
): InvoicesState {
  const loader = useCallback(
    () => api.listInvoices(filters, limit, offset),
    [filters, limit, offset],
  );
  const state = useAsyncData<InvoiceListResponse>(loader, [
    filters.status,
    filters.supplier_id,
    filters.issue_date_from,
    filters.issue_date_to,
    filters.sort,
    limit,
    offset,
  ]);
  return {
    invoices: state.data?.items ?? [],
    total: state.data?.total ?? 0,
    loading: state.loading,
    error: state.error,
    reload: state.reload,
  };
}

export function useInvoice(id: number): {
  invoice: Invoice | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
  setInvoice: (invoice: Invoice) => void;
} {
  const loader = useCallback(() => api.getInvoice(id), [id]);
  const state = useAsyncData<Invoice>(loader, [id], id > 0);
  return {
    invoice: state.data,
    loading: state.loading,
    error: state.error,
    reload: state.reload,
    setInvoice: state.setData,
  };
}

export function useSummary(): {
  summary: DashboardSummary | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
} {
  const state = useAsyncData<DashboardSummary>(useCallback(() => api.summary(), []), []);
  return {
    summary: state.data,
    loading: state.loading,
    error: state.error,
    reload: state.reload,
  };
}

export function useAuditLogs(id: number): {
  logs: AuditLog[];
  loading: boolean;
  error: string | null;
  reload: () => void;
} {
  const state = useAsyncData<AuditLog[]>(
    useCallback(() => api.auditLogs(id), [id]),
    [id],
    id > 0,
  );
  return { logs: state.data ?? [], loading: state.loading, error: state.error, reload: state.reload };
}

/** Actions de cycle de vie d'une facture, avec états `busy`/`error`. */
export function useInvoiceActions(onDone: (invoice: Invoice) => void) {
  const onDoneRef = useMemo(() => onDone, [onDone]);

  const validate = useAction(async (id: number) => {
    const invoice = await api.validateInvoice(id);
    onDoneRef(invoice);
    return invoice;
  });

  const reject = useAction(async (id: number, reason: string) => {
    const invoice = await api.rejectInvoice(id, reason);
    onDoneRef(invoice);
    return invoice;
  });

  const correct = useAction(async (id: number, payload: Parameters<typeof api.correctInvoice>[1]) => {
    const invoice = await api.correctInvoice(id, payload);
    onDoneRef(invoice);
    return invoice;
  });

  const createVendorBill = useAction(async (id: number) => {
    const invoice = await api.createVendorBill(id);
    onDoneRef(invoice);
    return invoice;
  });

  return { validate, reject, correct, createVendorBill };
}
