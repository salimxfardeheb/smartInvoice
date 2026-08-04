"use client";

import Link from "next/link";

import { CATEGORY_LABELS } from "@/lib/status";
import { formatDateTime } from "@/lib/format";
import type { Anomaly } from "@/types";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Table, TD, TH, THead, TR } from "@/components/ui/Table";
import { CategoryBadge, SeverityBadge } from "@/components/ui/badges";

/** Tableau des anomalies avec bouton de résolution. */
export function AnomaliesTable({
  anomalies,
  busy,
  onResolve,
}: {
  anomalies: Anomaly[];
  busy: boolean;
  onResolve: (anomaly: Anomaly) => void;
}) {
  if (anomalies.length === 0) {
    return (
      <EmptyState
        title="Aucune anomalie"
        description="Aucune anomalie ne correspond aux filtres sélectionnés."
      />
    );
  }

  return (
    <Table>
      <THead>
        <TH>Sévérité</TH>
        <TH>Type</TH>
        <TH>Détail</TH>
        <TH>Facture</TH>
        <TH>Écart</TH>
        <TH>Créée le</TH>
        <TH className="text-right">Action</TH>
      </THead>
      <tbody>
        {anomalies.map((anomaly) => (
          <TR key={anomaly.id}>
            <TD>
              <SeverityBadge severity={anomaly.severity} />
            </TD>
            <TD>
              <CategoryBadge category={anomaly.category} />
            </TD>
            <TD>
              <p className="max-w-xs text-slate-800">{anomaly.message}</p>
              {anomaly.resolved && anomaly.resolved_at && (
                <p className="mt-0.5 text-xs text-emerald-600">
                  Résolue le {formatDateTime(anomaly.resolved_at)}
                </p>
              )}
            </TD>
            <TD>
              <Link
                href={`/invoices/${anomaly.invoice_id}/matching`}
                className="font-medium text-brand-600 hover:underline"
              >
                {anomaly.invoice_number}
              </Link>
              {anomaly.supplier_name && (
                <p className="text-xs text-slate-500">{anomaly.supplier_name}</p>
              )}
            </TD>
            <TD>
              {anomaly.expected_value || anomaly.actual_value ? (
                <span className="text-xs text-slate-500">
                  Attendu : <b className="text-slate-700">{anomaly.expected_value ?? "—"}</b>
                  <br />
                  Reçu : <b className="text-slate-700">{anomaly.actual_value ?? "—"}</b>
                </span>
              ) : (
                <span className="text-xs text-slate-400">—</span>
              )}
            </TD>
            <TD>
              <span className="text-xs text-slate-500">{formatDateTime(anomaly.created_at)}</span>
            </TD>
            <TD className="text-right">
              {anomaly.resolved ? (
                <Link
                  href={`/invoices/${anomaly.invoice_id}/validation`}
                  className="text-xs font-medium text-brand-600 hover:underline"
                >
                  Voir la facture →
                </Link>
              ) : (
                <div className="flex items-center justify-end gap-2">
                  <Link
                    href={`/invoices/${anomaly.invoice_id}/validation`}
                    className="text-xs font-medium text-slate-500 hover:underline"
                  >
                    Traiter
                  </Link>
                  <Button size="sm" variant="success" disabled={busy} onClick={() => onResolve(anomaly)}>
                    Marquer résolue
                  </Button>
                </div>
              )}
            </TD>
          </TR>
        ))}
      </tbody>
    </Table>
  );
}