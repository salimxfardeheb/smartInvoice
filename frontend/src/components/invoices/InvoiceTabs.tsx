"use client";

import Link from "next/link";

/** Onglets de navigation d'une facture (pages détail). */
export function InvoiceTabs({ invoiceId, active }: { invoiceId: number; active: string }) {
  const tabs = [
    { id: "overview", href: `/invoices/${invoiceId}`, label: "Vue d'ensemble" },
    { id: "ocr", href: `/invoices/${invoiceId}/ocr`, label: "OCR" },
    { id: "matching", href: `/invoices/${invoiceId}/matching`, label: "Matching" },
    { id: "validation", href: `/invoices/${invoiceId}/validation`, label: "Validation" },
    { id: "history", href: `/invoices/${invoiceId}/history`, label: "Historique" },
  ];

  return (
    <nav aria-label="Sections de la facture" className="flex flex-wrap gap-1 border-b border-slate-200">
      {tabs.map((tab) => {
        const isActive = tab.id === active;
        return (
          <Link
            key={tab.id}
            href={tab.href}
            aria-current={isActive ? "page" : undefined}
            className={`-mb-px rounded-t-md px-4 py-2 text-sm font-medium transition ${
              isActive
                ? "border border-b-white border-slate-200 bg-white text-brand-700"
                : "text-slate-500 hover:text-slate-800"
            }`}
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
