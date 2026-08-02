"use client";

import Link from "next/link";

import type { Invoice } from "@/types";
import { formatCurrency, formatDate, formatDateTime, formatScore } from "@/lib/format";
import { StatusBadge } from "@/components/ui/badges";
import { Table, TD, TH, THead, TR } from "@/components/ui/Table";
import { EmptyState } from "@/components/ui/EmptyState";

/** Tableau des factures avec liens vers la vue détaillée. */
export function InvoiceTable({ invoices }: { invoices: Invoice[] }) {
  if (invoices.length === 0) {
    return (
      <EmptyState
        title="Aucune facture trouvée"
        description="Modifiez les filtres ou déposez une nouvelle facture."
      />
    );
  }

  return (
    <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
      <Table>
        <THead>
          <TH>Numéro</TH>
          <TH>Fournisseur</TH>
          <TH>Statut</TH>
          <TH>Émise le</TH>
          <TH className="text-right">Total TTC</TH>
          <TH>OCR</TH>
          <TH>Matching</TH>
          <TH>Déposée le</TH>
        </THead>
        <tbody>
          {invoices.map((invoice) => (
            <TR key={invoice.id}>
              <TD>
                <Link
                  href={`/invoices/${invoice.id}/ocr`}
                  className="font-medium text-brand-600 hover:underline"
                >
                  {invoice.invoice_number}
                </Link>
              </TD>
              <TD className="max-w-[12rem] truncate">{invoice.supplier.name}</TD>
              <TD>
                <StatusBadge status={invoice.status} />
              </TD>
              <TD>{formatDate(invoice.issue_date)}</TD>
              <TD className="text-right font-medium">
                {formatCurrency(invoice.total_incl_tax, invoice.currency)}
              </TD>
              <TD>{formatScore(invoice.ocr_confidence_score)}</TD>
              <TD>{formatScore(invoice.matching_score)}</TD>
              <TD className="text-slate-500">{formatDateTime(invoice.created_at)}</TD>
            </TR>
          ))}
        </tbody>
      </Table>
    </div>
  );
}
