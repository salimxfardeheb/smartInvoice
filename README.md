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
OCR (PaddleOCR ou Tesseract) ──► Extraction structurée
   │  (tâche asynchrone)                │
   ▼                                    ▼
Matching facture ↔ Bon de commande Odoo (score + anomalies)
   │
   ▼
Confirmation Acheteur (quantités / produits)  ──┐
   │                                            │
   ▼                                            ▼
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
- [Référence des endpoints](#référence-des-endpoints)
- [Tests et qualité](#tests-et-qualité)
- [Documentation](#documentation)
- [Limites actuelles](#limites-actuelles)

---

## Fonctionnalités

| Domaine | Détails |
| --- | --- |
| **Authentification** | JWT access (30 min) + refresh tokens avec rotation et révocation (stockés hachés), hash bcrypt, changement de mot de passe, premier compte → Administrateur. Rotation des secrets JWT (`JWT_LEGACY_SECRETS`) et rate limiting anti-brute-force sur `/login` et `/refresh`. |
| **Gestion des utilisateurs** | CRUD, rôles (Comptable / Acheteur / Administrateur), activation/désactivation, matrice de permissions centralisée. |
| **Dépôt de factures** | Upload PDF, JPG, JPEG, PNG — validation par *magic bytes* + ouverture réelle du fichier (anti-corruption), anti-doublon garanti en base (contrainte fournisseur + numéro), limite de taille configurable, **dépôt par lot** (`/batch`). |
| **OCR** | Pipeline **asynchrone** : rendu PDF page à page (pypdfium2) → moteur OCR (PaddleOCR par défaut, Tesseract en second moteur, sélecteur via `OCR_ENGINE`) → nettoyage → extraction (champs généraux, financiers, lignes) → score global + confiance par champ. Pages annexes détectées et conservées comme preuves (images rendues + boîtes englobantes dans `extracted_data`). Garde-fous : `OCR_MAX_PAGES`, timeout global du pipeline. |
| **Tâches asynchrones** | File in-process (pool de threads), cycle `en attente → en cours → réussi/échoué`, session SQLAlchemy propre par job. `POST /process` retourne **202** + un `task_id` interrogeable via `/api/tasks/{id}`. |
| **Intégration Odoo** | Client XML-RPC (timeout, traduction des erreurs, **clé API** d'utilisateur applicatif), synchronisation en cache local : `res.partner` → fournisseurs, `purchase.order` → BC, `purchase.order.line` → lignes BC, `account.tax` → taux de TVA. |
| **Matching** | Rapprochement facture ↔ BC : fournisseur, lignes (produit/référence/nom flou via difflib), quantités, prix unitaires, montants HT/TTC, TVA, **conversion multi-devises** vers une devise de référence. Score global pondéré (0..1) persisté ; ré-exécution idempotente. |
| **Anomalies** | Catégories : montant, TVA, quantité, produit absent, doublon, fournisseur, bon de commande, autre. Sévérités info/warning/critical. Liste globale paginée et filtrable, résolution traçée. |
| **Confirmation Acheteur** | L'acheteur confirme (et corrige au besoin) quantités et produits sur les anomalies confirmables, avant la décision comptable. |
| **Validation comptable** | Valider, rejeter (motif obligatoire), corriger (champs + lignes), créer la Vendor Bill Odoo (avec compteur de tentatives et dernier message d'erreur) — chaque action tracée dans un **journal d'audit** paginé (qui, quand, quoi, détail). |
| **Configuration à chaud** | Les seuils de matching sont lisibles et modifiables via `/api/config` (permissions `CONFIG_READ` / `CONFIG_WRITE`), sans redéploiement. |
| **Exploitation** | Métriques Prometheus (`/metrics`) : durée des pipelines OCR/matching, taux d'erreur, jauges de file par état de tâche. Verrou optimiste sur les factures (concurrence, double-clic). |
| **Frontend** | Next.js 14 (App Router, TypeScript, Tailwind) : dashboard, liste/filtres, dépôt avec aperçu, détail OCR / matching / validation / historique, écrans anomalies, utilisateurs et sync Odoo, ré-analyse avec suivi de tâche, PWA (manifest + service worker), rafraîchissement automatique de session. |

---

## Architecture et structure du projet

Le backend suit une **architecture en couches** (API → Services → Repositories →
Modèles), avec deux abstractions stratégiques : le **stockage** (`Storage`) et le
**moteur OCR** (`OcrEngine`), remplaçables sans toucher au reste du code.

### Arborescence

```
smartInvoice/
├── app/                          # Backend FastAPI
│   ├── main.py                   # Fabrique de l'application, CORS, exception handlers HTTP
│   ├── api/
│   │   ├── deps.py               # Dépendances FastAPI (DB, services, permissions)
│   │   └── routes/               # 9 routers : auth, users, invoices, anomalies,
│   │                             #   odoo, config, catalog, tasks, metrics
│   ├── core/
│   │   ├── config.py             # Configuration Pydantic-settings (variables d'env)
│   │   ├── exceptions.py         # Exceptions métier → statuts HTTP
│   │   ├── metrics.py            # Registre de métriques (exposition Prometheus)
│   │   ├── permissions.py        # Matrice rôle → permissions
│   │   ├── ratelimit.py          # Limiteur en fenêtre glissante (auth)
│   │   └── security.py           # bcrypt, JWT access/refresh, hash de jeton
│   ├── db/
│   │   ├── base.py               # Base déclarative + conventions de nommage
│   │   └── session.py            # Engine + session SQLAlchemy
│   ├── models/                   # Modèles SQLAlchemy (12 entités)
│   │   ├── enums.py              # Statuts, rôles, catégories, sévérités, actions, tâches
│   │   ├── mixins.py             # TimestampMixin
│   │   ├── user.py, refresh_token.py
│   │   ├── supplier.py, purchase_order.py, purchase_order_line.py
│   │   ├── invoice.py, invoice_line.py, anomaly.py, audit_log.py
│   │   └── task.py, setting.py, currency_rate.py
│   ├── repositories/             # Accès données (CRUD + requêtes métier)
│   │   ├── base.py               # BaseRepository générique
│   │   └── <entité>_repository.py    # 12 repositories
│   ├── schemas/                  # Schémas Pydantic (entrée/sortie API)
│   │   ├── auth.py, user.py, invoice.py, ocr.py, anomaly.py
│   │   ├── matching.py, validation.py, summary.py
│   │   └── catalog.py, config.py, odoo.py, task.py
│   ├── services/                 # Orchestration métier
│   │   ├── document_service.py   # Validation/détection des documents (magic bytes)
│   │   ├── invoice_service.py    # Dépôt, historique, consultation, transitions
│   │   ├── ocr_service.py        # Pipeline OCR complet
│   │   ├── task_manager.py       # File de jobs asynchrones (pool de threads)
│   │   ├── odoo_service.py       # Synchronisation fournisseurs / BC / lignes / taxes
│   │   ├── matching_service.py   # Rapprochement facture ↔ BC (multi-devises)
│   │   ├── confirmation_service.py   # Confirmation Acheteur (quantités/produits)
│   │   ├── validation_service.py # Validation, rejet, correction, Vendor Bill
│   │   ├── config_service.py     # Lecture/écriture des seuils en base
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
│   │   └── client.py             # Client XML-RPC Odoo (mot de passe ou clé API)
│   └── storage/
│       ├── base.py               # Contrat Storage (save/open/exists/delete/path)
│       └── local.py              # Implémentation disque local
│
├── alembic/                      # Migrations de schéma
│   ├── env.py
│   └── versions/                 # 0001 → 0008 (schéma, refresh tokens, fichiers, BC,
│                                 #   audit, actions, tâches/settings/version, Odoo)
│
├── frontend/                     # Interface Next.js 14
│   ├── public/                   # manifest.webmanifest, sw.js, icônes (PWA)
│   ├── src/
│   │   ├── app/                  # 12 pages : login, dashboard, invoices (+ détail,
│   │   │                         #   upload, ocr, matching, validation, historique),
│   │   │                         #   anomalies, users, odoo
│   │   ├── components/           # ui/, layout/, dashboard/, invoices/, anomalies/,
│   │   │                         #   users/, odoo/
│   │   ├── hooks/                # useAsync, useInvoices, useTaskPolling
│   │   ├── lib/                  # api-client, auth, config, errors, format, status, tokens
│   │   └── types/                # Types alignés sur les schémas Pydantic
│   └── tests/                    # Jest + Testing Library
│
├── tests/                        # Tests backend (pytest) — 25 modules
├── datasets/                     # Factures d'exemple FR/EN + generate_samples.py
├── scripts/                      # sync_odoo.py (synchronisation périodique, cron)
├── odoo/                         # Config serveur + addon smartinvoice_bridge (squelette)
├── docker/                       # Dockerfile.backend, Dockerfile.frontend, entrypoint
└── storage/                      # Stockage local des documents (racine par défaut)
```

### Flux de traitement côté backend

1. `POST /api/invoices` (ou `/batch`) dépose la facture → statut **Déposée**.
2. `POST /api/invoices/{id}/process` **planifie** le pipeline OCR et retourne
   **202** + un `task_id` ; l'analyse s'exécute en arrière-plan → statut
   **À vérifier**. Le suivi se fait via `GET /api/tasks/{task_id}`.
3. `POST /api/invoices/{id}/match` rapproche avec le bon de commande → score + anomalies.
4. `POST /api/invoices/{id}/confirm` — l'acheteur confirme quantités et produits.
5. `POST /api/invoices/{id}/validate` / `reject` / `correct` → décision comptable tracée.
6. `POST /api/invoices/{id}/vendor-bill` crée l'`account.move` Odoo → **Vendor Bill créée**.

En cas d'échec, `POST /api/invoices/{id}/retry` relance l'analyse d'une facture
en « Erreur système » avec une action d'audit dédiée.

### Points d'architecture notables

- **Couche de services** orchestrée par les routes ; la logique métier est testable
  sans HTTP (les services sont instanciés directement dans les tests).
- **Repositories** : un seul point d'accès données par agrégat, commit/rollback
  gérés par la dépendance `get_db`.
- **Abstraction OCR** : `OcrEngine` permet de remplacer PaddleOCR par Tesseract
  (ou de bouchonner le moteur dans les tests) sans modifier le pipeline.
- **Abstraction stockage** : `Storage` permet de passer du disque local à un
  object storage (S3/GCS) sans modifier les services.
- **Abstraction d'exécution** : `Executor` (`ThreadedExecutor` en production,
  `InlineExecutor` dans les tests) rend les jobs asynchrones déterministes
  en test, sans broker externe.
- **Verrou optimiste** : les factures sont versionnées (`version_id`), ce qui
  protège des écritures concurrentes (double-clic, retries, jobs parallèles).
- **Migrations** : Alembic, 8 révisions ; convention de nommage des contraintes
  centralisée dans `app/db/base.py`.
- **JSONB en PostgreSQL** (avec variante JSON pour les tests SQLite) : portabilité
  du schéma.

---

## Technologies

**Backend**

- Python 3.12, FastAPI, Uvicorn
- SQLAlchemy 2.0, Alembic, PostgreSQL (psycopg2)
- PaddleOCR 3.x + PaddlePaddle, Tesseract (pytesseract), OpenCV, pypdfium2, Pillow
- Pydantic 2 + pydantic-settings
- PyJWT, bcrypt, email-validator
- RapidFuzz/difflib (matching flou), pytest + pytest-cov
- File de tâches : `concurrent.futures` (pool de threads in-process, sans broker)

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

- **Erreur système** : atteignable depuis toute étape ; la reprise se fait via
  `/retry` (ou `/process`), qui ramène la facture à **Déposée** puis la
  réanalyse, en traçant l'action `re_analyse` dans le journal d'audit.
- Une facture déjà **En cours d'analyse** refuse une nouvelle demande (HTTP 409),
  ce qui évite les traitements concurrents.
- Les statuts, rôles, catégories d'anomalies, actions d'audit et états de tâche
  sont des enums métier stockés en base sous leur **libellé français**
  (`app/models/enums.py`).

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

# Dépendances applicatives
pip install -r requirements.txt

# …ou, pour développer (ajoute pytest et ruff)
pip install -r requirements-dev.txt

# Base de données
createdb smartinvoice   # ou via psql
```

> `requirements.txt` ne contient que les dépendances d'exécution : c'est ce que
> l'image Docker installe. L'outillage de test et de lint vit dans
> `requirements-dev.txt`.

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
JWT_LEGACY_SECRETS=            # anciennes clés encore acceptées en décodage (rotation)

# --- CORS (vide = désactivé ; inutile derrière le proxy Next.js) ---
CORS_ORIGINS=                  # ex. https://app.exemple.com,https://admin.exemple.com

# --- Rate limiting de l'authentification (anti-brute-force) ---
RATE_LIMIT_ENABLED=true        # ACTIF par défaut ; "false"/"0"/"no" pour désactiver
RATE_LIMIT_MAX=20              # tentatives autorisées par fenêtre et par (utilisateur, IP)
RATE_LIMIT_WINDOW_SECONDS=60

# --- Stockage ---
STORAGE_ROOT=storage
MAX_UPLOAD_SIZE_MB=20

# --- OCR ---
OCR_ENGINE=paddle              # "paddle" ou "tesseract"
OCR_LANG=fr
OCR_TESSERACT_LANG=fra
OCR_RENDER_DPI=200
OCR_CONFIDENCE_THRESHOLD=0.6
OCR_MAX_PAGES=50               # garde-fou : pages analysées au maximum
OCR_PIPELINE_TIMEOUT_SECONDS=300

# --- File de tâches asynchrones ---
TASK_QUEUE_WORKERS=2           # threads du pool de jobs OCR — c'est CE réglage
                               # qu'on augmente, pas le nombre de workers Uvicorn

# --- Odoo (laisser vide désactive la synchronisation) ---
ODOO_URL=http://odoo.local:8069
ODOO_DB=production
ODOO_USERNAME=smartinvoice
ODOO_PASSWORD=********
ODOO_API_KEY=                  # si renseignée, prime sur ODOO_PASSWORD (Odoo 14+)
ODOO_TIMEOUT_SECONDS=30

# --- Matching (tolérances d'écart relatives) ---
MATCHING_QUANTITY_TOLERANCE=0.05
MATCHING_PRICE_TOLERANCE=0.02
MATCHING_AMOUNT_TOLERANCE=0.02
MATCHING_TAX_TOLERANCE=0.02
FX_BASE_CURRENCY=EUR           # devise pivot pour le matching multi-devises
```

Toutes les variables sont optionnelles (des défauts de développement sont
définis dans `app/core/config.py`).

> **Attention** : ce `.env` est lu par `pydantic-settings` au **chargement du
> module**, y compris pendant les tests. Un `.env` local renseigné peut donc
> faire diverger le résultat de la suite de tests (voir `AUDIT.md`, § 7).

Les **tolérances de matching** (`MATCHING_*`) peuvent aussi être modifiées à
chaud, sans redéploiement, via `PATCH /api/config` (permission `CONFIG_WRITE`) :
la valeur persistée en base prime alors sur la variable d'environnement
(`MatchingService.__init__`).

> `OCR_CONFIDENCE_THRESHOLD` est également accepté par `PATCH /api/config` et
> renvoyé modifié par `GET /api/config`, **mais le pipeline OCR lit encore la
> valeur d'environnement** — la surcharge est donc sans effet réel à ce jour
> (voir `AUDIT.md`, § 3). Utilisez la variable d'environnement pour ce seuil.

### Migrations

```bash
alembic upgrade head
```

---

## Démarrage

### Backend

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000          # développement
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1   # production
```

- API : http://localhost:8000
- Documentation interactive Swagger : http://localhost:8000/docs

> ### ⚠️ Lancer l'API avec **un seul worker** (`--workers 1`)
>
> Trois composants sont des singletons **en mémoire du processus** :
>
> | Composant | Module | Conséquence avec plusieurs workers |
> | --- | --- | --- |
> | Limiteur anti-brute-force | `app/core/ratelimit.py` | Chaque worker tient son propre compteur : la limite effective devient `RATE_LIMIT_MAX × nombre de workers`. |
> | File de jobs OCR | `app/services/task_manager.py` | Le pool de threads est propre au worker qui a reçu la requête ; aucune file partagée, aucune reprise entre workers. |
> | Registre de métriques | `app/core/metrics.py` | Un scrape de `/metrics` ne renvoie que les compteurs du worker interrogé — les séries sont partielles et incohérentes d'un scrape à l'autre. |
>
> **Pour absorber plus de charge OCR, augmente `TASK_QUEUE_WORKERS`** (threads
> du pool, dans le même processus), pas le nombre de workers Uvicorn. La même
> règle vaut pour un déploiement conteneurisé : **une seule réplique** de l'API
> tant que ces trois composants ne sont pas déportés sur un stockage partagé
> (Redis).

**Reprise au démarrage.** Les jobs OCR ne survivent pas à un arrêt du serveur.
À chaque démarrage, l'application balaye les tâches restées « en cours »
(`app/services/startup_recovery.py`) : elles passent à « échoué », et les
factures bloquées en « En cours d'analyse » repassent en « Erreur système »,
état depuis lequel `POST /api/invoices/{id}/retry` est accepté. Chaque reprise
est tracée dans le journal d'audit sous l'action `tâche_interrompue`, sans
utilisateur. Si la base est injoignable au démarrage, l'application démarre
quand même et l'incident est journalisé.

### Frontend

```bash
cd frontend
npm run dev        # http://localhost:3000
```

Les appels `/api/*` du navigateur sont proxifiés vers le backend
(`http://localhost:8000` par défaut, variable `API_BASE_URL` dans
`frontend/next.config.mjs`) — aucune configuration CORS n'est nécessaire.

### Avec Docker

```bash
cp .env.example .env        # puis renseigner JWT_SECRET_KEY
docker compose up --build
```

Trois services démarrent en cascade, chacun attendant que le précédent soit
*sain* (`depends_on: condition: service_healthy`) : `db` (PostgreSQL 16) →
`backend` → `frontend`. Les migrations Alembic sont appliquées par
l'entrypoint du backend avant le lancement d'Uvicorn.

| Volume | Contenu |
| --- | --- |
| `postgres_data` | Données PostgreSQL |
| `storage_data` | Documents déposés (`/app/storage`) |

> **Premier build long.** L'image backend précharge les modèles PaddleOCR
> (`docker/Dockerfile.backend`) : plusieurs centaines de Mo sont téléchargées
> pendant le `build`, et non au premier appel OCR en production. C'est
> volontaire — sans cela, la première facture analysée semble bloquée, et
> échoue si l'hôte n'a pas d'accès sortant.

`JWT_SECRET_KEY` est obligatoire : les conteneurs tournent avec
`ENVIRONMENT=production`, et l'API refuse de démarrer avec la clé de
développement par défaut.

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

La synchronisation est exposée sous `/api/odoo/sync` et pilotable depuis la page
**Sync Odoo** du frontend :

```bash
# Synchroniser un fournisseur par son nom
curl -X POST http://localhost:8000/api/odoo/sync/suppliers \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"name":"ACME SARL"}'

# Synchroniser un bon de commande par sa référence
curl -X POST http://localhost:8000/api/odoo/sync/purchase-orders \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"reference":"PO00042"}'

# Actualiser les lignes d'un BC (et lire les lignes en cache)
curl -X POST http://localhost:8000/api/odoo/sync/purchase-orders/1/lines \
  -H "Authorization: Bearer <access_token>"
curl http://localhost:8000/api/odoo/sync/purchase-orders/1/lines \
  -H "Authorization: Bearer <access_token>"
```

Les fournisseurs et bons de commande sont aussi consultables et modifiables
directement via `/api/suppliers` et `/api/purchase-orders`.

Pour une synchronisation programmée (cron), utilisez
[scripts/sync_odoo.py](scripts/sync_odoo.py) — à ce jour, seul le
synchroniseur de taux de change y est branché.

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
Pour déposer plusieurs factures en une requête, utilisez
`POST /api/invoices/batch`.

### 4. Lancer l'analyse OCR (asynchrone)

```bash
# Retourne 202 + un task_id ; l'analyse tourne en arrière-plan
curl -X POST http://localhost:8000/api/invoices/1/process \
  -H "Authorization: Bearer <access_token>"

# Suivre l'avancement (en attente → en cours → réussi | échoué)
curl http://localhost:8000/api/tasks/1 \
  -H "Authorization: Bearer <access_token>"
```

En cas de succès la facture passe **À vérifier** avec les données extraites
(`extracted_data`), le score de confiance OCR et les lignes de facture. Un
score inférieur au seuil crée une anomalie d'alerte ; les champs critiques peu
fiables sont signalés individuellement.

Si la facture est déjà « En cours d'analyse », la requête est refusée (409).
Une facture en « Erreur système » se relance via
`POST /api/invoices/1/retry`.

### 5. Rapprocher avec le bon de commande

```bash
curl -X POST http://localhost:8000/api/invoices/1/match \
  -H "Authorization: Bearer <access_token>"
```

Le matching compare le fournisseur, rapproche les lignes, contrôle montants et
TVA (en convertissant les devises si facture et BC diffèrent), calcule le
**score global** et crée les **anomalies** éventuelles (montant, quantité,
produit absent, doublon, …). L'opération est idempotente : les anomalies du
passage précédent sont purgées à chaque nouvelle exécution.

### 6. Confirmer les quantités et produits (rôle Acheteur)

```bash
curl -X POST http://localhost:8000/api/invoices/1/confirm \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"lines":[{"line_number":1,"confirmed":true,"quantity":"12","product_ref":"REF-A"}]}'
```

L'acheteur confirme ligne à ligne ; les valeurs fournies (`quantity`,
`unit_price`, `product_ref`) **écrasent** celles extraites par l'OCR, et les
anomalies confirmables encore ouvertes (quantité, produit absent, prix) sont
marquées résolues. L'action est tracée sous `confirmation_acheteur` dans le
journal d'audit.

### 7. Valider / rejeter / corriger

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

Chaque action est tracée dans le **journal d'audit** de la facture, paginé :
`GET /api/invoices/1/audit-logs?limit=50&offset=0`.

### 8. Traiter les anomalies

```bash
# Lister les anomalies ouvertes, filtrées
curl "http://localhost:8000/api/anomalies?resolved=false&severity=critical&limit=50" \
  -H "Authorization: Bearer <access_token>"

# Marquer une anomalie résolue
curl -X POST http://localhost:8000/api/anomalies/12/resolve \
  -H "Authorization: Bearer <access_token>"
```

### 9. Créer la Vendor Bill Odoo

```bash
curl -X POST http://localhost:8000/api/invoices/1/vendor-bill \
  -H "Authorization: Bearer <access_token>"
```

Génère l'`account.move` (`in_invoice`) dans Odoo, lie son identifiant à la
facture (`vendor_bill_id`) et fait passer la facture au statut **Vendor Bill
créée**. En cas d'échec Odoo, la facture reste **Validée** : la tentative est
comptée (`vendor_bill_attempts`) et le motif conservé (`vendor_bill_error`),
une nouvelle tentative reste possible.

### 10. Suivi via le frontend

- **Tableau de bord** (`/`) : nombre de factures par statut + anomalies en attente.
- **Liste des factures** (`/invoices`) : filtres (statut, fournisseur, dates),
  tri et pagination ; accès au fichier source.
- **Détail d'une facture** (`/invoices/{id}`) : métadonnées + onglets
  **OCR** (avec preuves visuelles et bouton de ré-analyse), **Matching**,
  **Validation** et **Historique** (journal d'audit).
- **Dépôt** (`/invoices/upload`) : formulaire d'upload avec aperçu du document.
- **Anomalies** (`/anomalies`) : liste filtrable et résolution.
- **Utilisateurs** (`/users`) : administration des comptes et des rôles.
- **Sync Odoo** (`/odoo`) : déclenchement des synchronisations et résultat.

---

## Modèle de permissions

| Rôle | Permissions |
| --- | --- |
| **Administrateur** | Toutes les permissions (dont `user:*` et `config:write`) |
| **Comptable** | Lecture factures, dépôt, validation, correction, lecture du journal |
| **Acheteur** | Lecture factures, confirmation (quantités/produits) |

Les 11 permissions (`invoice:read|deposit|validate|correct|confirm`,
`user:read|write|deactivate`, `config:read|write`, `journal:read`) sont définies
dans `app/core/permissions.py` (`Permission`, `ROLE_PERMISSIONS`). Les endpoints
y sont protégés via `Depends(require_permissions(...))` dans `app/api/deps.py`,
et le frontend double le contrôle côté UI avec `RequireAuth` / `RequireRole`.

---

## Référence des endpoints

**48 routes** exposées dans l'OpenAPI (`/docs`, `/openapi.json`), plus
`/metrics` (hors schéma).

| Préfixe | Routes | Rôle |
| --- | --- | --- |
| `/api/auth` | `register`, `login`, `refresh`, `logout`, `me`, `change-password` | Authentification et session |
| `/api/users` | liste, détail, création, `PATCH`, `deactivate` | Administration des comptes |
| `/api/invoices` | dépôt, `batch`, liste, `summary`, détail, `file`, `process`, `retry`, `match`, `confirm`, `validate`, `reject`, `correct`, `status`, `vendor-bill`, `audit-logs`, résolution d'anomalie | Cycle de vie complet des factures |
| `/api/anomalies` | liste filtrable, `resolve` | Suivi et résolution des anomalies |
| `/api/tasks` | liste, détail | Suivi des jobs OCR asynchrones |
| `/api/odoo/sync` | `suppliers`, `purchase-orders`, lignes de BC (`GET`/`POST`) | Synchronisation des référentiels Odoo |
| `/api/suppliers` | CRUD complet (5 routes) | Catalogue fournisseurs |
| `/api/purchase-orders` | liste, création, détail, `PATCH`, lignes | Catalogue bons de commande |
| `/api/config` | `GET`, `PATCH` | Seuils applicatifs modifiables à chaud |
| `/metrics` | `GET` | Exposition Prometheus (hors OpenAPI) |

---

## Tests et qualité

### Backend

```bash
source .venv/bin/activate
python -m pytest                     # 454 tests, ~100 s
python -m pytest --cov=app           # couverture globale 95 %
```

- Base SQLite en mémoire (`StaticPool`) avec `PRAGMA foreign_keys=ON`.
- Moteur OCR et client Odoo **bouchonnés** dans les tests
  (`tests/ocr_fakes.py`, doubles implémentant la même interface).
- Les jobs asynchrones utilisent `InlineExecutor` en test : le pipeline
  s'exécute dans le fil de l'appel, les assertions restent déterministes.

> **Un test échoue actuellement** en présence d'un `.env` local renseigné :
> `test_odoo_client.py::TestAuthentication::test_missing_configuration_raises`.
> C'est un défaut d'isolation de la suite (le `.env` du développeur fuite dans
> les settings), pas une régression du code applicatif. Détail et correctif
> dans `AUDIT.md`, § 7.

### Frontend

```bash
cd frontend
npm run typecheck    # TypeScript — propre
npm run lint         # ESLint
npm test             # Jest — 22 suites, 135 tests
npm run build        # build de production
```

Couverture frontend : 78 % instructions / 63 % branches (les `lib/*` et
`hooks/*` sont à 100 %, le retard porte sur les composants de page).

---

## Documentation

- `AUDIT.md` — état vérifié du projet et travaux restants, par priorité.
  **Non versionné** (présent dans `.gitignore`).
- `frontend/README.md` — guide frontend.
- `docs/COVERAGE.md` — rapport de couverture. ⚠️ **Périmé** (établi à 373 tests
  / 97 % sur un périmètre antérieur) ; se fier aux commandes ci-dessus.

---

## Limites actuelles

Ces limites sont détaillées, avec leur correctif envisagé, dans `AUDIT.md`.

- **Déploiement à éprouver** : la pile Docker (`docker compose up --build`) et
  la CI GitHub Actions existent mais n'ont pas encore tourné sur une machine
  disposant de Docker — le premier build, qui précharge les modèles PaddleOCR,
  reste à valider.
- **Mono-instance** : la file de tâches et le rate limiter vivent en mémoire du
  processus. Pas de reprise des tâches après un crash, pas de compteur partagé
  entre répliques — une migration Redis + Celery/RQ sera nécessaire pour
  passer à l'échelle.
- **Extraction OCR heuristique** (libellés FR/EN) : les scans inclinés (pas de
  *deskew*), les QR codes / Factur-X et les mises en page très libres peuvent
  nécessiter une correction manuelle.
- **Intégration Odoo testée avec des doubles** : aucun test de bout en bout
  contre un serveur Odoo réel. L'addon `odoo/addons/smartinvoice_bridge` n'est
  qu'un squelette (manifeste seul, aucun modèle) et `odoo/config/odoo.conf` est
  vide.
- **Tests sur SQLite uniquement** : le comportement sous PostgreSQL (JSONB,
  contraintes, verrous concurrents) n'est pas encore validé en continu.
