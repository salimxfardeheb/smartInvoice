# SmartInvoice

OCR intelligent et rapprochement automatique des factures fournisseurs avec **Odoo**.

Le projet automatise le traitement des factures fournisseurs de bout en bout :
dépôt du document (PDF/image), reconnaissance optique (PaddleOCR), extraction
structurée des champs et des lignes, rapprochement avec le bon de commande
Odoo, détection des anomalies, puis validation comptable et création de la
**Vendor Bill** dans Odoo.

```
PDF / Image
   │
   ▼
OCR (PaddleOCR) ──► Extraction structurée
   │                        │
   ▼                        ▼
Matching facture ↔ Bon de commande Odoo (score + anomalies)
   │
   ▼
Validation comptable (valider / rejeter / corriger)  ──► journal d'audit
   │
   ▼
Création Vendor Bill (account.move Odoo)
```

---

## Table des matières

- [Fonctionnalités](#fonctionnalités)
- [Architecture et structure du projet](#architecture-et-structure-du-projet)
- [Technologies](#technologies)
- [Cycle de vie d'une facture](#cycle-de-vie-dune-facture)
- [Prérequis](#prérequis)
- [Installation](#installation)
- [Configuration](#configuration)
- [Démarrage](#démarrage)
- [Guide d'utilisation](#guide-dutilisation)
- [Modèle de permissions](#modèle-de-permissions)
- [Tests et qualité](#tests-et-qualité)
- [Documentation](#documentation)
- [Limites actuelles](#limites-actuelles)

---

## Fonctionnalités

| Domaine | Détails |
| --- | --- |
| **Authentification** | JWT access (30 min) + refresh tokens avec rotation et révocation (stockés hachés), hash bcrypt, changement de mot de passe, premier compte → Administrateur. |
| **Gestion des utilisateurs** | CRUD, rôles (Comptable / Acheteur / Administrateur), activation/désactivation, matrice de permissions centralisée. |
| **Dépôt de factures** | Upload PDF, JPG, JPEG, PNG — validation par *magic bytes* + ouverture réelle du fichier (anti-corruption), anti-doublon (fournisseur + numéro), limite de taille configurable. |
| **OCR** | Pipeline complet : rendu PDF page à page (pypdfium2) → moteur OCR (PaddleOCR par défaut, Tesseract en second moteur, sélecteur via `OCR_ENGINE`) → nettoyage → extraction (champs généraux, financiers, lignes) → score global + confiance par champ. Pages annexes détectées et conservées comme preuves (images rendues + boîtes englobantes dans `extracted_data`). |
| **Intégration Odoo** | Client XML-RPC (timeout, traduction des erreurs), synchronisation en cache local : `res.partner` → fournisseurs, `purchase.order` → BC, `purchase.order.line` → lignes BC. |
| **Matching** | Rapprochement facture ↔ BC : fournisseur, lignes (produit/référence/nom flou via difflib), quantités, prix unitaires, montants HT/TTC, TVA. Score global pondéré (0..1) persisté. |
| **Anomalies** | Catégories : montant, TVA, quantité, produit absent, doublon, fournisseur, bon de commande, autre. Sévérités info/warning/critical. |
| **Validation comptable** | Valider, rejeter (motif obligatoire), corriger (champs + lignes), créer la Vendor Bill Odoo — chaque action tracée dans un **journal d'audit** (qui, quand, quoi, détail). |
| **Frontend** | Next.js 14 (App Router, TypeScript, Tailwind) : dashboard, liste/filtres, dépôt, détail OCR / matching / validation / historique, rafraîchissement automatique de session. |

---

## Architecture et structure du projet

Le backend suit une **architecture en couches** (API → Services → Repositories →
Modèles), avec deux abstractions stratégiques : le **stockage** (`Storage`) et le
**moteur OCR** (`OcrEngine`), remplaçables sans toucher au reste du code.

### Arborescence

```
smartInvoice/
├── app/                          # Backend FastAPI
│   ├── main.py                   # Fabrique de l'application + exception handlers HTTP
│   ├── api/
│   │   ├── deps.py               # Dépendances FastAPI (DB, services, permissions)
│   │   └── routes/               # Routers : auth, users, invoices
│   ├── core/
│   │   ├── config.py             # Configuration Pydantic-settings (variables d'env)
│   │   ├── exceptions.py         # Exceptions métier → statuts HTTP
│   │   ├── permissions.py        # Matrice rôle → permissions
│   │   └── security.py           # bcrypt, JWT access/refresh, hash de jeton
│   ├── db/
│   │   ├── base.py               # Base déclarative + conventions de nommage
│   │   └── session.py            # Engine + session SQLAlchemy
│   ├── models/                   # Modèles SQLAlchemy (9 entités)
│   │   ├── enums.py              # Statuts, rôles, catégories, sévérités, actions
│   │   ├── mixins.py             # TimestampMixin
│   │   ├── user.py, refresh_token.py
│   │   ├── supplier.py, purchase_order.py, purchase_order_line.py
│   │   ├── invoice.py, invoice_line.py, anomaly.py, audit_log.py
│   ├── repositories/             # Accès données (CRUD + requêtes métier)
│   │   ├── base.py               # BaseRepository générique
│   │   └── <entité>_repository.py
│   ├── schemas/                  # Schémas Pydantic (entrée/sortie API)
│   │   ├── auth.py, user.py, invoice.py, ocr.py
│   │   ├── matching.py, validation.py, summary.py
│   ├── services/                 # Orchestration métier
│   │   ├── document_service.py   # Validation/détection des documents (magic bytes)
│   │   ├── invoice_service.py    # Dépôt, historique, consultation, transitions
│   │   ├── ocr_service.py        # Pipeline OCR complet
│   │   ├── odoo_service.py       # Synchronisation fournisseurs / BC / lignes
│   │   ├── matching_service.py   # Rapprochement facture ↔ BC
│   │   ├── validation_service.py # Validation, rejet, correction, Vendor Bill
│   │   └── auth_service.py       # Auth, comptes, jetons
│   ├── ocr/
│   │   ├── base.py               # Contrat OcrEngine + fabrique (sélecteur)
│   │   ├── paddle.py             # Moteur PaddleOCR (par défaut)
│   │   ├── tesseract.py          # Moteur Tesseract (second moteur, psm 6)
│   │   ├── pages.py              # Détection des pages annexes
│   │   ├── confidence.py         # Confiance par champ (politique)
│   │   ├── document.py           # Chargement PDF/image → images
│   │   ├── cleaners.py           # Normalisation texte, montants, dates, devises
│   │   ├── extractor.py          # Extraction des champs généraux/financiers
│   │   ├── lines.py              # Parsing des lignes de facture
│   │   └── schema.py             # Schémas d'extraction OCR (+ layout/preuves)
│   ├── odoo/
│   │   └── client.py             # Client XML-RPC Odoo
│   └── storage/
│       ├── base.py               # Contrat Storage (save/open/exists/delete/path)
│       └── local.py              # Implémentation disque local
│
├── alembic/                      # Migrations de schéma
│   ├── env.py
│   └── versions/                 # 0001 → 0005 (schéma, refresh tokens, fichiers, BC, audit)
│
├── frontend/                     # Interface Next.js 14
│   ├── src/
│   │   ├── app/                  # Pages : login, dashboard, invoices, upload, détail…
│   │   ├── components/           # ui/, layout/, dashboard/, invoices/
│   │   ├── hooks/                # useAsync, useInvoices
│   │   ├── lib/                  # api-client, auth, config, errors, format, status, tokens
│   │   └── types/                # Types alignés sur les schémas Pydantic
│   └── tests/                    # Jest + Testing Library
│
├── tests/                        # Tests backend (pytest)
├── odoo/                         # Configuration serveur Odoo (à compléter)
├── docker/                       # Fichiers Docker (à compléter)
├── datasets/                     # Jeux de données d'exemple (à compléter)
├── scripts/                      # Scripts utilitaires (à compléter)
└── storage/                      # Stockage local des documents (racine par défaut)
```

### Flux de traitement côté backend

1. `POST /api/invoices` dépose la facture → statut **Déposée**.
2. `POST /api/invoices/{id}/process` exécute le pipeline OCR → statut **À vérifier**.
3. `POST /api/invoices/{id}/match` rapproche avec le bon de commande → score + anomalies.
4. `POST /api/invoices/{id}/validate` / `reject` / `correct` → décision comptable tracée.
5. `POST /api/invoices/{id}/vendor-bill` crée l'`account.move` Odoo → **Vendor Bill créée**.

### Points d'architecture notables

- **Couche de services** orchestrée par les routes ; la logique métier est testable
  sans HTTP (les services sont instanciés directement dans les tests).
- **Repositories** : un seul point d'accès données par agrégat, commit/rollback
  gérés par la dépendance `get_db`.
- **Abstraction OCR** : `OcrEngine` permet de remplacer PaddleOCR (ou de bouchonner
  le moteur dans les tests) sans modifier le pipeline.
- **Abstraction stockage** : `Storage` permet de passer du disque local à un
  object storage (S3/GCS) sans modifier les services.
- **Migrations** : Alembic, 5 révisions ; convention de nommage des contraintes
  centralisée dans `app/db/base.py`.
- **JSONB en PostgreSQL** (avec variante JSON pour les tests SQLite) : portabilité
  du schéma.

---

## Technologies

**Backend**
- Python 3.12, FastAPI, Uvicorn
- SQLAlchemy 2.0, Alembic, PostgreSQL (psycopg2)
- PaddleOCR 3.x + PaddlePaddle, OpenCV, pypdfium2, Pillow
- Pydantic 2 + pydantic-settings
- PyJWT, bcrypt, email-validator
- RapidFuzz/difflib (matching flou), pytest + pytest-cov

**Frontend**
- Next.js 14 (App Router), React 18, TypeScript 5, Tailwind CSS 3
- Jest + Testing Library

---

## Cycle de vie d'une facture

Les transitions de statut sont validées par un graphe (voir
`app/services/invoice_service.py`), les transitions invalides renvoient HTTP 409.

```
Déposée ──► En cours d'analyse ──► À vérifier ──► Validée ──► Vendor Bill créée
   ▲                                    │             │
   │                                    ▼             ▼
Erreur système ◄────────────────────  Rejetée   (validation impossible)
   ▲
   │  (reprise : ré-engagement → Déposée)
```

- **Erreur système** : atteignable depuis toute étape ; la reprise se fait en
  relançant l'analyse (`/process`), qui ramène la facture à **Déposée** puis la
  réanalyse.
- Les statuts, rôles, catégories d'anomalies et actions d'audit sont des enums
  métier stockés en base sous leur **libellé français** (`app/models/enums.py`).

---

## Prérequis

- **Python 3.12** (`.venv` recommandé)
- **PostgreSQL** (en production ; les tests utilisent SQLite en mémoire)
- **Node.js ≥ 18** (pour le frontend)
- Un serveur **Odoo** joignable (uniquement si l'intégration est utilisée)
- PaddleOCR télécharge ses modèles au premier appel (connexion requise)

---

## Installation

### Backend

```bash
# Environnement virtuel
python -m venv .venv
source .venv/bin/activate

# Dépendances
pip install -r requirements.txt

# Base de données
createdb smartinvoice   # ou via psql
```

### Frontend

```bash
cd frontend
npm install
```

---

## Configuration

Copiez la configuration dans `.env` (fichier non versionné) :

```bash
# --- Base de données ---
DATABASE_URL=postgresql+psycopg2://smartinvoice:smartinvoice@localhost:5432/smartinvoice

# --- Sécurité (obligatoire en production) ---
JWT_SECRET_KEY=change-moi-avec-une-vraie-cle
ENVIRONMENT=development        # "production" refuse la clé JWT par défaut

# --- Stockage ---
STORAGE_ROOT=storage
MAX_UPLOAD_SIZE_MB=20

# --- OCR ---
OCR_ENGINE=paddle
OCR_LANG=fr
OCR_TESSERACT_LANG=fra
OCR_RENDER_DPI=200
OCR_CONFIDENCE_THRESHOLD=0.6

# --- Odoo (laisser vide désactive la synchronisation) ---
ODOO_URL=http://odoo.local:8069
ODOO_DB=production
ODOO_USERNAME=smartinvoice
ODOO_PASSWORD=********
ODOO_TIMEOUT_SECONDS=30

# --- Matching (tolérances d'écart relatives) ---
MATCHING_QUANTITY_TOLERANCE=0.05
MATCHING_PRICE_TOLERANCE=0.02
MATCHING_AMOUNT_TOLERANCE=0.02
MATCHING_TAX_TOLERANCE=0.02
```

Toutes les variables sont optionnelles (des défauts de développement sont
définis dans `app/core/config.py`).

### Migrations

```bash
alembic upgrade head
```

---

## Démarrage

### Backend

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

- API : http://localhost:8000
- Documentation interactive Swagger : http://localhost:8000/docs

### Frontend

```bash
cd frontend
npm run dev        # http://localhost:3000
```

Les appels `/api/*` du navigateur sont proxifiés vers le backend
(`http://localhost:8000` par défaut, variable `API_BASE_URL` dans
`frontend/next.config.mjs`) — aucune configuration CORS n'est nécessaire.

---

## Guide d'utilisation

### 1. Créer le compte administrateur

Le **premier compte créé** reçoit automatiquement le rôle **Administrateur**.
Utilisez le formulaire d'inscription du frontend (`/login`) ou :

```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","email":"admin@example.com","password":"motdepasse","full_name":"Admin"}'
```

Les comptes suivants doivent être créés par l'administrateur
(`POST /api/users`), avec le rôle souhaité.

### 2. Synchroniser les référentiels Odoo (fournisseurs, bons de commande)

Les fournisseurs et bons de commande sont synchronisés depuis Odoo par le
service `OdooSyncService`. L'API REST de déclenchement de la synchronisation
n'est **pas encore exposée** (voir `AUDIT.md`) : la synchronisation est pour
l'instant utilisée en interne par le matching et les tests. En attendant un
endpoint dédié, l'intégration nécessite les données déjà en cache local.

### 3. Déposer une facture

```bash
curl -X POST http://localhost:8000/api/invoices \
  -H "Authorization: Bearer <access_token>" \
  -F "file=@facture.pdf" \
  -F "invoice_number=FAC-2026-001" \
  -F "supplier_id=1" \
  -F "issue_date=2026-08-01"
```

Le document est validé (format + lisibilité), la facture passe au statut
**Déposée**. Formats acceptés : PDF, JPG, JPEG, PNG (20 Mo max par défaut).

### 4. Lancer l'analyse OCR

```bash
curl -X POST http://localhost:8000/api/invoices/1/process \
  -H "Authorization: Bearer <access_token>"
```

En cas de succès la facture passe **À vérifier** avec les données extraites
(`extracted_data`), le score de confiance OCR et les lignes de facture. Un
score inférieur au seuil crée une anomalie d'alerte.

### 5. Rapprocher avec le bon de commande

```bash
curl -X POST http://localhost:8000/api/invoices/1/match \
  -H "Authorization: Bearer <access_token>"
```

Le matching compare le fournisseur, rapproche les lignes, contrôle montants et
TVA, calcule le **score global** et crée les **anomalies** éventuelles
(montant, quantité, produit absent, doublon, …).

### 6. Valider / rejeter / corriger

```bash
# Valider
curl -X POST http://localhost:8000/api/invoices/1/validate \
  -H "Authorization: Bearer <access_token>"

# Rejeter (motif obligatoire)
curl -X POST http://localhost:8000/api/invoices/1/reject \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"reason":"Montant erroné"}'

# Corriger les données extraites (champs et/ou lignes)
curl -X PUT http://localhost:8000/api/invoices/1/correct \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"total_excl_tax":"1250.00","lines":[{"line_number":1,"description":"Poste corrigé","amount":"1250.00"}]}'
```

Chaque action est tracée dans le **journal d'audit** de la facture
(`GET /api/invoices/1/audit-logs`).

### 7. Créer la Vendor Bill Odoo

```bash
curl -X POST http://localhost:8000/api/invoices/1/vendor-bill \
  -H "Authorization: Bearer <access_token>"
```

Génère l'`account.move` (`in_invoice`) dans Odoo, lie son identifiant à la
facture (`vendor_bill_id`) et fait passer la facture au statut **Vendor Bill
créée**. En cas d'échec Odoo, la facture reste **Validée** (nouvelle tentative
possible).

### 8. Suivi via le frontend

- **Tableau de bord** (`/`) : nombre de factures par statut + anomalies en attente.
- **Liste des factures** (`/invoices`) : filtres (statut, fournisseur, dates),
  tri et pagination ; accès au fichier source.
- **Détail d'une facture** (`/invoices/{id}`) : métadonnées + onglets
  **OCR**, **Matching**, **Validation** et **Historique** (journal d'audit).
- **Dépôt** (`/invoices/upload`) : formulaire d'upload d'une nouvelle facture.

---

## Modèle de permissions

| Rôle | Permissions |
| --- | --- |
| **Administrateur** | Toutes les permissions |
| **Comptable** | Lecture factures, dépôt, validation, correction, lecture du journal |
| **Acheteur** | Lecture factures, confirmation (quantités/produits) |

Les permissions sont définies dans `app/core/permissions.py`
(`Permission`, `ROLE_PERMISSIONS`). Les endpoints y sont protégés via
`Depends(require_permissions(...))` dans `app/api/deps.py`.

---

## Tests et qualité

### Backend

```bash
source .venv/bin/activate
python -m pytest                     # 373 tests
python -m pytest --cov=app           # couverture globale ~97 %
```

- Base SQLite en mémoire (`StaticPool`) avec `PRAGMA foreign_keys=ON`.
- Moteur OCR et client Odoo **bouchonnés** dans les tests
  (`tests/ocr_fakes.py`, doubles implémentant la même interface).

### Frontend

```bash
cd frontend
npm run typecheck    # TypeScript
npm run lint         # ESLint
npm test             # Jest (94 tests)
npm run build        # build de production
```

Rapport détaillé : voir `docs/COVERAGE.md`.

---

## Documentation

- `docs/COVERAGE.md` — rapport de couverture backend/frontend.
- `frontend/README.md` — guide frontend.
- `AUDIT.md` — état des travaux restants (fichier de suivi, non versionné).

---

## Limites actuelles

- Le pipeline OCR/matching s'exécute de façon **synchrone** (pas de file d'attente
  ni de jobs asynchrones).
- L'extraction OCR repose sur des heuristiques de libellés (français/anglais) :
  les mises en page très complexes peuvent nécessiter une correction manuelle.
- L'intégration Odoo est testée avec des doubles ; aucun test de bout en bout
  contre un serveur Odoo réel.
- La synchronisation Odoo, la résolution d'anomalies et la gestion des
  fournisseurs/BC ne disposent pas encore d'endpoints REST dédiés ni d'interface
  frontend (voir `AUDIT.md`).
- Le conteneurisation (Docker) et le déploiement ne sont pas finalisés
  (`docker-compose.yml` vide).
