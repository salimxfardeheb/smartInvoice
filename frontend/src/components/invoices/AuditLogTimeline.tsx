"use client";

import type { AuditLog } from "@/types";
import { ACTION_LABELS } from "@/lib/status";
import { formatDateTime } from "@/lib/format";
import { ActionBadge } from "@/components/ui/badges";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";

/** Journal d'audit d'une facture (chronologie des actions). */
export function AuditLogTimeline({ logs }: { logs: AuditLog[] }) {
  if (logs.length === 0) {
    return (
      <Card>
        <CardHeader title="Historique" />
        <CardBody>
          <EmptyState title="Aucune action enregistrée" description="Le journal est vide pour cette facture." />
        </CardBody>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader title="Historique des actions" subtitle="Qui, quand, quoi — journal d'audit" />
      <CardBody>
        <ol className="relative ml-3 space-y-6 border-l border-slate-200 pl-6">
          {logs.map((log) => (
            <li key={log.id} className="relative">
              <span
                aria-hidden
                className="absolute -left-[31px] top-1.5 h-3 w-3 rounded-full bg-brand-500 ring-4 ring-white"
              />
              <div className="flex flex-wrap items-center gap-2">
                <ActionBadge action={log.action} />
                <span className="text-xs text-slate-500">{formatDateTime(log.created_at)}</span>
              </div>
              <p className="mt-1 text-sm text-slate-800">{log.message}</p>
              <p className="mt-0.5 text-xs text-slate-500">
                {log.user ? (
                  <>
                    Par <span className="font-medium">{log.user.full_name ?? log.user.username}</span>
                  </>
                ) : (
                  "Utilisateur supprimé"
                )}
              </p>
              {log.details && (
                <details className="mt-1">
                  <summary className="cursor-pointer text-xs font-medium text-brand-600 hover:underline">
                    Détails techniques
                  </summary>
                  <pre className="mt-2 overflow-x-auto rounded bg-slate-50 p-3 text-xs text-slate-600">
                    {JSON.stringify(log.details, null, 2)}
                  </pre>
                </details>
              )}
            </li>
          ))}
        </ol>
      </CardBody>
    </Card>
  );
}

/** Utilitaire : libellé lisible d'une action (exporté pour les tests). */
export function actionLabel(action: AuditLog["action"]): string {
  return ACTION_LABELS[action] ?? action;
}
