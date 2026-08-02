"use client";

import Link from "next/link";

import { AppShell } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { InvoiceHeader } from "@/components/invoices/InvoiceHeader";
import { InvoiceTabs } from "@/components/invoices/InvoiceTabs";
import { ValidationPanel } from "@/components/invoices/ValidationPanel";
import { Alert } from "@/components/ui/Alert";
import { Spinner } from "@/components/ui/Spinner";
import { useInvoice } from "@/hooks/useInvoices";

export default function ValidationPage({ params }: { params: { id: string } }) {
  return (
    <RequireAuth>
      <AppShell>
        <ValidationContent invoiceId={Number(params.id)} />
      </AppShell>
    </RequireAuth>
  );
}

function ValidationContent({ invoiceId }: { invoiceId: number }) {
  const { invoice, loading, error, setInvoice } = useInvoice(invoiceId);

  if (loading) return <Spinner label="Chargement de la validation…" />;
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
      <InvoiceTabs invoiceId={invoiceId} active="validation" />
      <InvoiceHeader invoice={invoice} />
      <ValidationPanel invoice={invoice} onUpdated={setInvoice} />
    </div>
  );
}
