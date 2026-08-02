"use client";

import { useCallback, useState } from "react";

import { api } from "@/lib/api-client";
import { formatDelta, formatScore } from "@/lib/format";
import type { Invoice, MatchingResult } from "@/types";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { CategoryBadge, SeverityBadge } from "@/components/ui/badges";
import { Table, TD, TH, THead, TR } from "@/components/ui/Table";

function DeltaCell({ delta, matched }: { delta: number | null; matched: boolean }) {
  if (delta === null) return <span className="text-slate-400">—</span>;
  const tone = matched ? "text-emerald-600" : "text-rose-600";
  return <span className={`font-medium ${tone}`}>{formatDelta(delta)}</span>;
}

/** Panneau de matching : comparaison facture ↔ bon de commande. */
export function MatchingPanel({
  invoice,
  onMatched,
}: {
  invoice: Invoice;
  onMatched: (result: MatchingResult) => void;
}) {
  const [result, setResult] = useState<MatchingResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runMatch = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const matching = await api.matchInvoice(invoice.id);
      setResult(matching);
      onMatched(matching);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Erreur pendant le matching.");
    } finally {
      setBusy(false);
    }
  }, [invoice.id, onMatched]);

  const score = result?.score ?? invoice.matching_score ?? null;
  const purchaseOrderReference = result?.purchase_order_reference ?? null;
  const supplierMatch = result?.supplier_match ?? null;
  const duplicateFound = result?.duplicate_found ?? null;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader
          title="Rapprochement facture / bon de commande"
          subtitle={
            purchaseOrderReference
              ? `Bon de commande : ${purchaseOrderReference}`
              : "Comparaison des lignes, montants et TVA"
          }
          action={<span className="text-sm font-semibold text-slate-700">Score : {formatScore(score)}</span>}
        />
        <CardBody>
          {error && <Alert tone="danger" className="mb-4">{error}</Alert>}

          <div className="mb-4 flex flex-wrap gap-2">
            {supplierMatch !== null && (
              <Badge tone={supplierMatch ? "emerald" : "rose"}>
                {supplierMatch ? "Fournisseur conforme" : "Fournisseur différent"}
              </Badge>
            )}
            {duplicateFound !== null && (
              <Badge tone={duplicateFound ? "amber" : "slate"}>
                {duplicateFound ? "Doublon détecté" : "Aucun doublon"}
              </Badge>
            )}
          </div>

          <div className="flex justify-end">
            <Button onClick={runMatch} loading={busy}>
              {result ? "Relancer le matching" : "Lancer le matching"}
            </Button>
          </div>
        </CardBody>
      </Card>

      {result && (
        <Card>
          <CardHeader title="Comparaison des lignes" subtitle="Les écarts hors tolérance sont signalés" />
          <CardBody>
            <Table>
              <THead>
                <TH>N°</TH>
                <TH>Description</TH>
                <TH>Réf. produit</TH>
                <TH className="text-right">Qté facturée</TH>
                <TH className="text-right">Écart qté</TH>
                <TH className="text-right">PU HT</TH>
                <TH className="text-right">Écart prix</TH>
              </THead>
              <tbody>
                {result.lines.map((line) => (
                  <TR key={line.line_number}>
                    <TD>{line.line_number}</TD>
                    <TD className="max-w-xs truncate">{line.description}</TD>
                    <TD>{line.product_ref ?? "—"}</TD>
                    <TD className="text-right">{line.quantity ?? "—"}</TD>
                    <TD className="text-right">
                      <DeltaCell delta={line.quantity_delta} matched={line.quantity_matched} />
                    </TD>
                    <TD className="text-right">{line.unit_price ?? "—"}</TD>
                    <TD className="text-right">
                      <DeltaCell delta={line.unit_price_delta} matched={line.unit_price_matched} />
                    </TD>
                  </TR>
                ))}
              </tbody>
            </Table>
          </CardBody>
        </Card>
      )}

      {result && (
        <Card>
          <CardHeader title="Anomalies" subtitle="Écarts détectés lors du rapprochement" />
          <CardBody>
            {result.anomalies.length === 0 ? (
              <EmptyState title="Aucune anomalie" description="La facture est conforme au bon de commande." />
            ) : (
              <ul className="divide-y divide-slate-100">
                {result.anomalies.map((anomaly, index) => (
                  <li key={index} className="py-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <SeverityBadge severity={anomaly.severity} />
                      <CategoryBadge category={anomaly.category} />
                    </div>
                    <p className="mt-1 text-sm text-slate-800">{anomaly.message}</p>
                    {(anomaly.expected_value || anomaly.actual_value) && (
                      <p className="mt-0.5 text-xs text-slate-500">
                        Attendu : <span className="font-medium">{anomaly.expected_value ?? "—"}</span> · Reçu :{" "}
                        <span className="font-medium">{anomaly.actual_value ?? "—"}</span>
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>
      )}
    </div>
  );
}
