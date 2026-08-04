"use client";

import { AppShell } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { OdooSyncPanel } from "@/components/odoo/OdooSyncPanel";
import { Alert } from "@/components/ui/Alert";
import { PageHeader } from "@/components/ui/Page";

export default function OdooSyncPage() {
  return (
    <RequireAuth>
      <AppShell>
        <div className="space-y-6">
          <PageHeader
            title="Synchronisation Odoo"
            description="Importez les fournisseurs et les bons de commande depuis Odoo"
          />
<Alert tone="info" title="Périmètre">
            La synchronisation est limitée aux éléments fournis : nom de
            fournisseur ou référence de bon de commande. Les résultats sont
            affichés ci-dessous.
          </Alert>
          <OdooSyncPanel />
        </div>
      </AppShell>
    </RequireAuth>
  );
}