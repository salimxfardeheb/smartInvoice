"use client";

import { useMemo, useState } from "react";

import { AppShell } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { AnomaliesTable } from "@/components/anomalies/AnomaliesTable";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/Page";
import { Pagination } from "@/components/ui/Pagination";
import { Select } from "@/components/ui/Input";
import { Spinner } from "@/components/ui/Spinner";
import { useAnomalies, useResolveAnomaly } from "@/hooks/useAdmin";
import { PAGE_SIZE } from "@/lib/config";
import type { AnomalySeverity } from "@/types";

export default function AnomaliesPage() {
  return (
    <RequireAuth>
      <AppShell>
        <AnomaliesContent />
      </AppShell>
    </RequireAuth>
  );
}

function AnomaliesContent() {
  const [resolved, setResolved] = useState<"pending" | "resolved" | "all">("pending");
  const [severity, setSeverity] = useState<string>("");
  const [page, setPage] = useState(1);

  const filters = useMemo(
    () => ({
      resolved: resolved === "all" ? undefined : resolved === "resolved",
      severity: severity || undefined,
    }),
    [resolved, severity],
  );

  const { anomalies, total, loading, error, reload } = useAnomalies(filters, PAGE_SIZE, (page - 1) * PAGE_SIZE);
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const resolve = useResolveAnomaly(reload);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Anomalies"
        description="Anomalies de matching issues de la synchronisation"
        actions={
          <Button variant="secondary" onClick={reload} disabled={loading}>
            Actualiser
          </Button>
        }
      >
        {error && <Alert tone="danger">{error}</Alert>}
        {resolve.error && <Alert tone="danger">{resolve.error}</Alert>}
      </PageHeader>

      <Card>
        <CardHeader
          title="Liste des anomalies"
          subtitle={`${total} anomalie(s)`}
          action={
            <div className="flex items-center gap-2">
              <Select
                aria-label="État"
                options={[
                  { value: "pending", label: "En attente" },
                  { value: "all", label: "Toutes" },
                  { value: "resolved", label: "Résolues" },
                ]}
                value={resolved}
                onChange={(event) => {
                  setResolved(event.target.value as typeof resolved);
                  setPage(1);
                }}
              />
              <Select
                aria-label="Sévérité"
                options={[
                  { value: "", label: "Toutes sévérités" },
                  { value: "critical", label: "Critique" },
                  { value: "warning", label: "Avertissement" },
                  { value: "info", label: "Info" },
                ]}
                value={severity}
                onChange={(event) => {
                  setSeverity(event.target.value);
                  setPage(1);
                }}
              />
            </div>
          }
        />
        <CardBody>
          {loading ? (
            <Spinner label="Chargement des anomalies…" />
          ) : (
            <>
              <AnomaliesTable
                anomalies={anomalies}
                busy={resolve.busy}
                onResolve={(anomaly) => resolve.run(anomaly.id)}
              />
              <div className="mt-4">
                <Pagination
                  page={page}
                  pageCount={pageCount}
                  total={total}
                  pageSize={PAGE_SIZE}
                  onChange={setPage}
                />
              </div>
            </>
          )}
        </CardBody>
      </Card>
    </div>
  );
}