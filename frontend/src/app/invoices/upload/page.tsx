"use client";

import Link from "next/link";

import { AppShell } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { UploadForm, useKnownSuppliers } from "@/components/invoices/UploadForm";
import { Alert } from "@/components/ui/Alert";
import { PageHeader } from "@/components/ui/Page";

export default function UploadPage() {
  return (
    <RequireAuth>
      <AppShell>
        <UploadContent />
      </AppShell>
    </RequireAuth>
  );
}

function UploadContent() {
  const { suppliers, loading } = useKnownSuppliers();

  return (
    <div className="space-y-6">
      <PageHeader
        title="Déposer une facture"
        description="Envoyez le document source et renseignez les métadonnées"
      />
      {loading ? (
        <p className="text-sm text-slate-500">Chargement des fournisseurs…</p>
      ) : suppliers.length === 0 ? (
        <Alert tone="warning" title="Aucun fournisseur connu">
          Aucun fournisseur n'a encore été associé à une facture. Renseignez
          l'identifiant fournisseur{" "}
          <Link href="/invoices" className="font-medium underline">
            depuis la liste des factures
          </Link>{" "}
          ou après une première synchronisation Odoo.
        </Alert>
      ) : null}
      <UploadForm suppliers={suppliers} />
    </div>
  );
}
