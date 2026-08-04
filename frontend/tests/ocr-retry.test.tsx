/** Tests du bouton « Réanalyser » sur les factures en erreur système. */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { OcrPanel } from "@/components/invoices/OcrPanel";
import { api } from "@/lib/api-client";
import type { OcrTask } from "@/types";
import { makeInvoice } from "./fixtures";

jest.mock("@/lib/api-client", () => ({
  api: { processInvoice: jest.fn(), retryInvoice: jest.fn(), getTask: jest.fn() },
}));

let taskForPolling: OcrTask | null = null;
jest.mock("@/hooks/useTask", () => ({
  useTaskPolling: (taskId: number | null) => ({
    task: taskId === null ? null : taskForPolling,
    running: taskId !== null && taskForPolling === null,
  }),
}));

const mockedApi = api as jest.Mocked<typeof api>;

function makeTask(state: OcrTask["state"], overrides: Partial<OcrTask> = {}): OcrTask {
  return {
    id: 5,
    kind: "ocr",
    state,
    invoice_id: 1,
    error_message: null,
    result: null,
    started_at: "2026-01-16T10:00:00",
    finished_at: null,
    created_at: "2026-01-16T10:00:00",
    ...overrides,
  };
}

describe("OcrPanel ré-analyse", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    taskForPolling = null;
  });

  test("affiche « Réanalyser » sur une facture en erreur système", () => {
    render(<OcrPanel invoice={makeInvoice({ status: "Erreur système" })} onProcessed={jest.fn()} />);
    expect(screen.getByRole("button", { name: "Réanalyser" })).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Lancer l'analyse OCR" }),
    ).not.toBeInTheDocument();
  });

  test("n'affiche pas « Réanalyser » sur une facture déposée", () => {
    render(<OcrPanel invoice={makeInvoice({ status: "Déposée" })} onProcessed={jest.fn()} />);
    expect(screen.getByRole("button", { name: "Lancer l'analyse OCR" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Réanalyser" })).not.toBeInTheDocument();
  });

  test("déclenche la ré-analyse et notifie le parent à la fin", async () => {
    const user = userEvent.setup();
    mockedApi.retryInvoice.mockResolvedValue(makeTask("en cours"));
    const onProcessed = jest.fn();
    taskForPolling = makeTask("réussi", { result: { invoice_id: 1, status: "À vérifier" } });

    render(<OcrPanel invoice={makeInvoice({ status: "Erreur système" })} onProcessed={onProcessed} />);

    await user.click(screen.getByRole("button", { name: "Réanalyser" }));

    await waitFor(() => {
      expect(mockedApi.retryInvoice).toHaveBeenCalledWith(1);
      expect(onProcessed).toHaveBeenCalled();
    });
  });

  test("affiche le message d'erreur si la ré-analyse échoue", async () => {
    const user = userEvent.setup();
    mockedApi.retryInvoice.mockResolvedValue(makeTask("en cours"));
    taskForPolling = makeTask("échoué", { error_message: "OCR indisponible." });

    render(<OcrPanel invoice={makeInvoice({ status: "Erreur système" })} onProcessed={jest.fn()} />);

    await user.click(screen.getByRole("button", { name: "Réanalyser" }));
    expect(await screen.findByText("OCR indisponible.")).toBeInTheDocument();
    expect(screen.getByText("La ré-analyse a échoué")).toBeInTheDocument();
  });
});