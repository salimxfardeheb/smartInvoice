"use client";

import type { InvoiceStatus, AnomalySeverity, AuditAction } from "@/types";
import {
  ACTION_LABELS,
  CATEGORY_LABELS,
  SEVERITY_STYLES,
  STATUS_STYLES,
} from "@/lib/status";
import type { AnomalyCategory } from "@/types";
import { Badge } from "@/components/ui/Badge";

/** Badge coloré du statut d'une facture. */
export function StatusBadge({ status }: { status: InvoiceStatus }) {
  return (
    <span
      className={`inline-flex items-center whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ring-1 ${STATUS_STYLES[status] ?? "bg-slate-100 text-slate-700 ring-slate-300"}`}
    >
      {status}
    </span>
  );
}

/** Badge coloré de la sévérité d'une anomalie. */
export function SeverityBadge({ severity }: { severity: AnomalySeverity }) {
  return (
    <span
      className={`inline-flex items-center whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium capitalize ring-1 ${SEVERITY_STYLES[severity] ?? "bg-slate-100 text-slate-700 ring-slate-300"}`}
    >
      {severity}
    </span>
  );
}

/** Badge du type d'anomalie. */
export function CategoryBadge({ category }: { category: AnomalyCategory }) {
  return <Badge tone="slate">{CATEGORY_LABELS[category] ?? category}</Badge>;
}

/** Badge du type d'action d'audit. */
export function ActionBadge({ action }: { action: AuditAction }) {
  const toneByAction: Record<AuditAction, string> = {
    validation: "emerald",
    correction: "blue",
    rejet: "rose",
    vendor_bill_créée: "teal",
  };
  return <Badge tone={toneByAction[action] ?? "slate"}>{ACTION_LABELS[action] ?? action}</Badge>;
}

/** Jauge de score 0..1 avec couleur par seuil. */
export function ScoreBadge({
  score,
  label,
}: {
  score: number | null | undefined;
  label: string;
}) {
  if (score === null || score === undefined) {
    return <span className="text-xs text-slate-400">—</span>;
  }
  const percent = Math.round(score * 100);
  const tone = percent >= 80 ? "emerald" : percent >= 60 ? "amber" : "rose";
  const labelTone: Record<string, string> = {
    emerald: "bg-emerald-50 text-emerald-700",
    amber: "bg-amber-50 text-amber-700",
    rose: "bg-rose-50 text-rose-700",
  };
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-slate-500">{label}</span>
      <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${labelTone[tone]}`}>
        {percent} %
      </span>
    </div>
  );
}
