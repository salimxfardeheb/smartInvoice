"use client";

/** Garde de rôle : n'affiche le contenu que pour les rôles autorisés. */

import Link from "next/link";
import type { ReactNode } from "react";

import { useAuth } from "@/lib/auth";
import type { UserRole } from "@/types";
import { Alert } from "@/components/ui/Alert";
import { Card, CardBody } from "@/components/ui/Card";

export function RequireRole({
  roles,
  children,
}: {
  roles: UserRole[];
  children: ReactNode;
}) {
  const { user } = useAuth();
  if (!user || !roles.includes(user.role)) {
    return (
      <Card>
        <CardBody>
          <Alert tone="danger" title="Accès refusé">
            Vous n'avez pas les droits nécessaires pour consulter cette page.{" "}
            <Link href="/" className="font-medium underline">
              Retour au tableau de bord
            </Link>
          </Alert>
        </CardBody>
      </Card>
    );
  }
  return <>{children}</>;
}