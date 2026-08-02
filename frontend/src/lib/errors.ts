/** Erreur métier renvoyée par l'API (format `{"detail": "..."}`). */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/** Extrait un message lisible depuis un corps de réponse d'erreur. */
export function extractDetail(data: unknown): string {
  if (data && typeof data === "object" && "detail" in data) {
    const detail = (data as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      // Erreurs de validation FastAPI (422) : on concatène les messages.
      return detail
        .map((item: { msg?: string }) => item.msg ?? "Champ invalide")
        .join(" ; ");
    }
    return JSON.stringify(detail);
  }
  return "Une erreur inattendue est survenue.";
}
