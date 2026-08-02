"use client";

import type { Invoice } from "@/types";
import { formatCurrency, formatDate, formatScore } from "@/lib/format";
import { StatusBadge } from "@/components/ui/badges";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";

/** En-tête descriptif d'une facture (métadonnées + scores). */
export function InvoiceHeader({ invoice }: { invoice: Invoice }) {
  const rows: Array<[string, string]> = [
    ["Fournisseur", invoice.supplier.name],
    ["Date d'émission", formatDate(invoice.issue_date)],
    ["Date d'échéance", formatDate(invoice.due_date)],
    ["Devise", invoice.currency],
    ["Total HT", formatCurrency(invoice.total_excl_tax, invoice.currency)],
    ["TVA", formatCurrency(invoice.tax_amount, invoice.currency)],
    ["Total TTC", formatCurrency(invoice.total_incl_tax, invoice.currency)],
    ["Remise", formatCurrency(invoice.discount, invoice.currency)],
    ["Frais de port", formatCurrency(invoice.shipping_fees, invoice.currency)],
    ["Fichier", invoice.file_info?.original_filename ?? "—"],
  ];

  return (
    <Card>
      <CardHeader
        title={
          <span className="flex items-center gap-3">
            {invoice.invoice_number}
            <StatusBadge status={invoice.status} />
            {invoice.is_duplicate && (
              <span className="text-xs font-medium text-rose-600">Doublon détecté</span>
            )}
          </span>
        }
        subtitle={`Facture #${invoice.id}`}
      />
      <CardBody>
        <div className="grid grid-cols-1 gap-x-8 gap-y-1 sm:grid-cols-2 lg:grid-cols-3">
          {rows.map(([label, value]) => (
            <div key={label} className="flex items-baseline justify-between gap-4 py-1 text-sm">
              <span className="text-slate-500">{label}</span>
              <span className="font-medium text-slate-900">{value}</span>
            </div>
          ))}
        </div>
        <div className="mt-4 flex flex-wrap gap-6 border-t border-slate-100 pt-4">
          <div className="text-sm">
            <span className="mr-2 text-slate-500">Score OCR</span>
            <span className="font-semibold">{formatScore(invoice.ocr_confidence_score)}</span>
          </div>
          <div className="text-sm">
            <span className="mr-2 text-slate-500">Score matching</span>
            <span className="font-semibold">{formatScore(invoice.matching_score)}</span>
          </div>
          {invoice.vendor_bill_id !== null && (
            <div className="text-sm">
              <span className="mr-2 text-slate-500">Vendor Bill Odoo</span>
              <span className="font-semibold">#{invoice.vendor_bill_id}</span>
            </div>
          )}
        </div>
        {invoice.rejection_reason && (
          <p className="mt-4 rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700">
            <span className="font-medium">Motif de rejet :</span> {invoice.rejection_reason}
          </p>
        )}
        {invoice.error_message && (
          <p className="mt-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
            <span className="font-medium">Erreur système :</span> {invoice.error_message}
          </p>
        )}
      </CardBody>
    </Card>
  );
}
