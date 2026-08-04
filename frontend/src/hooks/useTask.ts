"use client";

/** Polling de l'état d'une tâche asynchrone (OCR / ré-analyse). */

import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "@/lib/api-client";
import type { OcrTask } from "@/types";

const POLL_INTERVAL_MS = 2000;

/**
 * Interroge la tâche `taskId` toutes les 2 s jusqu'à son terme
 * (`réussi`/`échoué`). `onSettled` est appelé avec la tâche finale.
 */
export function useTaskPolling(
  taskId: number | null,
  onSettled?: (task: OcrTask) => void,
): { task: OcrTask | null; running: boolean } {
  const [task, setTask] = useState<OcrTask | null>(null);
  const onSettledRef = useRef(onSettled);
  onSettledRef.current = onSettled;

  const pollOnce = useCallback(async (id: number): Promise<OcrTask> => {
    const fetched = await api.getTask(id);
    setTask(fetched);
    return fetched;
  }, []);

  useEffect(() => {
    if (taskId === null) {
      setTask(null);
      return;
    }
    let cancelled = false;
    let interval: ReturnType<typeof setInterval> | null = null;
    const id = taskId;

    async function start() {
      let settled = false;
      try {
        const initial = await pollOnce(id);
        settled = initial.state === "réussi" || initial.state === "échoué";
        if (settled) {
          onSettledRef.current?.(initial);
          return;
        }
      } catch {
        cancelled = true;
        return;
      }
      if (cancelled) return;

      interval = setInterval(async () => {
        try {
          const fetched = await pollOnce(id);
          settled = fetched.state === "réussi" || fetched.state === "échoué";
          if (settled) {
            onSettledRef.current?.(fetched);
            if (interval) clearInterval(interval);
          }
        } catch {
          if (interval) clearInterval(interval);
        }
      }, POLL_INTERVAL_MS);
    }

    void start();

    return () => {
      cancelled = true;
      if (interval) clearInterval(interval);
    };
  }, [taskId, pollOnce]);

  return { task, running: taskId !== null && task === null };
}