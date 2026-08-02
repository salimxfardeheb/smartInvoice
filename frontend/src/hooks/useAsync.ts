"use client";

/** Hook générique de chargement asynchrone (données du composant). */

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, extractDetail } from "@/lib/errors";

export interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}

/**
 * Charge une ressource via `loader`. `deps` pilote les rechargements ;
 * `enabled` permet de suspendre le chargement (ex. en attendant un id).
 */
export function useAsyncData<T>(
  loader: () => Promise<T>,
  deps: readonly unknown[],
  enabled = true,
): AsyncState<T> & { reload: () => void; setData: (data: T | null) => void } {
  const [state, setState] = useState<AsyncState<T>>({
    data: null,
    loading: enabled,
    error: null,
  });
  const loaderRef = useRef(loader);
  loaderRef.current = loader;

  const run = useCallback(() => {
    let cancelled = false;
    setState((previous) => ({ ...previous, loading: true, error: null }));
    loaderRef
      .current()
      .then((data) => {
        if (!cancelled) setState({ data, loading: false, error: null });
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          const message =
            error instanceof ApiError
              ? error.detail
              : extractDetail(error) ?? "Erreur inattendue.";
          setState({ data: null, loading: false, error: message });
        }
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    if (!enabled) {
      setState({ data: null, loading: false, error: null });
      return;
    }
    return run();
  }, [enabled, run]);

  const setData = useCallback((data: T | null) => {
    setState({ data, loading: false, error: null });
  }, []);

  return { ...state, reload: run, setData };
}

/** Hook d'action : execute une opération et expose `busy` + `error`. */
export function useAction<TArgs extends unknown[], TResult>(
  fn: (...args: TArgs) => Promise<TResult>,
): {
  busy: boolean;
  error: string | null;
  clearError: () => void;
  run: (...args: TArgs) => Promise<TResult | null>;
} {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  const run = useCallback(async (...args: TArgs): Promise<TResult | null> => {
    setBusy(true);
    setError(null);
    try {
      return await fnRef.current(...args);
    } catch (cause) {
      const message =
        cause instanceof ApiError ? cause.detail : "Une erreur inattendue est survenue.";
      setError(message);
      return null;
    } finally {
      setBusy(false);
    }
  }, []);

  const clearError = useCallback(() => setError(null), []);
  return { busy, error, clearError, run };
}
