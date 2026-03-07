# Snapshift

Outil personnel de veille visuelle web : capture automatique de pages avec archive WACZ (browsertrix-crawler + ReplayWeb.page), detection de changements, alertes — organise par tags.

## Stack technique

### Backend
- **API** : FastAPI (Python 3.14)
- **BDD** : PostgreSQL 16 (Docker, port 5433) avec SQLAlchemy 2.0 (async) + Alembic
- **Worker** : Container Docker separe (`Dockerfile.worker`), poll la table `capture_jobs` en BDD (SELECT FOR UPDATE SKIP LOCKED)
- **Capture** : browsertrix-crawler (Docker-in-Docker) — crawl une page, capture tout le trafic reseau, produit un WACZ + screenshot full-page
- **Scheduler** : APScheduler (AsyncIOScheduler) integre au lifespan FastAPI
- **Archive** : WACZ (Web Archive Collection Zipped) via browsertrix-crawler, replay via ReplayWeb.page (Service Worker)
- **Replay** : ReplayWeb.page web component (`<replay-web-page>`) charge le WACZ et rejoue fidelement (JS, animations, scroll)
- **Auth** : Token API simple — Bearer header OU query param `?token=xxx` (pour `<img src>` et downloads)

### Frontend
- **Framework** : Vue 3 (Composition API + `<script setup lang="ts">`)
- **UI** : shadcn-vue + Tailwind CSS v4 (plugin `@tailwindcss/vite`)
- **Build** : Vite
- **Router** : Vue Router (history mode)
- **State** : Pinia (stores: urls, tags, captures)
- **HTTP** : Axios (token Bearer via interceptor)
- **Env** : `frontend/.env` avec `VITE_API_URL` et `VITE_API_TOKEN`

### Stockage
- **v1** : Systeme de fichiers local avec abstraction `StorageBackend`
- Structure : `storage/{category}/{YYYY-MM}/{uuid}.ext`
- Categories : screenshots, thumbnails, archives, diffs

## Commandes

### Demarrage complet (Docker)
```bash
docker compose up -d                              # PostgreSQL + API + Worker
```

### Demarrage dev (local)
```bash
docker compose up -d postgres                     # PostgreSQL seul (port 5433)
cd backend && source .venv/bin/activate
alembic upgrade head                               # Migrations
uvicorn app.main:app --reload --port 8000          # API + Scheduler
python -m app.worker.cli                           # Worker (autre terminal)
cd ../frontend && npm run dev                      # Frontend (port 5173)
```

### Backend
```bash
cd backend && source .venv/bin/activate
pip install -e ".[dev]"
alembic revision --autogenerate -m "description"   # Nouvelle migration
pytest                                             # Tests
```

### Frontend
```bash
cd frontend
npm install
npm run dev          # Dev server (port 5173)
npm run build        # Build production
```

### Docker
```bash
docker compose up -d                              # Tout demarrer
docker compose up -d --build                      # Rebuild + demarrer
docker compose logs -f worker                     # Logs du worker
docker compose run --rm worker python -c "..."    # Commande ponctuelle dans le worker
```

## Conventions de code

### Python (Backend)
- Python 3.12+, async/await partout
- Type hints obligatoires
- Pydantic pour la validation (schemas + settings)
- SQLAlchemy 2.0 style (mapped_column, async session)
- Nommage : snake_case pour fonctions/variables, PascalCase pour classes
- Un fichier par model SQLAlchemy
- Routes groupees par ressource dans `api/`
- Logique metier dans `services/`, pas dans les routes
- Les URLs saisies sont auto-normalisees (`dior.com` -> `https://dior.com`) via `@field_validator`

### TypeScript (Frontend)
- TypeScript strict
- Composition API avec `<script setup lang="ts">`
- Un composant par fichier (.vue)
- Stores Pinia par domaine (urls, tags, captures)
- Types centralises dans `src/types/index.ts`
- Client API dans `src/lib/api.ts`
- Les fichiers protegees (images, archives) passent le token via query param dans les URLs

## Architecture

```
API (FastAPI :8000)              Worker (Docker, processus separe)
├── api/urls.py                  └── worker/runner.py
├── api/tags.py                      ├── Poll capture_jobs (status=pending)
├── api/captures.py                  ├── Claim job (SELECT FOR UPDATE SKIP LOCKED)
│   ├── GET screenshot/thumb/archive  ├── Execute via CaptureOrchestrator
│   ├── DELETE single/batch          │   ├── BrowsertrixService
├── api/replay.py                    │   │   └── docker run browsertrix-crawler
│   └── GET /replay/sw.js           │   ├── generate_thumbnail (Pillow)
├── api/deps.py                      │   └── LocalStorage.save_file()
│   └── Auth: Bearer + ?token=       └── Update job status
├── services/scheduler.py
│   └── Cree 1 CaptureJob par URL
└── services/retention.py
    └── Cleanup daily 3:00AM
```

### Docker
- **Dockerfile.worker** : `linux/amd64`, Python + Docker CLI (pas de Chrome/Xvfb)
- **docker-compose.yml** : PostgreSQL + API + Worker
- Storage partage entre API et Worker via bind mount `./backend/storage:/app/storage`
- Worker monte `/var/run/docker.sock` pour Docker-in-Docker (browsertrix-crawler)
- `BROWSERTRIX_HOST_CRAWL_DIR` (chemin HOST) vs `BROWSERTRIX_CRAWL_DIR` (chemin container) pour les volumes Docker-in-Docker

## Modeles BDD
- `MonitoredURL` — URL surveillee avec config (viewports, schedule, archive_enabled)
- `Tag` — Tags libres (N:N avec URLs via `url_tags`)
- `Capture` — Archive WACZ + screenshot optionnel + metadata (1 par capture)
- `CaptureJob` — File d'attente (pending -> running -> completed/failed), 1 job par URL

## API Endpoints
- `GET/POST /api/urls` — Liste (filtres: tag, search, is_active) / Creer
- `GET/PUT/DELETE /api/urls/{id}` — Detail / Modifier / Supprimer
- `POST /api/urls/{id}/capture-now` — Declencher capture immediate (1 job)
- `GET/POST /api/tags` — Liste / Creer
- `GET/PUT/DELETE /api/tags/{id}` — Detail / Modifier / Supprimer
- `GET /api/captures` — Liste (filtres: url_id, viewport_label)
- `GET /api/captures/{id}/screenshot` — Fichier screenshot (auth via token query)
- `GET /api/captures/{id}/thumbnail` — Fichier thumbnail (auth via token query)
- `GET /api/captures/{id}/archive` — Fichier archive WACZ (auth via token query, range requests)
- `GET /api/captures/{id}/archive-preview` — Preview via ReplayWeb.page (auth via token query)
- `GET /api/replay/sw.js` — Service Worker proxy pour ReplayWeb.page
- `DELETE /api/captures/{id}` — Supprimer une capture + fichiers
- `POST /api/captures/delete-batch` — Supprimer plusieurs captures (body: `{capture_ids: [...]}`)
- `GET /health` — Health check (pas d'auth)

## Frontend Views
- **Dashboard** (`/`) — Stats, captures recentes, erreurs
- **URL List** (`/urls`) — Tableau filtrable par tag/recherche, ajout URL, capture now
- **URL Detail** (`/urls/:id`) — Galerie captures, mode selection + suppression batch, viewer pleine taille, download archive
- **Settings** (`/settings`) — Gestion tags (CRUD), retention

## Phases de developpement
- **Phase 1 (MVP)** : Capture WACZ (browsertrix-crawler) + Replay (ReplayWeb.page) + Consultation — COMPLETE
- **Phase 2** : Detection changements + Alertes (diff pixel, email, web push)
- **Phase 3** : Extension Chrome
- **Phase 4** : Multi-user + cloud (auth, S3/R2, roles)
