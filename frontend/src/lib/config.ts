/**
 * Configuration de l'application.
 *
 * Les appels d'API utilisent une URL relative ('' = même origine) et sont
 * proxifiés vers le backend par les rewrites de `next.config.mjs`. Il est
 * aussi possible de définir `NEXT_PUBLIC_API_BASE_URL` pour pointer
 * directement vers l'API (attention alors à la configuration CORS).
 */

export const API_BASE_URL: string =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

/** Nombre de factures affichées par page. */
export const PAGE_SIZE = 20;
