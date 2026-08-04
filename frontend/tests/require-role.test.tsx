/** Tests de la garde de rôle. */

import { render, screen } from "@testing-library/react";
import { RequireRole } from "@/components/layout/RequireRole";
import { useAuth } from "@/lib/auth";

jest.mock("@/lib/auth", () => ({
  useAuth: jest.fn(),
}));

jest.mock("next/link", () => {
  const Link = ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  );
  return Link;
});

const mockedUseAuth = useAuth as jest.Mock;

describe("RequireRole", () => {
  test("affiche le contenu pour un rôle autorisé", () => {
    mockedUseAuth.mockReturnValue({ user: { role: "Administrateur" } });
    render(<RequireRole roles={["Administrateur"]}><p>Panneau admin</p></RequireRole>);
    expect(screen.getByText("Panneau admin")).toBeInTheDocument();
  });

  test("refuse l'accès à un rôle non autorisé", () => {
    mockedUseAuth.mockReturnValue({ user: { role: "Acheteur" } });
    render(<RequireRole roles={["Administrateur"]}><p>Panneau admin</p></RequireRole>);
    expect(screen.getByText("Accès refusé")).toBeInTheDocument();
    expect(screen.queryByText("Panneau admin")).not.toBeInTheDocument();
  });

  test("refuse l'accès sans utilisateur", () => {
    mockedUseAuth.mockReturnValue({ user: null });
    render(<RequireRole roles={["Administrateur"]}><p>Panneau admin</p></RequireRole>);
    expect(screen.getByText("Accès refusé")).toBeInTheDocument();
  });
});