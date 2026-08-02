"use client";

import Link from "next/link";

import { AppShell } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { InvoiceHeader } from "@/components/invoices/InvoiceHeader";
import { InvoiceTabs } from "@/components/invoices/InvoiceTabs";
import { MatchingPanel } from "@/components/invoices/MatchingPanel";
import { Alert } from "@/components/ui/Alert";
import { Spinner } from "@/components/ui/Spinner";
import { useInvoice } from "@/hooks/useInvoices";

export default function MatchingPage({ params }: { params: { id: string } }) {
  return (
    <RequireAuth>
      <AppShell>
        <MatchingContent invoiceId={Number(params.id)} />
      </AppShell>
    </RequireAuth>
  );
}

function MatchingContent({ invoiceId }: { invoiceId: number }) {
  const { invoice, loading, error, reload } = useInvoice(invoiceId);

  if (loading) return <Spinner label="Chargement du matching…" />;
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
      <InvoiceTabs invoiceId={invoiceId} active="matching" />
      <InvoiceHeader invoice={invoice} />
      <MatchingPanel invoice={invoice} onMatched={reload} />
    </div>
  );
}
