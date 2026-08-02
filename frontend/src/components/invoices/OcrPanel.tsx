"use client";

import { useCallback, useEffect, useState } from "react";

import { api } from "@/lib/api-client";
import { formatCurrency } from "@/lib/format";
import type { Invoice, OcrResult } from "@/types";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { ScoreBadge } from "@/components/ui/badges";
import { Table, TD, TH, THead, TR } from "@/components/ui/Table";

function ExtractedLines({ invoice }: { invoice: Invoice }) {
  const lines = invoice.extracted_data?.lines ?? [];
  if (lines.length === 0) {
    return <p className="text-sm text-slate-500">Aucune ligne extraite.</p>;
  }
  return (
    <Table>
      <THead>
        <TH>N°</TH>
        <TH>Description</TH>
        <TH>Réf. produit</TH>
        <TH className="text-right">Qté</TH>
        <TH className="text-right">PU HT</TH>
        <TH className="text-right">TVA</TH>
        <TH className="text-right">Montant</TH>
      </THead>
      <tbody>
        {lines.map((line) => (
          <TR key={line.line_number}>
            <TD>{line.line_number}</TD>
            <TD className="max-w-xs truncate">{line.description}</TD>
            <TD>{line.product_ref ?? "—"}</TD>
            <TD className="text-right">{line.quantity ?? "—"}</TD>
            <TD className="text-right">
              {formatCurrency(line.unit_price, invoice.currency)}
            </TD>
            <TD className="text-right">{line.tax_rate ? `${line.tax_rate} %` : "—"}</TD>
            <TD className="text-right">{formatCurrency(line.amount, invoice.currency)}</TD>
          </TR>
        ))}
      </tbody>
    </Table>
  );
}

/** Panneau OCR : données extraites, score et lancement de l'analyse. */
export function OcrPanel({ invoice, onProcessed }: { invoice: Invoice; onProcessed: (result: OcrResult) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canProcess = invoice.status === "Déposée" || invoice.status === "Erreur système";

  const process = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await api.processInvoice(invoice.id);
      onProcessed(result);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Erreur pendant l'analyse.");
    } finally {
      setBusy(false);
    }
  }, [invoice.id, onProcessed]);

  // Laisse l'état d'erreur local expirer quand la facture est rafraîchie.
  useEffect(() => setError(null), [invoice.id]);

  const general = invoice.extracted_data?.general;
  const financial = invoice.extracted_data?.financial;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader
          title="Données extraites"
          subtitle="Résultat de l'analyse OCR"
          action={
            <ScoreBadge score={invoice.ocr_confidence_score} label="Score OCR" />
          }
        />
        <CardBody>
          {error && <Alert tone="danger" className="mb-4">{error}</Alert>}
          {invoice.error_message && (
            <Alert tone="danger" className="mb-4" title="Erreur système">
              {invoice.error_message}
            </Alert>
          )}
          {general ? (
            <dl className="grid grid-cols-1 gap-x-8 gap-y-2 sm:grid-cols-2 lg:grid-cols-3">
              <Field label="Fournisseur" value={general.supplier_name} />
              <Field label="Adresse" value={general.supplier_address} />
              <Field label="Numéro de facture" value={general.invoice_number} />
              <Field label="Date d'émission" value={general.issue_date} />
              <Field label="Date d'échéance" value={general.due_date} />
              <Field label="Devise" value={general.currency} />
              <Field label="Réf. bon de commande" value={general.purchase_order_reference} />
              <Field label="Réf. fournisseur" value={general.supplier_reference} />
            </dl>
          ) : (
            <p className="text-sm text-slate-500">
              Aucune donnée extraite pour le moment. Lancez l'analyse OCR si la facture le permet.
            </p>
          )}

          {financial && (
            <div className="mt-5 border-t border-slate-100 pt-4">
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                Montants
              </h3>
              <dl className="grid grid-cols-1 gap-x-8 gap-y-2 sm:grid-cols-2 lg:grid-cols-3">
                <Field label="Total HT" value={financial.total_excl_tax} currency={invoice.currency} />
                <Field label="TVA" value={financial.tax_amount} currency={invoice.currency} />
                <Field label="Total TTC" value={financial.total_incl_tax} currency={invoice.currency} />
                <Field label="Remise" value={financial.discount} currency={invoice.currency} />
                <Field label="Frais de port" value={financial.shipping_fees} currency={invoice.currency} />
              </dl>
            </div>
          )}
        </CardBody>
      </Card>

      {general && (
        <Card>
          <CardHeader title="Lignes extraites" />
          <CardBody>
            <ExtractedLines invoice={invoice} />
          </CardBody>
        </Card>
      )}

      {canProcess && (
        <div className="flex justify-end">
          <Button onClick={process} loading={busy}>
            Lancer l'analyse OCR
          </Button>
        </div>
      )}
    </div>
  );
}

function Field({
  label,
  value,
  currency,
}: {
  label: string;
  value: string | null | undefined;
  currency?: string;
}) {
  const display =
    currency && value
      ? formatCurrency(value, currency)
      : value ?? "—";
  return (
    <div className="flex items-baseline justify-between gap-4 py-1 text-sm">
      <dt className="text-slate-500">{label}</dt>
      <dd className="text-right font-medium text-slate-900">{display}</dd>
    </div>
  );
}
