"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { AppShell } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { FilePreview } from "@/components/invoices/FilePreview";
import { InvoiceHeader } from "@/components/invoices/InvoiceHeader";
import { InvoiceTabs } from "@/components/invoices/InvoiceTabs";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { useInvoice } from "@/hooks/useInvoices";

export default function InvoiceOverviewPage({ params }: { params: { id: string } }) {
  return (
    <RequireAuth>
      <AppShell>
        <InvoiceOverviewContent invoiceId={Number(params.id)} />
      </AppShell>
    </RequireAuth>
  );
}

function InvoiceOverviewContent({ invoiceId }: { invoiceId: number }) {
  const { invoice, loading, error } = useInvoice(invoiceId);
  const router = useRouter();

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
      <InvoiceTabs invoiceId={invoiceId} active="overview" />
      <InvoiceHeader invoice={invoice} />

      <Card>
        <CardHeader
          title="Document source"
          subtitle={invoice.file_info?.original_filename ?? "Aucun fichier associé"}
        />
        <CardBody>
          {invoice.file_info ? (
            <FilePreview invoice={invoice} />
          ) : (
            <Alert tone="info">Aucun fichier source n'est associé à cette facture.</Alert>
          )}
        </CardBody>
      </Card>

      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" onClick={() => router.push(`/invoices/${invoiceId}/ocr`)}>
          Voir l'analyse OCR
        </Button>
        <Button variant="secondary" onClick={() => router.push(`/invoices/${invoiceId}/matching`)}>
          Voir le matching
        </Button>
        <Button variant="secondary" onClick={() => router.push(`/invoices/${invoiceId}/validation`)}>
          Valider / corriger
        </Button>
        <Button variant="secondary" onClick={() => router.push(`/invoices/${invoiceId}/history`)}>
          Historique
        </Button>
      </div>
    </div>
  );
}
