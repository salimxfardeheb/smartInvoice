/** Utilitaires de formatage des valeurs affichées. */

export function formatCurrency(
  value: string | number | null | undefined,
  currency = "EUR",
): string {
  if (value === null || value === undefined || value === "") return "—";
  const number = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(number)) return "—";
  return new Intl.NumberFormat("fr-FR", {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
  }).format(number);
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("fr-FR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(date);
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("fr-FR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

/** Convertit un score 0..1 en pourcentage arrondi. */
export function formatScore(score: number | null | undefined): string {
  if (score === null || score === undefined) return "—";
  return `${Math.round(score * 100)} %`;
}

/** Formate un écart relatif (-0.05 → "5 %"). */
export function formatDelta(delta: number | null | undefined): string {
  if (delta === null || delta === undefined) return "—";
  const percent = Math.abs(delta) * 100;
  const sign = delta > 0 ? "+" : delta < 0 ? "−" : "";
  return `${sign}${percent.toFixed(1)} %`;
}

/** Convertit une chaîne décimale API en nombre (parse safe). */
export function toNumber(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined || value === "") return null;
  const number = typeof value === "number" ? value : Number(value);
  return Number.isNaN(number) ? null : number;
}
