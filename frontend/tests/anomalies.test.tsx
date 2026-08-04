/** Tests du tableau de traitement des anomalies. */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AnomaliesTable } from "@/components/anomalies/AnomaliesTable";
import { makeAnomaly } from "./fixtures";

jest.mock("next/link", () => {
  const Link = ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  );
  return Link;
});

describe("AnomaliesTable", () => {
  test("affiche les détails d'une anomalie en attente", () => {
    render(
      <AnomaliesTable anomalies={[makeAnomaly()]} busy={false} onResolve={jest.fn()} />,
    );
    expect(screen.getByText("Quantité différente du bon de commande.")).toBeInTheDocument();
    expect(screen.getByText("Avertissement")).toBeInTheDocument();
    expect(screen.getByText("Quantité")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "FAC-2026-001" })).toHaveAttribute(
      "href",
      "/invoices/1/matching",
    );
  });

  test("marque une anomalie résolue via le bouton", async () => {
    const user = userEvent.setup();
    const onResolve = jest.fn();
    render(<AnomaliesTable anomalies={[makeAnomaly()]} busy={false} onResolve={onResolve} />);

    await user.click(screen.getByRole("button", { name: "Marquer résolue" }));
    expect(onResolve).toHaveBeenCalledWith(expect.objectContaining({ id: 1 }));
  });

  test("une anomalie résolue affiche la date et un lien vers la facture", () => {
    render(
      <AnomaliesTable
        anomalies={[
          makeAnomaly({ resolved: true, resolved_at: "2026-01-20T10:00:00" }),
        ]}
        busy={false}
        onResolve={jest.fn()}
      />,
    );
    expect(screen.getByText(/Résolue le/)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Marquer résolue" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Voir la facture/ })).toHaveAttribute(
      "href",
      "/invoices/1/validation",
    );
  });

  test("affiche un état vide", () => {
    render(<AnomaliesTable anomalies={[]} busy={false} onResolve={jest.fn()} />);
    expect(screen.getByText("Aucune anomalie")).toBeInTheDocument();
  });

  test("désactive le bouton pendant l'action", () => {
    render(<AnomaliesTable anomalies={[makeAnomaly()]} busy onResolve={jest.fn()} />);
    expect(screen.getByRole("button", { name: "Marquer résolue" })).toBeDisabled();
  });
});