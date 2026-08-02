/** Tests des hooks génériques de chargement et d'action. */

import { act, renderHook, waitFor } from "@testing-library/react";

import { ApiError } from "@/lib/errors";
import { useAction, useAsyncData } from "@/hooks/useAsync";

describe("useAsyncData", () => {
  test("charge la ressource et expose data / loading / error", async () => {
    const loader = jest.fn().mockResolvedValue({ id: 1 });
    const { result } = renderHook(() => useAsyncData(loader, []));

    expect(result.current.loading).toBe(true);

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data).toEqual({ id: 1 });
    expect(result.current.error).toBeNull();
  });

  test("capture les erreurs API avec le détail métier", async () => {
    const loader = jest.fn().mockRejectedValue(new ApiError(500, "Panne serveur."));
    const { result } = renderHook(() => useAsyncData(loader, []));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data).toBeNull();
    expect(result.current.error).toBe("Panne serveur.");
  });

  test("capture les erreurs inattendues avec un message générique", async () => {
    const loader = jest.fn().mockRejectedValue(new Error("boom"));
    const { result } = renderHook(() => useAsyncData(loader, []));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe("Une erreur inattendue est survenue.");
  });

  test("reload relance le chargement", async () => {
    let count = 0;
    const loader = jest.fn().mockImplementation(async () => ({ n: ++count }));
    const { result } = renderHook(() => useAsyncData(loader, []));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data).toEqual({ n: 1 });

    act(() => result.current.reload());
    await waitFor(() => expect(result.current.data).toEqual({ n: 2 }));
  });

  test("enabled=false neutralise le hook (pas de chargement)", async () => {
    const loader = jest.fn().mockResolvedValue({ id: 1 });
    const { result } = renderHook(() => useAsyncData(loader, [], false));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(loader).not.toHaveBeenCalled();
    expect(result.current.data).toBeNull();
    expect(result.current.error).toBeNull();
  });

  test("setData met à jour les données sans recharger", async () => {
    const loader = jest.fn().mockResolvedValue({ id: 1 });
    const { result } = renderHook(() => useAsyncData(loader, []));

    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => result.current.setData({ id: 2 }));
    expect(result.current.data).toEqual({ id: 2 });
    expect(loader).toHaveBeenCalledTimes(1);
  });
});

describe("useAction", () => {
  test("execute l'action et expose busy / résultat", async () => {
    const fn: (id: number) => Promise<string> = jest.fn().mockResolvedValue("ok");
    const { result } = renderHook(() => useAction(fn));

    let returned: string | null = null;
    await act(async () => {
      returned = await result.current.run(1);
    });

    expect(returned).toBe("ok");
    expect(fn).toHaveBeenCalledWith(1);
    expect(result.current.busy).toBe(false);
    expect(result.current.error).toBeNull();
  });

  test("capture les erreurs API et retourne null", async () => {
    const fn: (id: number) => Promise<string> = jest
      .fn()
      .mockRejectedValue(new ApiError(409, "Doublon."));
    const { result } = renderHook(() => useAction(fn));

    let returned: string | null = "sentinel";
    await act(async () => {
      returned = await result.current.run(1);
    });

    expect(returned).toBeNull();
    expect(result.current.error).toBe("Doublon.");
    expect(result.current.busy).toBe(false);
  });

  test("capture les erreurs inattendues", async () => {
    const fn: (id: number) => Promise<string> = jest
      .fn()
      .mockRejectedValue(new Error("boom"));
    const { result } = renderHook(() => useAction(fn));

    await act(async () => {
      await result.current.run(1);
    });

    expect(result.current.error).toBe("Une erreur inattendue est survenue.");
  });

  test("clearError réinitialise l'erreur", async () => {
    const fn: (id: number) => Promise<string> = jest
      .fn()
      .mockRejectedValue(new Error("boom"));
    const { result } = renderHook(() => useAction(fn));

    await act(async () => {
      await result.current.run(1);
    });
    expect(result.current.error).not.toBeNull();

    act(() => result.current.clearError());
    expect(result.current.error).toBeNull();
  });
});
