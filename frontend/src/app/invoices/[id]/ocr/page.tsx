"use client";

import Link from "next/link";

import { AppShell } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { FilePreview } from "@/components/invoices/FilePreview";
import { InvoiceHeader } from "@/components/invoices/InvoiceHeader";
import { InvoiceTabs } from "@/components/invoices/InvoiceTabs";
import { OcrPanel } from "@/components/invoices/OcrPanel";
import { Alert } from "@/components/ui/Alert";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { useInvoice } from "@/hooks/useInvoices";

export default function OcrPage({ params }: { params: { id: string } }) {
  return (
    <RequireAuth>
      <AppShell>
        <OcrContent invoiceId={Number(params.id)} />
      </AppShell>
    </RequireAuth>
  );
}

function OcrContent({ invoiceId }: { invoiceId: number }) {
  const { invoice, loading, error, reload } = useInvoice(invoiceId);

  if (loading) return <Spinner label="Chargement de l'analyse OCR…" />;
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
      <InvoiceTabs invoiceId={invoiceId} active="ocr" />
      <InvoiceHeader invoice={invoice} />
      <OcrPanel invoice={invoice} onProcessed={reload} />
      <Card>
        <CardHeader title="Document source" />
        <CardBody>
          {invoice.file_info ? (
            <FilePreview invoice={invoice} />
          ) : (
            <Alert tone="info">Aucun fichier source associé.</Alert>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
