"use client";

import { useState } from "react";

import { ROLE_LABELS } from "@/lib/status";
import type { User, UserRole } from "@/types";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Input, Select } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";

const ROLES: UserRole[] = ["Comptable", "Acheteur", "Administrateur"];

interface CreateUserModalProps {
  open: boolean;
  onClose: () => void;
  onCreate: (payload: {
    username: string;
    email: string;
    password: string;
    full_name?: string;
    role: UserRole;
  }) => Promise<User | null>;
}

/** Modale de création d'un utilisateur (admin). */
export function CreateUserModal({ open, onClose, onCreate }: CreateUserModalProps) {
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [role, setRole] = useState<UserRole>("Comptable");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const canSubmit =
    username.trim().length >= 3 &&
    email.trim().length > 0 &&
    password.length >= 8;

  function reset() {
    setUsername("");
    setEmail("");
    setPassword("");
    setFullName("");
    setRole("Comptable");
    setError(null);
  }

  function handleClose() {
    reset();
    onClose();
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!canSubmit || busy) return;
    setBusy(true);
    setError(null);
    try {
      const created = await onCreate({
        username: username.trim(),
        email: email.trim(),
        password,
        full_name: fullName.trim() || undefined,
        role,
      });
      if (created) handleClose();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Création impossible.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={open}
      title="Créer un utilisateur"
      onClose={handleClose}
      footer={
        <>
          <Button variant="secondary" onClick={handleClose}>
            Annuler
          </Button>
          <Button type="submit" form="create-user-form" disabled={!canSubmit} loading={busy}>
            Créer
          </Button>
        </>
      }
    >
      {error && (
        <Alert tone="danger" className="mb-4">
          {error}
        </Alert>
      )}
      <form id="create-user-form" onSubmit={handleSubmit} className="space-y-4">
        <Input
          label="Identifiant *"
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          placeholder="ex. jdoe"
          maxLength={50}
          autoFocus
          required
        />
        <Input
          label="Email *"
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="ex. jdoe@entreprise.fr"
          required
        />
        <Input
          label="Mot de passe *"
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          hint="8 caractères minimum"
          minLength={8}
          required
        />
        <Input
          label="Nom complet"
          value={fullName}
          onChange={(event) => setFullName(event.target.value)}
          placeholder="ex. Jeanne Doe"
          maxLength={150}
        />
        <Select
          label="Rôle *"
          value={role}
          onChange={(event) => setRole(event.target.value as UserRole)}
          options={ROLES.map((r) => ({ value: r, label: ROLE_LABELS[r] }))}
        />
      </form>
    </Modal>
  );
}