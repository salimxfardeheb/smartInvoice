"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";

import { AppShell } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { InvoiceFilters } from "@/components/invoices/InvoiceFilters";
import { InvoiceTable } from "@/components/invoices/InvoiceTable";
import { useKnownSuppliers } from "@/components/invoices/UploadForm";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/Page";
import { Pagination } from "@/components/ui/Pagination";
import { Spinner } from "@/components/ui/Spinner";
import { useInvoices } from "@/hooks/useInvoices";
import { PAGE_SIZE } from "@/lib/config";
import type { InvoiceFilters as Filters } from "@/types";

export default function InvoicesPage() {
  return (
    <RequireAuth>
      <AppShell>
        <Suspense fallback={<Spinner label="Chargement des factures…" />}>
          <InvoicesList />
        </Suspense>
      </AppShell>
    </RequireAuth>
  );
}

function InvoicesList() {
  const searchParams = useSearchParams();
  const statusFromUrl = searchParams.get("status") ?? undefined;

  const [filters, setFilters] = useState<Filters>(() =>
    statusFromUrl ? { status: statusFromUrl as Filters["status"] } : {},
  );
  const [page, setPage] = useState(1);
  const { suppliers } = useKnownSuppliers();

  // Synchronise les filtres quand on vient du tableau de bord (?status=).
  useEffect(() => {
    if (statusFromUrl) {
      setFilters((previous) => ({ ...previous, status: statusFromUrl as Filters["status"] }));
      setPage(1);
    }
  }, [statusFromUrl]);

  const offset = useMemo(() => (page - 1) * PAGE_SIZE, [page]);
  const { invoices, total, loading, error, reload } = useInvoices(filters, PAGE_SIZE, offset);
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  function handleFilterChange(next: Filters) {
    setFilters(next);
    setPage(1);
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Factures"
        description="Historique, filtres et suivi des factures déposées"
        actions={
          <Link href="/invoices/upload">
            <Button>Déposer une facture</Button>
          </Link>
        }
      />

      <InvoiceFilters filters={filters} suppliers={suppliers} onChange={handleFilterChange} />

      {error && <Alert tone="danger">{error}</Alert>}

      {loading ? (
        <Spinner label="Chargement des factures…" />
      ) : (
        <>
          <InvoiceTable invoices={invoices} />
          <Pagination
            page={page}
            pageCount={pageCount}
            total={total}
            pageSize={PAGE_SIZE}
            onChange={setPage}
          />
        </>
      )}

      {!loading && total === 0 && !error && (
        <EmptyState
          title="Aucune facture"
          description="Commencez par déposer une facture."
          action={
            <Link href="/invoices/upload">
              <Button>Déposer une facture</Button>
            </Link>
          }
        />
      )}

      <p className="text-xs text-slate-400">
        <Link href="/" className="text-brand-600 hover:underline">
          Retour au tableau de bord
        </Link>
      </p>
    </div>
  );
}
