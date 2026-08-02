/** Tests du journal d'audit. */

import { render, screen } from "@testing-library/react";
import { AuditLogTimeline } from "@/components/invoices/AuditLogTimeline";
import { makeAuditLogs } from "./fixtures";

describe("AuditLogTimeline", () => {
  test("affiche les actions dans l'ordre avec libellés et auteurs", () => {
    render(<AuditLogTimeline logs={makeAuditLogs()} />);

    expect(screen.getByText("Facture validée par le comptable.")).toBeInTheDocument();
    expect(screen.getByText("Données corrigées.")).toBeInTheDocument();
    expect(screen.getByText("Validation")).toBeInTheDocument();
    expect(screen.getByText("Correction")).toBeInTheDocument();
    expect(screen.getByText("Camille Dupont")).toBeInTheDocument();
    expect(screen.getByText("Détails techniques")).toBeInTheDocument();
  });

  test("gère un utilisateur supprimé", () => {
    const logs = makeAuditLogs();
    logs[0].user = null;
    render(<AuditLogTimeline logs={logs} />);
    expect(screen.getByText("Utilisateur supprimé")).toBeInTheDocument();
  });

  test("affiche un état vide", () => {
    render(<AuditLogTimeline logs={[]} />);
    expect(screen.getByText("Aucune action enregistrée")).toBeInTheDocument();
  });
});
