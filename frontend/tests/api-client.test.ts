/** Tests du client API (jetons, rafraîchissement, erreurs normalisées). */

import { api, tryRefresh } from "@/lib/api-client";
import { getAccessToken, getRefreshToken, setTokens } from "@/lib/tokens";

function fakeResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => (typeof body === "string" ? body : JSON.stringify(body)),
  } as unknown as Response;
}

describe("api-client", () => {
  let fetchMock: jest.Mock;

  beforeEach(() => {
    fetchMock = jest.fn();
    global.fetch = fetchMock as unknown as typeof fetch;
    window.localStorage.clear();
  });

  test("ajoute le header Authorization Bearer", async () => {
    setTokens("access-1", "refresh-1");
    fetchMock.mockResolvedValueOnce(fakeResponse(200, { items: [], total: 0 }));

    const result = await api.listInvoices({}, 20, 0);

    expect(result.total).toBe(0);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/api/invoices?");
    expect(String(url)).toContain("limit=20");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer access-1");
  });

  test("rafraîchit le jeton sur 401 puis réessaie une fois", async () => {
    setTokens("expired", "refresh-1");
    fetchMock
      .mockResolvedValueOnce(fakeResponse(401, { detail: "Jeton invalide" }))
      .mockResolvedValueOnce(
        fakeResponse(200, {
          access_token: "new-access",
          refresh_token: "new-refresh",
          token_type: "bearer",
        }),
      )
      .mockResolvedValueOnce(fakeResponse(200, { id: 1 }));

    const invoice = await api.getInvoice(1);

    expect(invoice.id).toBe(1);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(getAccessToken()).toBe("new-access");
  });

  test("lève ApiError avec le détail métier", async () => {
    setTokens("access-1", "refresh-1");
    fetchMock.mockResolvedValueOnce(fakeResponse(409, { detail: "Doublon détecté." }));

    await expect(api.depositInvoice(new FormData())).rejects.toMatchObject({
      status: 409,
      detail: "Doublon détecté.",
    });
  });

  test("envoie les filtres de statut et de dates", async () => {
    setTokens("access-1", "refresh-1");
    fetchMock.mockResolvedValueOnce(fakeResponse(200, { items: [], total: 0 }));

    await api.listInvoices(
      { status: "À vérifier", issue_date_from: "2026-01-01", sort: "issue_date_desc" },
      10,
      20,
    );

    const [url] = fetchMock.mock.calls[0];
    const query = decodeURIComponent(String(url)).replace(/\+/g, " ");
    expect(query).toContain("status=À vérifier");
    expect(query).toContain("issue_date_from=2026-01-01");
    expect(query).toContain("sort=issue_date_desc");
    expect(query).toContain("limit=10&offset=20");
  });

  test("serialise supplier_id et issue_date_to dans les filtres", async () => {
    fetchMock.mockResolvedValueOnce(fakeResponse(200, { items: [], total: 0 }));

    await api.listInvoices(
      { supplier_id: 42, issue_date_to: "2026-02-01" },
      10,
      0,
    );

    const [url] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("supplier_id=42");
    expect(String(url)).toContain("issue_date_to=2026-02-01");
    expect(String(url)).toContain("sort=created_at_desc");
  });

  test("retourne undefined sur 204", async () => {
    setTokens("access-1", "refresh-1");
    fetchMock.mockResolvedValueOnce(fakeResponse(204, ""));

    const result = await api.logout("refresh-1");
    expect(result).toBeUndefined();
  });

  test("logout ignore les erreurs réseau", async () => {
    setTokens("access-1", "refresh-1");
    fetchMock.mockRejectedValueOnce(new TypeError("Network error"));

    await expect(api.logout("refresh-1")).resolves.toBeUndefined();
  });

  test("login envoie le formulaire urlencodé", async () => {
    fetchMock.mockResolvedValueOnce(
      fakeResponse(200, {
        access_token: "access-1",
        refresh_token: "refresh-1",
        token_type: "bearer",
      }),
    );

    const pair = await api.login("salim", "Password123!");

    expect(pair.access_token).toBe("access-1");
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/api/auth/login");
    expect(String(init.body)).toContain("username=salim");
  });

  test("me récupère le profil utilisateur", async () => {
    setTokens("access-1", "refresh-1");
    fetchMock.mockResolvedValueOnce(
      fakeResponse(200, { id: 1, username: "salim", email: "salim@x.io" }),
    );

    const user = await api.me();
    expect(user.username).toBe("salim");
  });

  test("les actions de cycle de vie appellent les bons endpoints", async () => {
    setTokens("access-1", "refresh-1");
    const responses = [
      fakeResponse(200, { id: 1 }),
      fakeResponse(200, { id: 1 }),
      fakeResponse(200, { id: 1 }),
      fakeResponse(200, { id: 1 }),
      fakeResponse(200, { id: 1 }),
      fakeResponse(200, { id: 1 }),
    ];
    for (const response of responses) fetchMock.mockResolvedValueOnce(response);

    await api.processInvoice(1);
    await api.matchInvoice(1);
    await api.validateInvoice(1);
    await api.rejectInvoice(1, "Doublon");
    await api.correctInvoice(1, { currency: "USD" });
    await api.createVendorBill(1);

    const urls = fetchMock.mock.calls.map(([url]) => String(url));
    expect(urls[0]).toContain("/api/invoices/1/process");
    expect(urls[1]).toContain("/api/invoices/1/match");
    expect(urls[2]).toContain("/api/invoices/1/validate");
    expect(urls[3]).toContain("/api/invoices/1/reject");
    expect(urls[4]).toContain("/api/invoices/1/correct");
    expect(urls[5]).toContain("/api/invoices/1/vendor-bill");
  });

  test("auditLogs et summary", async () => {
    setTokens("access-1", "refresh-1");
    fetchMock
      .mockResolvedValueOnce(fakeResponse(200, [{ id: 1 }]))
      .mockResolvedValueOnce(
        fakeResponse(200, { by_status: {}, pending_anomalies: [] }),
      );

    const logs = await api.auditLogs(1);
    const summary = await api.summary();

    expect(logs).toHaveLength(1);
    expect(summary.pending_anomalies).toEqual([]);
    const [firstUrl, secondUrl] = fetchMock.mock.calls.map(([url]) => String(url));
    expect(firstUrl).toContain("/api/invoices/1/audit-logs");
    expect(secondUrl).toContain("/api/invoices/summary");
  });

  test("fetchFile retourne le blob et le type de contenu", async () => {
    setTokens("access-1", "refresh-1");
    const blob = new Blob(["pdf-data"]);
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      blob: async () => blob,
      headers: { get: () => "application/pdf" },
      text: async () => "",
    } as unknown as Response);

    const result = await api.fetchFile(1);

    expect(result.blob).toBe(blob);
    expect(result.contentType).toBe("application/pdf");
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/api/invoices/1/file");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer access-1");
  });

  test("fetchFile refraîchit puis réessaie sur 401", async () => {
    setTokens("access-1", "refresh-1");
    const blob = new Blob(["pdf-data"]);
    fetchMock
      .mockResolvedValueOnce({ ok: false, status: 401, text: async () => "" } as unknown as Response)
      .mockResolvedValueOnce(
        fakeResponse(200, {
          access_token: "new-access",
          refresh_token: "new-refresh",
          token_type: "bearer",
        }),
      )
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        blob: async () => blob,
        headers: { get: () => "application/pdf" },
        text: async () => "",
      } as unknown as Response);

    const result = await api.fetchFile(1);

    expect(result.blob).toBe(blob);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(getAccessToken()).toBe("new-access");
  });

  test("fetchFile lève ApiError si le refresh échoue", async () => {
    setTokens("access-1", "refresh-1");
    fetchMock.mockResolvedValueOnce({ ok: false, status: 401, text: async () => "" } as unknown as Response);

    await expect(api.fetchFile(1)).rejects.toMatchObject({
      status: 401,
      detail: "Session expirée.",
    });
  });

  test("fetchFile lève ApiError sur un statut d'erreur", async () => {
    setTokens("access-1", "refresh-1");
    fetchMock.mockResolvedValueOnce(
      fakeResponse(404, { detail: "Fichier introuvable." }),
    );

    await expect(api.fetchFile(999)).rejects.toMatchObject({
      status: 404,
      detail: "Fichier introuvable.",
    });
  });

  test("retourne null quand le corps de réponse est vide", async () => {
    setTokens("access-1", "refresh-1");
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      text: async () => "",
      json: async () => {
        throw new SyntaxError("vide");
      },
    } as unknown as Response);

    const result = await api.me();
    expect(result).toBeNull();
  });

  test("retourne le corps brut quand il n'est pas du JSON", async () => {
    setTokens("access-1", "refresh-1");
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      text: async () => "texte brut",
      json: async () => {
        throw new SyntaxError("invalide");
      },
    } as unknown as Response);

    const result = await api.me();
    expect(result).toBe("texte brut");
  });

  test("tryRefresh échoue sans refresh token", async () => {
    expect(await tryRefresh()).toBe(false);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  test("tryRefresh efface les jetons si la réponse n'est pas ok", async () => {
    setTokens("access-1", "refresh-1");
    fetchMock.mockResolvedValueOnce(fakeResponse(401, { detail: "Refresh invalide" }));

    expect(await tryRefresh()).toBe(false);
    expect(getAccessToken()).toBeNull();
    expect(getRefreshToken()).toBeNull();
  });

  test("tryRefresh efface les jetons sur erreur réseau", async () => {
    setTokens("access-1", "refresh-1");
    fetchMock.mockRejectedValueOnce(new TypeError("Network error"));

    expect(await tryRefresh()).toBe(false);
    expect(getAccessToken()).toBeNull();
    expect(getRefreshToken()).toBeNull();
  });
});

