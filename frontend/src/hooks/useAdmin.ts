"use client";

/** Hooks d'accès aux données d'administration (utilisateurs, anomalies). */

import { useCallback } from "react";

import { api } from "@/lib/api-client";
import type { Anomaly, AnomalyListResponse, User } from "@/types";
import { useAction, useAsyncData } from "@/hooks/useAsync";

export function useUsers(): {
  users: User[];
  loading: boolean;
  error: string | null;
  reload: () => void;
} {
  const loader = useCallback(() => api.listUsers(), []);
  const state = useAsyncData<User[]>(loader, []);
  return { users: state.data ?? [], loading: state.loading, error: state.error, reload: state.reload };
}

export function useAnomalies(
  filters: { resolved?: boolean; severity?: string; category?: string },
  limit: number,
  offset: number,
): {
  anomalies: Anomaly[];
  total: number;
  loading: boolean;
  error: string | null;
  reload: () => void;
} {
  const { resolved, severity, category } = filters;
  const loader = useCallback(
    () => api.listAnomalies({ resolved, severity, category }, limit, offset),
    [resolved, severity, category, limit, offset],
  );
  const state = useAsyncData<AnomalyListResponse>(loader, [
    resolved,
    severity,
    category,
    limit,
    offset,
  ]);
  return {
    anomalies: state.data?.items ?? [],
    total: state.data?.total ?? 0,
    loading: state.loading,
    error: state.error,
    reload: state.reload,
  };
}

/** Action : résout une anomalie puis rappelle `onDone`. */
export function useResolveAnomaly(onDone: (anomaly: Anomaly) => void) {
  return useAction(async (id: number) => {
    const anomaly = await api.resolveAnomaly(id);
    onDone(anomaly);
    return anomaly;
  });
}