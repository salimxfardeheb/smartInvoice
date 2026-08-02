# Rapport de couverture de tests — SmartInvoice

Rapport produit à la fin de la phase 9 (tests), après ajout des tests
unitaires manquants et des tests d'intégration du workflow complet.

Date : août 2026 — Backend : FastAPI + SQLAlchemy ; Frontend : Next.js + Jest.

---

## 1. Backend

### Suite exécutée

```
python -m pytest --cov=app
```

- **373 tests, tous passants** (test suite complète, en ~80 s).
- Moteur SQLite en mémoire (`StaticPool`) avec `PRAGMA foreign_keys=ON`.
- Coverages calculés avec `pytest-cov` / `coverage` (7.15.2).

### Couverture globale

```
app/      TOTAL  2507 stmts, 64 miss  →  97 %
```

### Couverture par module

| Module | Stmts | Couverture | Notes |
| --- | --- | --- | --- |
| `api/deps.py` | 76 | 100 % | dépendances, auth, fabriques de services |
| `api/routes/auth.py` | 32 | 100 % | inscription, login, refresh, logout, me |
| `api/routes/invoices.py` | 94 | 98 % | endpoints factures (OCR, matching, validation) |
| `api/routes/users.py` | 36 | 100 % | gestion des utilisateurs |
| `core/config.py` | 35 | 97 % | configuration |
| `core/exceptions.py` | 28 | 100 % | exceptions métier |
| `core/permissions.py` | 21 | 95 % | contrôle d'accès par rôle |
| `core/security.py` | 43 | 100 % | hachage, JWT, refresh tokens |
| `db/session.py` | 10 | 80 % | sessions (commit/rollback testés via deps) |
| `models/*` | — | 100 % | tous les modèles SQLAlchemy |
| `ocr/base.py` | 21 | 86 % | interface OCR |
| `ocr/cleaners.py` | 98 | 93 % | nettoyage des données OCR |
| `ocr/document.py` | 40 | 100 % | chargement des documents |
| `ocr/extractor.py` | 123 | 88 % | extraction des champs |
| `ocr/lines.py` | 83 | 92 % | détection des lignes |
| `ocr/paddle.py` | 36 | 97 % | moteur PaddleOCR |
| `ocr/schema.py` | 34 | 100 % | schémas de sortie OCR |
| `odoo/client.py` | 100 | 82 % | client Odoo (JSON-RPC) |
| `repositories/*` | — | **100 %** | les 10 repositories (CRUD, filtres, audit, refresh) |
| `schemas/*` | — | 100 % | tous les schémas Pydantic |
| `services/auth_service.py` | 82 | 100 % | inscription, refresh, gestion utilisateurs |
| `services/document_service.py` | 47 | 100 % | dépôt + stockage du fichier |
| `services/invoice_service.py` | 55 | 100 % | cycle de vie des factures, transitions |
| `services/matching_service.py` | 274 | **100 %** | matching facture ↔ BC (score, anomalies) |
| `services/ocr_service.py` | 92 | 97 % | orchestration de l'analyse OCR |
| `services/odoo_service.py` | 138 | **100 %** | synchronisation fournisseurs / BC / lignes |
| `services/validation_service.py` | 137 | 97 % | validation, rejet, correction, Vendor Bill |
| `storage/*` | — | 100 % | stockage local, fichiers sources |
| `main.py` | 33 | 100 % | création de l'application |

### Nouveaux fichiers de test (phase 9)

| Fichier | Tests | Couvre |
| --- | --- | --- |
| `tests/test_workflow_integration.py` | 9 | Workflow complet upload → OCR → matching → validation → Vendor Bill + scénarios d'erreur (document illisible, fournisseur inconnu, BC introuvable, écarts, doublon, Odoo indisponible) |
| `tests/test_ocr_engines.py` | 14 | `PaddleOcrEngine`, `DocumentLoader`, parsing des payloads OCR |
| `tests/test_deps.py` | 13 | dépendances, `get_current_user`, `require_roles`, fabriques |
| `tests/test_auth_service.py` | 8 | `update_user`, refresh (jeton révoqué / inconnu / hash), suppression |
| `tests/test_storage_and_invoice.py` | 14 | `LocalStorage`, `get_source_file`, rollback du dépôt |
| `tests/test_matching_service.py` (étendu) | 33 | toutes les branches du matching (fournisseur flou, BC autre fournisseur, fallback BC lié, TVA, écarts limites, helpers) |
| `tests/test_odoo_sync_service.py` (étendu) | 23 | branche vide, fournisseur via BC, mise à jour BC, helpers de conversion |
| `tests/test_repositories.py` (étendu) | 27 | `AuditLogRepository`, `RefreshTokenRepository`, `UserRepository.filter`, `InvoiceRepository` (dates, `find_other_with_supplier_number`), `BaseRepository` |

---

## 2. Frontend

### Suite exécutée

```
npx jest --coverage
```

- **15 suites de test, 94 tests, tous passants** (~2 s).
- Environnement `jest-environment-jsdom`, `@testing-library/react`.

### Couverture globale

```
All files   78,17 % stmts | 57,02 % branch | 70,05 % funcs | 78,47 % lines
```

### Modules ciblés en phase 9

| Module | Stmts | Branches | Notes |
| --- | --- | --- | --- |
| `hooks/useAsync.ts` | 100 % | 90 % | chargement, erreurs, `reload`, `enabled`, `setData` |
| `hooks/useInvoices.ts` | 100 % | 100 % | liste, détail, résumé, audit, actions |
| `lib/api-client.ts` | 100 % | 100 % | tous les endpoints, refresh, `fetchFile`, 204, corps bruts |
| `lib/config.ts` | 100 % | 100 % | URL de base, taille de page |
| `lib/errors.ts` | 100 % | 100 % | `ApiError`, `extractDetail` (chaîne, liste 422, objet) |
| `lib/format.ts` | 100 % | 93 % | devises, dates, scores, écarts, `toNumber` |
| `lib/status.ts` | 100 % | 100 % | statuts, sévérités, catégories, actions, rôles, tris |
| `lib/tokens.ts` | 100 % | 100 % | jetons, profil, JSON invalide, `storeUser(null)` |

### Nouveaux fichiers de test (phase 9)

| Fichier | Tests | Couvre |
| --- | --- | --- |
| `tests/useAsync.test.ts` | 10 | `useAsyncData` (succès, erreurs, reload, disabled, setData), `useAction` |
| `tests/useInvoices.test.ts` | 14 | `useInvoices`, `useInvoice`, `useSummary`, `useAuditLogs`, `useInvoiceActions` |
| `tests/api-client.test.ts` (étendu) | 20 | tous les endpoints, refresh/rotation, 204, `fetchFile` (blob, 401, refresh, 404), `tryRefresh` |
| `tests/tokens.test.ts` | 5 | gestion `localStorage` des jetons et du profil |
| `tests/errors.test.ts` | 5 | normalisation des erreurs API |
| `tests/status.test.ts` | 8 | libellés et styles des statuts/sévérités/catégories |
| `tests/format.test.ts` (étendu) | 10 | `formatDateTime`, `toNumber`, cas limites |
| `tests/config.test.ts` | 2 | configuration |

---

## 3. Vérifications

- `python -m compileall` : OK sur l'ensemble des sources backend.
- `tsc --noEmit` (`npm run typecheck`) : OK sur le frontend.
- Backend : 373 tests OK ; Frontend : 94 tests OK.
- Modules critiques à 100 % : matching, odoo, auth, storage, document,
  invoice, tous les repositories, hooks frontend et `lib/*`.
