"use client";

import { ROLE_LABELS, ROLE_TONES } from "@/lib/status";
import { formatDateTime } from "@/lib/format";
import type { User, UserRole } from "@/types";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Table, TD, TH, THead, TR } from "@/components/ui/Table";

/** Tableau des utilisateurs avec gestion du rôle et activation/désactivation. */
export function UsersTable({
  users,
  currentUserId,
  busy,
  onRoleChange,
  onToggleActive,
}: {
  users: User[];
  currentUserId: number | null;
  busy: boolean;
  onRoleChange: (user: User, role: UserRole) => void;
  onToggleActive: (user: User) => void;
}) {
  if (users.length === 0) {
    return (
      <EmptyState
        title="Aucun utilisateur"
        description="Créez un utilisateur pour lui donner accès à l'interface."
      />
    );
  }

  return (
    <Table>
      <THead>
        <TH>Utilisateur</TH>
        <TH>Rôle</TH>
        <TH>État</TH>
        <TH>Créé le</TH>
        <TH className="text-right">Actions</TH>
      </THead>
      <tbody>
        {users.map((user) => {
          const isSelf = user.id === currentUserId;
          return (
            <TR key={user.id}>
              <TD>
                <p className="font-medium text-slate-900">{user.full_name ?? user.username}</p>
                <p className="text-xs text-slate-500">
                  @{user.username} · {user.email}
                </p>
              </TD>
              <TD>
                <label className="sr-only" htmlFor={`role-${user.id}`}>
                  Rôle de {user.full_name ?? user.username}
                </label>
                <select
                  id={`role-${user.id}`}
                  value={user.role}
                  disabled={isSelf || busy || !user.is_active}
                  onChange={(event) =>
                    onRoleChange(user, event.target.value as UserRole)
                  }
                  className="rounded-md border border-slate-300 bg-white px-2 py-1 text-xs text-slate-700 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/30 disabled:opacity-50"
                >
                  {Object.keys(ROLE_LABELS).map((role) => (
                    <option key={role} value={role}>
                      {ROLE_LABELS[role as UserRole]}
                    </option>
                  ))}
                </select>
              </TD>
              <TD>
                <Badge tone={user.is_active ? "emerald" : "rose"}>
                  {user.is_active ? "Actif" : "Désactivé"}
                </Badge>
              </TD>
              <TD>
                <span className="text-xs text-slate-500">{formatDateTime(user.created_at)}</span>
              </TD>
              <TD className="text-right">
                <span className="mr-2 hidden text-xs text-slate-400 sm:inline">
                  {ROLE_LABELS[user.role]}
                </span>
                <Button
                  variant={user.is_active ? "danger" : "success"}
                  size="sm"
                  disabled={isSelf || busy}
                  onClick={() => onToggleActive(user)}
                >
                  {user.is_active ? "Désactiver" : "Réactiver"}
                </Button>
              </TD>
            </TR>
          );
        })}
      </tbody>
    </Table>
  );
}