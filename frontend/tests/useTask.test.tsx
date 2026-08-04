/** Tests du hook de polling des tâches asynchrones. */

import { act, render, screen } from "@testing-library/react";
import { useTaskPolling } from "@/hooks/useTask";
import { api } from "@/lib/api-client";
import type { OcrTask } from "@/types";

jest.mock("@/lib/api-client", () => ({
  api: { getTask: jest.fn() },
}));

const getTask = (api as jest.Mocked<typeof api>).getTask;

function makeTask(state: OcrTask["state"]): OcrTask {
  return {
    id: 1,
    kind: "ocr",
    state,
    invoice_id: 1,
    error_message: null,
    result: null,
    started_at: null,
    finished_at: null,
    created_at: "2026-01-16T10:00:00",
  };
}

function Harness({ taskId, onSettled }: { taskId: number | null; onSettled?: (t: OcrTask) => void }) {
  const { task, running } = useTaskPolling(taskId, onSettled);
  return (
    <div>
      <span>{running ? "running" : "idle"}</span>
      <span>{task?.state ?? "none"}</span>
    </div>
  );
}

describe("useTaskPolling", () => {
  beforeEach(() => {
    jest.useFakeTimers();
    jest.clearAllMocks();
  });
  afterEach(() => jest.useRealTimers());

  test("ne démarre pas avec un taskId null", () => {
    render(<Harness taskId={null} />);
    expect(screen.getByText("idle")).toBeInTheDocument();
    expect(screen.getByText("none")).toBeInTheDocument();
    expect(getTask).not.toHaveBeenCalled();
  });

  test("poll jusqu'au succès puis notifie", async () => {
    const onSettled = jest.fn();
    getTask
      .mockResolvedValueOnce(makeTask("en attente"))
      .mockResolvedValueOnce(makeTask("en cours"))
      .mockResolvedValueOnce(makeTask("réussi"));

    render(<Harness taskId={1} onSettled={onSettled} />);
    expect(screen.getByText("running")).toBeInTheDocument();

    await act(async () => {
      jest.advanceTimersByTime(2000);
    });
    await act(async () => {
      jest.advanceTimersByTime(2000);
    });
    await act(async () => {
      jest.advanceTimersByTime(2000);
    });

    expect(screen.getByText("idle")).toBeInTheDocument();
    expect(screen.getByText("réussi")).toBeInTheDocument();
    expect(onSettled).toHaveBeenCalledWith(expect.objectContaining({ state: "réussi" }));
    expect(getTask).toHaveBeenCalledTimes(3);
  });

  test("arrête le polling en cas d'échec", async () => {
    getTask.mockResolvedValueOnce(makeTask("échoué"));

    render(<Harness taskId={1} />);
    await act(async () => {});

    expect(screen.getByText("idle")).toBeInTheDocument();
    expect(screen.getByText("échoué")).toBeInTheDocument();
    expect(getTask).toHaveBeenCalledTimes(1);
  });
});