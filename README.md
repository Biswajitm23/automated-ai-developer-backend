# Employee Leave Management — Backend

Django REST Framework API and PostgreSQL database for the Employee Leave
Management application.

The frontend lives in a separate repository:
https://github.com/Biswajitm23/automated-ai-developer-frontend

| Component | Technology |
|---|---|
| API | Django 6.1 + Django REST Framework |
| Database | PostgreSQL 17 via Docker Compose |

Task requirements are tracked on the Trello board
[Employee Leave Management](https://trello.com/b/uWtRCnyB/employee-leave-management).

## Prerequisites

Tested on WSL 2 (Ubuntu 24.04) with:

- Docker with Docker Compose v2 (Docker Desktop with WSL integration enabled)
- Python 3.12 or newer
- [uv](https://docs.astral.sh/uv/) (used to create the Python virtual environment)

## First-time setup

Run all commands from this repository's root.

### 1. Environment file

```bash
cp .env.example .env
```

Generate a database password and a Django secret key, then write them into
`.env` without printing them:

```bash
DB_PASSWORD=$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')
SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')
sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=${DB_PASSWORD}|" .env
sed -i "s|^DJANGO_SECRET_KEY=.*|DJANGO_SECRET_KEY=${SECRET_KEY}|" .env
unset DB_PASSWORD SECRET_KEY
```

`.env` is read by both Docker Compose and Django, so the credentials only need
to be set once.

### 2. Database

```bash
docker compose up -d db
docker compose ps        # wait until the db service shows "healthy"
```

This starts PostgreSQL with database `elm_dev` and role `elm`, reachable only
from this machine at `127.0.0.1:5433`. Data is kept in the named volume
`elm_elm_pgdata`.

### 3. Python environment and migrations

```bash
uv venv .venv -p 3.12
uv pip install -p .venv/bin/python -r requirements.txt
.venv/bin/python manage.py migrate
```

## Running locally

```bash
docker compose up -d db                                   # database
.venv/bin/python manage.py runserver 127.0.0.1:8000       # API
```

The API is then available at http://localhost:8000.

## Health endpoint

`GET /api/health/`

| Situation | HTTP status | Body |
|---|---|---|
| API and database reachable | 200 | `{"status": "ok", "database": "ok"}` |
| Database unreachable | 503 | `{"status": "error", "database": "error"}` |

```bash
curl http://localhost:8000/api/health/
```

## Checks

```bash
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/python manage.py test
```

## Stopping and resetting

```bash
docker compose stop           # stop the database, keep data
docker compose down           # remove the container, keep data
docker compose down -v        # remove the container AND delete all database data
```

## Troubleshooting

- **CORS error in the browser console** — add the frontend origin to
  `CORS_ALLOWED_ORIGINS` in `.env`.
- **`docker` not found in WSL** — enable WSL integration for your distribution in
  Docker Desktop → Settings → Resources → WSL integration.
- **Port 5433 already in use** — set `POSTGRES_HOST_PORT` and `POSTGRES_PORT` in
  `.env` to the same free port.
