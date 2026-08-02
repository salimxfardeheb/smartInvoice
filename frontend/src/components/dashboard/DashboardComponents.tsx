"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import type { DashboardSummary, InvoiceStatus } from "@/types";
import { STATUS_ORDER, STATUS_STYLES } from "@/lib/status";
import { formatDateTime } from "@/lib/format";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { CategoryBadge, SeverityBadge } from "@/components/ui/badges";
import { EmptyState } from "@/components/ui/EmptyState";

/** Cartes « factures par statut » du tableau de bord. */
export function StatusOverview({ summary }: { summary: DashboardSummary }) {
  const router = useRouter();
  const total = STATUS_ORDER.reduce((acc, status) => acc + (summary.by_status[status] ?? 0), 0);

  return (
    <Card>
      <CardHeader
        title="Factures par statut"
        subtitle={`${total} facture(s) au total`}
      />
      <CardBody>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {STATUS_ORDER.map((status) => {
            const count = summary.by_status[status] ?? 0;
            return (
              <button
                key={status}
                type="button"
                onClick={() => router.push(`/invoices?status=${encodeURIComponent(status)}`)}
                className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-left transition hover:border-brand-500 hover:shadow-sm"
              >
                <span
                  className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ring-1 ${STATUS_STYLES[status]}`}
                >
                  {status}
                </span>
                <p className="mt-3 text-2xl font-semibold text-slate-900">{count}</p>
              </button>
            );
          })}
        </div>
      </CardBody>
    </Card>
  );
}

/** Liste des anomalies en attente (non résolues). */
export function PendingAnomalies({ summary }: { summary: DashboardSummary }) {
  const { pending_anomalies } = summary;

  return (
    <Card>
      <CardHeader
        title="Anomalies en attente"
        subtitle="Anomalies de matching non résolues"
      />
      <CardBody>
        {pending_anomalies.length === 0 ? (
          <EmptyState title="Aucune anomalie en attente" description="Le suivi est au vert." />
        ) : (
          <ul className="divide-y divide-slate-100">
            {pending_anomalies.map((anomaly) => (
              <li key={anomaly.id} className="flex items-start justify-between gap-3 py-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <SeverityBadge severity={anomaly.severity} />
                    <CategoryBadge category={anomaly.category} />
                  </div>
                  <p className="mt-1 text-sm text-slate-800">{anomaly.message}</p>
                  <p className="mt-0.5 text-xs text-slate-500">
                    {anomaly.invoice_number}
                    {anomaly.supplier_name ? ` · ${anomaly.supplier_name}` : ""} ·{" "}
                    {formatDateTime(anomaly.created_at)}
                  </p>
                  {anomaly.expected_value && anomaly.actual_value && (
                    <p className="mt-0.5 text-xs text-slate-500">
                      Attendu : <span className="font-medium">{anomaly.expected_value}</span> · Reçu :{" "}
                      <span className="font-medium">{anomaly.actual_value}</span>
                    </p>
                  )}
                </div>
                <Link
                  href={`/invoices/${anomaly.invoice_id}/validation`}
                  className="shrink-0 text-xs font-medium text-brand-600 hover:underline"
                >
                  Traiter →
                </Link>
              </li>
            ))}
          </ul>
        )}
      </CardBody>
    </Card>
  );
}
