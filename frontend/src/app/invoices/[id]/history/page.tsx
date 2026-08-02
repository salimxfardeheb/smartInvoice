"use client";

import Link from "next/link";

import { AppShell } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { AuditLogTimeline } from "@/components/invoices/AuditLogTimeline";
import { InvoiceHeader } from "@/components/invoices/InvoiceHeader";
import { InvoiceTabs } from "@/components/invoices/InvoiceTabs";
import { Alert } from "@/components/ui/Alert";
import { Spinner } from "@/components/ui/Spinner";
import { useAuditLogs, useInvoice } from "@/hooks/useInvoices";

export default function HistoryPage({ params }: { params: { id: string } }) {
  return (
    <RequireAuth>
      <AppShell>
        <HistoryContent invoiceId={Number(params.id)} />
      </AppShell>
    </RequireAuth>
  );
}

function HistoryContent({ invoiceId }: { invoiceId: number }) {
  const { invoice, loading, error } = useInvoice(invoiceId);
  const { logs, loading: logsLoading, error: logsError } = useAuditLogs(invoiceId);

  if (loading) return <Spinner label="Chargement de la facture…" />;
  if (error) {
    return (
      <Alert tone="danger">
        {error}{" "}
        <Link href="/invoices" className="font-medium underline">
          Retour à la liste
        </Link>
      </Alert>
    );
  }
  if (!invoice) return null;

  return (
    <div className="space-y-6">
      <InvoiceTabs invoiceId={invoiceId} active="history" />
      <InvoiceHeader invoice={invoice} />
      {logsLoading ? (
        <Spinner label="Chargement de l'historique…" />
      ) : logsError ? (
        <Alert tone="danger">{logsError}</Alert>
      ) : (
        <AuditLogTimeline logs={logs} />
      )}
    </div>
  );
}
