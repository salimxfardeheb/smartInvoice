# SmartInvoice — Frontend

Interface Next.js (App Router, TypeScript, Tailwind CSS) de SmartInvoice :
dashboard, liste des factures, dépôt, OCR, matching, validation comptable et
journal d'audit.

## Prérequis

- Node.js ≥ 18
- L'API backend FastAPI démarrée sur `http://localhost:8000`

## Installation et lancement

```bash
npm install
npm run dev        # http://localhost:3000
```

Les appels `/api/*` du navigateur sont proxifiés vers le backend via les
`rewrites` de `next.config.mjs` (variable `API_BASE_URL`, défaut
`http://localhost:8000`). Aucune configuration CORS n'est nécessaire.

## Vérifications

```bash
npm run typecheck  # vérification TypeScript
npm run lint       # ESLint (next/core-web-vitals)
npm test           # Jest + Testing Library (34 tests)
npm run build      # build de production
```

## Structure

```
src/
  app/               pages (login, dashboard, invoices, upload, détail OCR/matching/validation/historique)
  components/        ui/, layout/, dashboard/, invoices/
  hooks/             useAsync, useInvoices (données + actions)
  lib/               api-client (auth + refresh), auth (contexte), format, status, tokens
  types/             types alignés sur les schémas Pydantic
tests/               fixtures + tests de composants (API mockée)
```

## Connexion

Premier compte créé = `Administrateur` ; ensuite création via l'API `/api/users`.
La session utilise un access token JWT (30 min) rafraîchi automatiquement
(rotation du refresh token) par `lib/api-client.ts`.
