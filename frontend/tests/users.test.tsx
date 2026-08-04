/** Tests de la gestion des utilisateurs (table + création). */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { UsersTable } from "@/components/users/UsersTable";
import { CreateUserModal } from "@/components/users/CreateUserModal";
import { makeUser } from "./fixtures";

describe("UsersTable", () => {
  test("affiche les utilisateurs avec leur rôle et état", () => {
    render(
      <UsersTable
        users={[makeUser({ id: 1, username: "salim", full_name: "Salim Admin", role: "Administrateur" })]}
        currentUserId={2}
        busy={false}
        onRoleChange={jest.fn()}
        onToggleActive={jest.fn()}
      />,
    );

    expect(screen.getByText("Salim Admin")).toBeInTheDocument();
    expect(screen.getByText(/@salim/)).toBeInTheDocument();
    expect(screen.getByLabelText("Rôle de Salim Admin")).toHaveValue("Administrateur");
    expect(screen.getByText("Actif")).toBeInTheDocument();
  });

  test("affiche l'état désactivé et ne permet pas de désactiver son propre compte", () => {
    render(
      <UsersTable
        users={[makeUser({ id: 1, username: "salim", full_name: null, is_active: true })]}
        currentUserId={1}
        busy={false}
        onRoleChange={jest.fn()}
        onToggleActive={jest.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: "Désactiver" })).toBeDisabled();
    expect(screen.getByLabelText("Rôle de salim")).toBeDisabled();
  });

  test("réactive un utilisateur désactivé", async () => {
    const user = userEvent.setup();
    const onToggleActive = jest.fn();
    render(
      <UsersTable
        users={[makeUser({ id: 3, username: "comptable", is_active: false })]}
        currentUserId={1}
        busy={false}
        onRoleChange={jest.fn()}
        onToggleActive={onToggleActive}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Réactiver" }));
    expect(onToggleActive).toHaveBeenCalledWith(expect.objectContaining({ id: 3 }));
  });

  test("notifie le changement de rôle", async () => {
    const user = userEvent.setup();
    const onRoleChange = jest.fn();
    render(
      <UsersTable
        users={[makeUser({ id: 3, username: "comptable", full_name: null })]}
        currentUserId={1}
        busy={false}
        onRoleChange={onRoleChange}
        onToggleActive={jest.fn()}
      />,
    );

    await user.selectOptions(screen.getByLabelText("Rôle de comptable"), "Acheteur");
    expect(onRoleChange).toHaveBeenCalledWith(
      expect.objectContaining({ id: 3 }),
      "Acheteur",
    );
  });

  test("affiche un état vide", () => {
    render(
      <UsersTable
        users={[]}
        currentUserId={null}
        busy={false}
        onRoleChange={jest.fn()}
        onToggleActive={jest.fn()}
      />,
    );
    expect(screen.getByText("Aucun utilisateur")).toBeInTheDocument();
  });
});

describe("CreateUserModal", () => {
  test("le bouton reste désactivé tant que le mot de passe est trop court", async () => {
    const user = userEvent.setup();
    render(<CreateUserModal open onClose={jest.fn()} onCreate={jest.fn()} />);

    await user.type(screen.getByLabelText("Identifiant *"), "jdoe");
    await user.type(screen.getByLabelText("Email *"), "jdoe@x.io");
    await user.type(screen.getByLabelText(/Mot de passe/), "court");
    await user.selectOptions(screen.getByLabelText(/Rôle/), "Comptable");

    expect(screen.getByRole("button", { name: "Créer" })).toBeDisabled();
  });

  test("crée un utilisateur avec le rôle choisi", async () => {
    const user = userEvent.setup();
    const onCreate = jest.fn().mockResolvedValue({ id: 5 });
    render(<CreateUserModal open onClose={jest.fn()} onCreate={onCreate} />);

    await user.type(screen.getByLabelText("Identifiant *"), "jdoe");
    await user.type(screen.getByLabelText("Email *"), "jdoe@x.io");
    await user.type(screen.getByLabelText(/Mot de passe/), "password123");
    await user.type(screen.getByLabelText("Nom complet"), "Jeanne Doe");
    await user.selectOptions(screen.getByLabelText(/Rôle/), "Acheteur");
    await user.click(screen.getByRole("button", { name: "Créer" }));

    await waitFor(() => {
      expect(onCreate).toHaveBeenCalledWith({
        username: "jdoe",
        email: "jdoe@x.io",
        password: "password123",
        full_name: "Jeanne Doe",
        role: "Acheteur",
      });
    });
  });

  test("affiche l'erreur renvoyée par le serveur", async () => {
    const user = userEvent.setup();
    const onCreate = jest.fn().mockRejectedValue(new Error("Identifiant déjà pris."));
    render(<CreateUserModal open onClose={jest.fn()} onCreate={onCreate} />);

    await user.type(screen.getByLabelText("Identifiant *"), "jdoe");
    await user.type(screen.getByLabelText("Email *"), "jdoe@x.io");
    await user.type(screen.getByLabelText(/Mot de passe/), "password123");
    await user.click(screen.getByRole("button", { name: "Créer" }));

    expect(await screen.findByText("Identifiant déjà pris.")).toBeInTheDocument();
  });

  test("n'affiche rien quand la modale est fermée", () => {
    render(<CreateUserModal open={false} onClose={jest.fn()} onCreate={jest.fn()} />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});