"use client";

import { useState } from "react";

import { AppShell } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { RequireRole } from "@/components/layout/RequireRole";
import { CreateUserModal } from "@/components/users/CreateUserModal";
import { UsersTable } from "@/components/users/UsersTable";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/Page";
import { Spinner } from "@/components/ui/Spinner";
import { useUsers } from "@/hooks/useAdmin";
import { useAction } from "@/hooks/useAsync";
import { useAuth } from "@/lib/auth";
import { api } from "@/lib/api-client";
import type { User, UserRole } from "@/types";

export default function UsersPage() {
  return (
    <RequireAuth>
      <AppShell>
        <RequireRole roles={["Administrateur"]}>
          <UsersContent />
        </RequireRole>
      </AppShell>
    </RequireAuth>
  );
}

function UsersContent() {
  const { user: currentUser } = useAuth();
  const { users, loading, error, reload } = useUsers();
  const [createOpen, setCreateOpen] = useState(false);

  const create = useAction(async (payload: Parameters<typeof api.createUser>[0]) => {
    const created = await api.createUser(payload);
    reload();
    return created;
  });

  const toggleActive = useAction(async (target: User) => {
    const updated = target.is_active
      ? await api.deactivateUser(target.id)
      : await api.updateUser(target.id, { is_active: true });
    reload();
    return updated;
  });

  const changeRole = useAction(async (target: User, role: UserRole) => {
    const updated = await api.updateUser(target.id, { role });
    reload();
    return updated;
  });

  if (loading) return <Spinner label="Chargement des utilisateurs…" />;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Gestion des utilisateurs"
        description="Comptes, rôles et activation des accès"
        actions={
          <Button onClick={() => setCreateOpen(true)}>Créer un utilisateur</Button>
        }
      >
        {error && <Alert tone="danger">{error}</Alert>}
        {(create.error || toggleActive.error || changeRole.error) && (
          <Alert tone="danger">
            {create.error ?? toggleActive.error ?? changeRole.error}
          </Alert>
        )}
      </PageHeader>

      <Card>
        <CardHeader
          title="Utilisateurs"
          subtitle={`${users.length} compte(s) enregistré(s)`}
        />
        <CardBody>
          <UsersTable
            users={users}
            currentUserId={currentUser?.id ?? null}
            busy={create.busy || toggleActive.busy || changeRole.busy}
            onRoleChange={(target, role) => changeRole.run(target, role)}
            onToggleActive={(target) => toggleActive.run(target)}
          />
        </CardBody>
      </Card>

      <CreateUserModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreate={create.run}
      />
    </div>
  );
}