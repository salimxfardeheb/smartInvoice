/**
 * Tokens de style partagés du design system.
 *
 * Centralise les classes Tailwind « pill » et les tons de couleur pour
 * éviter la duplication entre `Badge`, `badges.tsx` et les composants.
 */

/** Classes de base d'un badge/pill (pilule colorée). */
export const BADGE_BASE =
  "inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ring-1";

/** Tons de couleur disponibles pour un `Badge`. */
export const BADGE_TONES: Record<string, string> = {
  slate: "bg-slate-100 text-slate-700 ring-slate-300",
  blue: "bg-blue-50 text-blue-700 ring-blue-300",
  amber: "bg-amber-50 text-amber-700 ring-amber-300",
  emerald: "bg-emerald-50 text-emerald-700 ring-emerald-300",
  teal: "bg-teal-50 text-teal-700 ring-teal-300",
  rose: "bg-rose-50 text-rose-700 ring-rose-300",
  red: "bg-red-50 text-red-700 ring-red-300",
  sky: "bg-sky-50 text-sky-700 ring-sky-300",
};