/** Tests des composants du tableau de bord. */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StatusOverview, PendingAnomalies } from "@/components/dashboard/DashboardComponents";
import { makeSummary } from "./fixtures";

const pushMock = jest.fn();

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

jest.mock("next/link", () => {
  const Link = ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  );
  return Link;
});

describe("StatusOverview", () => {
  beforeEach(() => pushMock.mockClear());

  test("affiche le compte par statut et le total", () => {
    render(<StatusOverview summary={makeSummary()} />);
    expect(screen.getByText("14 facture(s) au total")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument(); // Déposée
    expect(screen.getByText("5")).toBeInTheDocument(); // Validée
  });

  test("navigue vers la liste filtrée au clic", async () => {
    const user = userEvent.setup();
    render(<StatusOverview summary={makeSummary()} />);
    await user.click(screen.getByRole("button", { name: /Validée/ }));
    expect(decodeURIComponent(pushMock.mock.calls[0][0])).toBe("/invoices?status=Validée");
  });
});

describe("PendingAnomalies", () => {
  test("liste les anomalies en attente avec lien de traitement", () => {
    render(<PendingAnomalies summary={makeSummary()} />);
    expect(screen.getByText("Quantité différente du bon de commande.")).toBeInTheDocument();
    expect(screen.getByText(/FAC-2026-001/)).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /Traiter/ });
    expect(link).toHaveAttribute("href", "/invoices/1/validation");
  });

  test("affiche un message quand tout est résolu", () => {
    const summary = makeSummary();
    summary.pending_anomalies = [];
    render(<PendingAnomalies summary={summary} />);
    expect(screen.getByText("Aucune anomalie en attente")).toBeInTheDocument();
  });
});
