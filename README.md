# SocialHub — Mass Social Media Account Manager

Manage 50–100+ SoundCloud, TikTok, Twitter/X, and Spotify accounts from one dashboard. Supports posting, scheduling, cross-posting, and first-class engagement actions (like, repost, comment, follow, play, save) — individually or in bulk across all accounts.

---

## Architecture

```
social-hub/
├── backend/              # FastAPI + Celery Python backend
│   ├── app/
│   │   ├── api/          # REST endpoints
│   │   ├── core/         # Config, DB, security
│   │   ├── models/       # SQLAlchemy ORM models
│   │   ├── platforms/    # Per-platform clients (API + Playwright)
│   │   ├── schemas/      # Pydantic request/response schemas
│   │   ├── services/     # Engagement logic, browser session manager
│   │   └── workers/      # Celery tasks (posting, engagement, analytics, health)
│   └── migrations/       # Alembic DB migrations
├── frontend/             # React + Vite + TailwindCSS dashboard
└── docker-compose.yml    # Full stack: DB, Redis, API, Worker, Beat, Frontend
```

**Stack:** FastAPI · PostgreSQL · Redis · Celery · Playwright · React · Tailwind

---

## Quick Start

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env — set SECRET_KEY, JWT_SECRET_KEY, ENCRYPTION_KEY
# Add Twitter API keys and Spotify Client ID/Secret if using those platforms
```

### 2. Start all services

```bash
docker compose up -d
```

This starts:
- **PostgreSQL** on port 5432
- **Redis** on port 6379
- **FastAPI backend** on http://localhost:8000
- **Celery worker** (posting + engagement queue)
- **Celery beat** (scheduler — runs every minute)
- **Flower** task monitor on http://localhost:5555
- **React dashboard** on http://localhost:3000

### 3. Run database migrations

```bash
docker compose exec backend alembic upgrade head
```

### 4. Install Playwright browsers (first run only)

```bash
docker compose exec backend playwright install chromium
```

### 5. Open the dashboard

→ http://localhost:3000

---

## Platform Authentication

| Platform   | Method              | What you need |
|------------|---------------------|---------------|
| SoundCloud | OAuth token + Playwright fallback | OAuth access token + client ID from SC developer portal |
| TikTok     | Playwright (browser session) | Paste session cookies from a logged-in browser |
| Twitter/X  | Official API v2     | Developer app keys from developer.twitter.com |
| Spotify    | Official OAuth2     | App credentials from developer.spotify.com |

---

## Engagement Actions

Every account supports these actions — individually or across 100 accounts at once:

| Action           | SC | TikTok | Twitter | Spotify |
|------------------|----|--------|---------|---------|
| Like / Save      | ✓  | ✓      | ✓       | ✓       |
| Unlike           | ✓  | ✓      | ✓       | ✓       |
| Repost           | ✓  | ✓      | ✓       | —       |
| Comment          | ✓  | ✓      | ✓       | —       |
| Follow           | ✓  | ✓      | ✓       | ✓       |
| Unfollow         | ✓  | ✓      | ✓       | ✓       |
| Play Track       | ✓  | —      | —       | ✓       |
| Add to Playlist  | ✓  | —      | —       | ✓       |

Bulk actions run sequentially with a configurable random delay (default: 5–30 seconds) between each account to mimic organic behaviour.

---

## API Reference

Interactive docs at http://localhost:8000/api/docs

Key endpoints:

```
GET    /api/v1/accounts/                     List all accounts
POST   /api/v1/accounts/                     Add account (with credentials)
POST   /api/v1/accounts/{id}/health-check    Check session validity
POST   /api/v1/accounts/health-check/all     Bulk health check

POST   /api/v1/engagement/action             Single engagement action
POST   /api/v1/engagement/bulk               Same action across multiple accounts
GET    /api/v1/engagement/task/{id}          Poll task status

POST   /api/v1/posts/                        Create / schedule a post
POST   /api/v1/posts/cross-post             Post to multiple accounts at once
POST   /api/v1/posts/{id}/publish-now        Immediate publish

GET    /api/v1/analytics/dashboard           Dashboard overview
GET    /api/v1/analytics/accounts/{id}/growth  Follower growth chart
```

---

## Account Isolation & Security

- Every account gets its **own isolated Playwright browser context** — separate cookies, localStorage, and cache. No cross-account session bleed.
- Sessions are **persisted to disk** (`browser_sessions/{account_id}/`) so logins survive restarts.
- All credentials are **encrypted at rest** with Fernet symmetric encryption before DB storage.
- Per-account **proxy configuration** is applied at the browser context level.
- A global **semaphore** caps concurrent browser pages (default: 10) to keep memory bounded at 100+ accounts.
- Automatic **health checks** run every 30 minutes; accounts needing re-auth are flagged on the dashboard.

---

## Scaling to 100+ Accounts

- Increase `MAX_CONCURRENT_BROWSERS` in `.env` (add RAM accordingly; ~150MB per browser)
- Scale Celery workers: `docker compose up --scale worker=3`
- Distribute engagement load by setting higher `delay_min`/`delay_max` values in bulk actions

---

## Roadmap (future expansion)

- AI-powered caption generation per platform
- Auto-scheduling based on optimal engagement windows
- Webhook integrations (Discord/Slack notifications on post publish, re-auth alerts)
- Analytics export (CSV/PDF reports per campaign)
- Campaign A/B testing across account groups
