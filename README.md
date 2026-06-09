# GitHub AI PR Reviewer

An event-driven microservices platform that automatically reviews GitHub pull requests using multiple AI agents, posts findings back to GitHub, and learns from merged PRs to improve future reviews.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Services](#services)
- [Request Flow](#request-flow)
- [Database Schema](#database-schema)
- [Tech Stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Local Development](#local-development)
- [Production Deployment](#production-deployment)
- [Environment Variables](#environment-variables)
- [GitHub App Setup](#github-app-setup)
- [Health Checks](#health-checks)
- [Scaling & Operations](#scaling--operations)
- [Troubleshooting](#troubleshooting)

---

## Overview

When a pull request is **opened**, **reopened**, or **updated** (`synchronize`), this system:

1. Receives the GitHub webhook
2. Queues the PR for analysis
3. Fetches the PR diff from GitHub
4. Runs four parallel AI review agents (static analysis, security, style, architecture)
5. Deduplicates findings and stores them in PostgreSQL
6. Posts a summary review and inline comments on the PR

When a PR is **merged**, the **learner** service extracts recurring warning/error patterns and stores them so the style agent can reference team-specific issues in future reviews.

---

## Architecture

```mermaid
flowchart TB
    GH[GitHub] -->|POST webhook| GW[Gateway :8100]
    GW -->|verify HMAC signature| GW
    GW -->|forward event| WH[Webhook :8101]

    WH -->|enqueue analyze_pr| RQ[(Redis)]
    RQ --> WW[Webhook Worker<br/>Celery]

    WW -->|POST /analyze| OR[Orchestrator :8102]
    OR -->|fetch PR diff| GH
    OR -->|LangGraph + GPT-4o-mini| AI[4 AI Agents]
    OR -->|store findings| PG[(PostgreSQL)]
    OR -->|POST /post-review| RV[Reviewer :8103]
    RV -->|post review comments| GH

    WH -->|on PR merged| RQ
    WW -->|POST /learn| LR[Learner :8104]
    LR -->|upsert patterns| PG
    OR -->|read patterns| PG

    MIG[Migrate<br/>Alembic] -->|schema| PG
```

### Infrastructure Components

| Component | Role |
|-----------|------|
| **PostgreSQL** | Persistent storage for PRs, findings, and learned patterns |
| **Redis** | Celery message broker and result backend for async jobs |
| **Migrate** | One-shot Alembic container that runs DB migrations on startup |

---

## Services

### 1. Gateway (`services/gateway`)

**Port:** `8000` (mapped to `8100` locally)

**Purpose:** Public entry point for GitHub webhooks.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Service info |
| `/health` | GET | Health check |
| `/webhook/github` | POST | Receives GitHub webhooks |

**Responsibilities:**
- Validates `X-Hub-Signature-256` HMAC signature using `GITHUB_WEBHOOK_SECRET`
- Rejects unsigned or invalid requests (401)
- Forwards the raw payload to the internal Webhook service

**Production note:** Only the Gateway needs a public URL. All other services can remain on a private network.

---

### 2. Webhook (`services/webhook`)

**Port:** `8001` (mapped to `8101` locally)

**Purpose:** Parses GitHub events and orchestrates async processing.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/events` | POST | Receives forwarded webhook payloads |

**Responsibilities:**
- Handles PR events: `opened`, `reopened`, `synchronize`
- Deduplicates by `repo + pr_number + head_sha` to avoid re-processing the same commit
- Creates a `pull_requests` record with status `pending`
- Enqueues `analyze_pr` Celery task on the `webhook` queue
- On merged PRs (`action=closed` + `merged=true`), enqueues `trigger_learning` on the `learning` queue

---

### 3. Webhook Worker (`services/webhook/worker.py`)

**Purpose:** Celery worker that executes background jobs.

**Queues:** `webhook`, `learning`

| Task | Action |
|------|--------|
| `analyze_pr` | Calls Orchestrator `POST /analyze` |
| `trigger_learning` | Calls Learner `POST /learn` |

**Production note:** Scale this worker horizontally for higher PR throughput. Run multiple replicas with the same Redis broker.

---

### 4. Orchestrator (`services/orchestrator`)

**Port:** `8002` (mapped to `8102` locally)

**Purpose:** Fetches PR diffs and runs multi-agent AI analysis.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/analyze` | POST | Analyze a PR (async, returns 202) |

**Responsibilities:**
- Authenticates to GitHub using a GitHub App installation token
- Fetches the PR diff via GitHub API
- Loads top 10 learned patterns for the repo from PostgreSQL
- Runs a **LangGraph** pipeline with four parallel agents:

| Agent | Focus |
|-------|-------|
| `static_analysis` | Complexity, unused variables, naming |
| `security` | OWASP Top 10, secrets, SQL injection |
| `style` | Formatting, readability (uses learned patterns) |
| `architecture` | Separation of concerns, error handling, dependencies |

- Merges and deduplicates findings
- Persists findings to PostgreSQL
- Sends results to the Reviewer service

**AI model:** `gpt-4o-mini` via OpenAI API

---

### 5. Reviewer (`services/reviewer`)

**Port:** `8003` (mapped to `8103` locally)

**Purpose:** Posts AI findings as a GitHub PR review.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/post-review` | POST | Post review to GitHub |

**Responsibilities:**
- Builds a markdown summary of all findings
- Posts inline comments on specific file/line locations
- Falls back to summary-only review if inline comments are rejected (422)
- Updates PR status to `reviewed` in PostgreSQL

---

### 6. Learner (`services/learner`)

**Port:** `8004` (mapped to `8104` locally)

**Purpose:** Learns from merged PRs to improve future reviews.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/learn` | POST | Extract patterns from merged PR findings |

**Responsibilities:**
- Reads `warning` and `error` findings for a merged PR
- Upserts patterns into the `patterns` table (increments frequency on conflict)
- Patterns are fed into the Orchestrator's style agent on future reviews

---

### 7. Migrate (`db/`)

**Purpose:** Database schema management via Alembic.

Runs once at startup (`alembic upgrade head`) before application services start.

**Tables created:**
- `pull_requests` — tracked PRs and their processing status
- `findings` — individual AI review findings per PR
- `patterns` — learned recurring issues per repository

---

## Request Flow

### PR Opened / Updated

```
GitHub webhook
  → Gateway (verify signature)
  → Webhook /events (dedupe + save PR record)
  → Celery: analyze_pr
  → Orchestrator /analyze
      → GitHub API (fetch diff)
      → LangGraph (4 parallel AI agents)
      → PostgreSQL (save findings)
  → Reviewer /post-review
      → GitHub API (post PR review + inline comments)
      → PostgreSQL (status = reviewed)
```

### PR Merged

```
GitHub webhook (closed + merged)
  → Webhook /events
  → Celery: trigger_learning
  → Learner /learn
      → PostgreSQL (upsert patterns from warnings/errors)
```

---

## Database Schema

```
pull_requests
├── id (UUID, PK)
├── repo_full_name (text)
├── pr_number (int)
├── head_sha (text)
├── installation_id (bigint)
├── status (text) — pending | reviewed
└── created_at (timestamp)

findings
├── id (UUID, PK)
├── pr_id (UUID, FK → pull_requests)
├── file, line, severity, message, agent
└── created_at (timestamp)

patterns
├── id (UUID, PK)
├── repo_full_name (text)
├── pattern_text (text)
├── frequency (int)
└── updated_at (timestamp)
UNIQUE (repo_full_name, pattern_text)
```

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| API framework | FastAPI + Uvicorn |
| Language | Python 3.11 |
| Database | PostgreSQL 16 + SQLAlchemy (async) + asyncpg |
| Migrations | Alembic |
| Task queue | Celery + Redis 7 |
| AI orchestration | LangGraph |
| LLM | OpenAI GPT-4o-mini |
| GitHub integration | GitHub App (JWT + installation tokens) |
| Containerization | Docker + Docker Compose |

---

## Prerequisites

- Docker & Docker Compose
- A [GitHub App](https://docs.github.com/en/apps/creating-github-apps) with:
  - Webhook URL pointing to your Gateway
  - Permissions: Pull requests (read & write), Contents (read)
  - Events: `pull_request`
- OpenAI API key
- (Production) Managed PostgreSQL and Redis, or self-hosted equivalents

---

## Local Development

### 1. Configure environment

```bash
cp sample.env .env
# Edit .env with your GitHub App credentials, OpenAI key, and webhook secret
```

### 2. Start all services

```bash
docker compose up --build -d
```

### 3. Verify health

```bash
curl http://localhost:8100/health   # gateway
curl http://localhost:8101/health   # webhook
curl http://localhost:8102/health   # orchestrator
curl http://localhost:8103/health   # reviewer
curl http://localhost:8104/health   # learner
```

### 4. Expose Gateway for GitHub webhooks (local testing)

GitHub cannot reach `localhost`. Use a tunnel:

```bash
ngrok http 8100
```

Set your GitHub App webhook URL to:

```
https://<your-ngrok-url>/webhook/github
```

### Local port mapping

| Service | Container Port | Host Port |
|---------|---------------|-----------|
| Gateway | 8000 | 8100 |
| Webhook | 8001 | 8101 |
| Orchestrator | 8002 | 8102 |
| Reviewer | 8003 | 8103 |
| Learner | 8004 | 8104 |

---

## Production Deployment

This section is intended for the deployment/ops team (e.g. cloud platform, Kubernetes, or VM-based hosting).

### Deployment topology

```
                    Internet
                       │
                 [Load Balancer / Ingress]
                       │
                  Gateway :8000  ← only public service
                       │
            ┌──────────┴──────────┐
            │   Private Network   │
            │                     │
            │  Webhook :8001      │
            │  Orchestrator :8002 │
            │  Reviewer :8003     │
            │  Learner :8004      │
            │  Webhook Worker     │
            │                     │
            │  PostgreSQL         │
            │  Redis              │
            └─────────────────────┘
```

### Step-by-step production checklist

#### 1. Provision infrastructure

| Resource | Recommendation |
|----------|----------------|
| PostgreSQL | Managed service (RDS, Cloud SQL, etc.) with `pgcrypto` extension |
| Redis | Managed service (ElastiCache, Memorystore, etc.) |
| Compute | Container platform (ECS, GKE, AKS, Railway, Render, etc.) |

#### 2. Build and push Docker images

Each service has its own Dockerfile under `services/<name>/Dockerfile`. The migrate image uses `db/Dockerfile`.

```bash
# Example — repeat for each service
docker build -f services/gateway/Dockerfile -t your-registry/gateway:latest .
docker build -f services/webhook/Dockerfile -t your-registry/webhook:latest .
docker build -f services/orchestrator/Dockerfile -t your-registry/orchestrator:latest .
docker build -f services/reviewer/Dockerfile -t your-registry/reviewer:latest .
docker build -f services/learner/Dockerfile -t your-registry/learner:latest .
docker build -f db/Dockerfile -t your-registry/migrate:latest .

docker push your-registry/gateway:latest
# ... push all images
```

#### 3. Run database migrations

Run the migrate container **once** before starting app services:

```bash
docker run --rm \
  -e DATABASE_URL="postgresql+asyncpg://user:pass@db-host:5432/codereviewer" \
  your-registry/migrate:latest
```

Or use a CI/CD init job / Kubernetes Job with the same image and command (`alembic upgrade head`).

#### 4. Deploy services

Deploy each service with the environment variables listed in [Environment Variables](#environment-variables).

**Startup order:**

1. PostgreSQL + Redis (must be healthy)
2. Migrate (one-shot, must complete successfully)
3. Webhook, Orchestrator, Reviewer, Learner (can start in parallel)
4. Webhook Worker (depends on Redis + Orchestrator + Learner)
5. Gateway (depends on Webhook)

#### 5. Configure ingress

- Point your domain to the **Gateway** only
- Enable HTTPS (required by GitHub webhooks)
- Webhook URL: `https://your-domain.com/webhook/github`

#### 6. Configure secrets

Store these in your platform's secret manager (not in source code):

- `GITHUB_WEBHOOK_SECRET`
- `GITHUB_APP_ID`
- `GITHUB_APP_PRIVATE_KEY`
- `OPENAI_API_KEY`
- `DATABASE_URL`
- `POSTGRES_PASSWORD` (if using compose-managed Postgres)

#### 7. Webhook Worker command

```
celery -A worker worker --loglevel=info -Q webhook,learning -c 2
```

Increase `-c` (concurrency) or replica count based on PR volume.

### Kubernetes example (reference)

| Deployment | Replicas | Notes |
|------------|----------|-------|
| gateway | 2+ | Behind Ingress with TLS |
| webhook | 2+ | Internal ClusterIP |
| orchestrator | 2+ | CPU/memory for AI calls |
| reviewer | 2+ | Internal |
| learner | 1–2 | Internal |
| webhook-worker | 2+ | Scale with queue depth |

Use a **Job** for migrate, not a Deployment.

### Using external PostgreSQL / Redis

Update `DATABASE_URL` and `REDIS_URL` to point to managed services. Remove the `postgres` and `redis` services from `docker-compose.yml` if not needed.

**Important:** `DATABASE_URL` must use:
- Driver: `postgresql+asyncpg://`
- Host: your DB hostname (not `localhost` from inside containers)
- No spaces around `=`
- URL-encode special characters in passwords (`@` → `%40`). If using Alembic directly, `%` must be doubled (`%%`)

---

## Environment Variables

| Variable | Required by | Description |
|----------|-------------|-------------|
| `POSTGRES_USER` | Postgres container | DB username |
| `POSTGRES_PASSWORD` | Postgres container | DB password |
| `POSTGRES_DB` | Postgres container | Database name |
| `DATABASE_URL` | webhook, orchestrator, reviewer, learner, migrate | Async SQLAlchemy URL (`postgresql+asyncpg://...`) |
| `REDIS_URL` | webhook, webhook-worker, learner | Celery broker URL (`redis://host:6379/0`) |
| `GITHUB_WEBHOOK_SECRET` | gateway | HMAC secret for webhook verification |
| `GITHUB_APP_ID` | orchestrator, reviewer | GitHub App ID |
| `GITHUB_APP_PRIVATE_KEY` | orchestrator, reviewer | PEM private key (use `\n` for newlines in env) |
| `OPENAI_API_KEY` | orchestrator | OpenAI API key |
| `WEBHOOK_SERVICE_URL` | gateway | Internal URL to webhook service |
| `ORCHESTRATOR_SERVICE_URL` | webhook-worker | Internal URL to orchestrator |
| `REVIEWER_SERVICE_URL` | orchestrator | Internal URL to reviewer |
| `LEARNER_SERVICE_URL` | webhook-worker | Internal URL to learner |

See `sample.env` for a complete template.

---

## GitHub App Setup

1. Go to **GitHub → Settings → Developer settings → GitHub Apps → New GitHub App**
2. Configure:
   - **Webhook URL:** `https://<your-gateway-domain>/webhook/github`
   - **Webhook secret:** same value as `GITHUB_WEBHOOK_SECRET`
   - **Permissions:**
     - Pull requests: Read & write
     - Contents: Read
   - **Subscribe to events:** `Pull request`
3. Generate and download the **private key** → set as `GITHUB_APP_PRIVATE_KEY`
4. Note the **App ID** → set as `GITHUB_APP_ID`
5. Install the app on target repositories

---

## Health Checks

All API services expose `GET /health` returning:

```json
{"status": "ok", "service": "<service-name>"}
```

| Service | Internal | Local (Docker Compose) |
|---------|----------|------------------------|
| Gateway | `:8000/health` | `http://localhost:8100/health` |
| Webhook | `:8001/health` | `http://localhost:8101/health` |
| Orchestrator | `:8002/health` | `http://localhost:8102/health` |
| Reviewer | `:8003/health` | `http://localhost:8103/health` |
| Learner | `:8004/health` | `http://localhost:8104/health` |

**Container status check:**

```bash
docker compose ps -a
```

Expected: all services `Up`, migrate `Exited (0)`, postgres/redis `healthy`.

---

## Scaling & Operations

| Concern | Recommendation |
|---------|----------------|
| High PR volume | Scale `webhook-worker` replicas and Celery concurrency |
| Slow AI reviews | Scale `orchestrator` replicas; monitor OpenAI rate limits |
| Database | Use connection pooling; managed Postgres with backups |
| Redis | Use managed Redis with persistence for task durability |
| Logs | Aggregate logs from all services (CloudWatch, Datadog, etc.) |
| Migrations | Run migrate job on each deploy before rolling out app pods |

### Useful commands

```bash
# View logs for a service
docker compose logs -f orchestrator

# Restart after .env changes
docker compose down && docker compose up --build -d

# Check worker status
docker compose logs webhook-worker --tail 20
```

---

## Troubleshooting

| Problem | Likely cause | Fix |
|---------|-------------|-----|
| Migrate fails with `invalid interpolation syntax` | `%` in `DATABASE_URL` password | URL-encode password; double `%` for Alembic |
| Services can't connect to DB | `DATABASE_URL` uses `localhost` inside Docker | Use service hostname `postgres` or external DB host |
| Webhook returns 401 | Signature mismatch | Ensure `GITHUB_WEBHOOK_SECRET` matches GitHub App settings |
| No review posted | Missing GitHub App permissions | Verify pull request read/write permissions |
| AI analysis fails | Missing/invalid `OPENAI_API_KEY` | Check orchestrator logs |
| PR not re-reviewed on push | Same `head_sha` already processed | Expected dedup behavior; push a new commit |
| Gateway unreachable from GitHub | No public HTTPS URL | Configure ingress/TLS; only Gateway needs to be public |

---

## Project Structure

```
.
├── docker-compose.yml          # Full stack for local / single-host deploy
├── sample.env                  # Environment variable template
├── db/
│   ├── Dockerfile              # Migration runner image
│   ├── alembic.ini
│   └── migrations/             # Alembic migration scripts
└── services/
    ├── gateway/                # Public webhook entry point
    ├── webhook/                # Event handler + Celery worker
    ├── orchestrator/           # AI analysis (LangGraph)
    ├── reviewer/               # GitHub review poster
    └── learner/                # Pattern learning from merged PRs
```

---

## License

Add your license here.
