"use client";

import Link from "next/link";

import { AppShell } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { PendingAnomalies, StatusOverview } from "@/components/dashboard/DashboardComponents";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { PageHeader } from "@/components/ui/Page";
import { Spinner } from "@/components/ui/Spinner";
import { useSummary } from "@/hooks/useInvoices";

export default function DashboardPage() {
  return (
    <RequireAuth>
      <AppShell>
        <DashboardContent />
      </AppShell>
    </RequireAuth>
  );
}

function DashboardContent() {
  const { summary, loading, error, reload } = useSummary();

  if (loading) return <Spinner label="Chargement du tableau de bord…" />;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Tableau de bord"
        description="Vue d'ensemble des factures et des anomalies en attente"
        actions={
          <Button
            variant="secondary"
            onClick={reload}
            disabled={loading}
            aria-label="Actualiser le tableau de bord"
          >
            Actualiser
          </Button>
        }
      >
        {error && <Alert tone="danger">{error}</Alert>}
      </PageHeader>

      {summary && (
        <>
          <StatusOverview summary={summary} />
          <PendingAnomalies summary={summary} />
        </>
      )}

      <p className="text-xs text-slate-400">
        <Link href="/invoices" className="text-brand-600 hover:underline">
          Voir toutes les factures
        </Link>
        {" · "}
        <Link href="/invoices/upload" className="text-brand-600 hover:underline">
          Déposer une facture
        </Link>
      </p>
    </div>
  );
}
