/** Tests du client API (jetons, rafraîchissement, erreurs normalisées). */

import { api } from "@/lib/api-client";
import { getAccessToken, setTokens } from "@/lib/tokens";

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
});
