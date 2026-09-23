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

## Authentication and roles

The API uses Django **session** authentication with CSRF protection. There is
no public registration: accounts are created by an administrator.

| Role | Can do |
|---|---|
| `EMPLOYEE` | Sign in and use employee endpoints |
| `ADMIN` | Everything an employee can, plus admin-only endpoints |

The role is stored on each user's profile (`accounts.Profile.role`) and is the
only thing API permissions look at. New users get `EMPLOYEE`; Django superusers
get `ADMIN`. Permissions are enforced by the API — the frontend is not a trust
boundary. Every endpoint requires a signed-in, active user unless it is listed
as public below.

| Method & path | Access | Success | Errors |
|---|---|---|---|
| `GET /api/health/` | public | 200 / 503 | – |
| `GET /api/auth/csrf/` | public | 200 `{"csrfToken": "..."}` and `csrftoken` cookie | – |
| `POST /api/auth/login/` | public, CSRF token required | 200 `{"user": {...}}` and `sessionid` cookie | 400 `{"detail": "Invalid username or password."}` (also for inactive accounts); 400 field errors; 403 CSRF; 429 too many attempts |
| `POST /api/auth/logout/` | public, CSRF token required | 204, session deleted on the server | 403 CSRF |
| `GET /api/auth/me/` | signed in | 200 `{"id", "username", "email", "first_name", "last_name", "role"}` | 401 |
| `GET /api/admin/ping/` | `ADMIN` role | 200 `{"status": "ok", "role": "ADMIN"}` | 401 not signed in; 403 not an admin |

`profile.role` is the only thing API authorization checks. The role also
controls access to the Django admin site: saving a profile with role `ADMIN`
grants full Django admin access (**Staff status** and **Superuser status**, the
same as `create_admin`); saving it with role `EMPLOYEE` removes both. The role
is re-applied whenever a user is saved in the Django admin site, so ticking or
clearing those two checkboxes there has no lasting effect. Changing the flags
outside the profile or the admin site (for example in a shell) is not synced.

Status codes: **401** means "not signed in" (anonymous, logged out, deactivated,
or password changed since sign-in); **403** means "signed in but not allowed" or
a CSRF failure.

Browser flow: call `GET /api/auth/csrf/` with `credentials: "include"`, then
send the returned token in the `X-CSRFToken` header on `POST` requests. The
session cookie is `HttpOnly`, `SameSite=Lax`, and expires after
`SESSION_COOKIE_AGE` seconds (8 hours by default).

Login attempts are throttled per client IP (`LOGIN_THROTTLE_RATE`, 20 per
minute by default; HTTP 429 when exceeded). Limitations to address in a later
card:

- The throttle counters live in Django's default in-memory (LocMem) cache, so
  they are per process and reset on restart. With several worker processes a
  shared cache is needed.
- `X-Forwarded-For` is ignored unless `DRF_NUM_PROXIES` is set. Keep it at `0`
  locally; behind a reverse proxy set it to the number of proxies.
- The Django admin site login (`/admin/login/`) is **not** throttled.

**Same hostname rule:** open the frontend and the API on the same hostname —
`http://localhost:3000` with `http://localhost:8000`, or `127.0.0.1` with
`127.0.0.1`. Mixing them makes the requests cross-site and the browser will not
send the session cookie.

## Create the initial administrator

```bash
read -rs -p "Admin password: " ELM_ADMIN_PASSWORD; echo; export ELM_ADMIN_PASSWORD
.venv/bin/python manage.py create_admin --username admin --email admin@example.com --no-input
unset ELM_ADMIN_PASSWORD
```

Or interactively (prompts twice for the password):

```bash
.venv/bin/python manage.py create_admin --username admin
```

- The username and email can also come from `ELM_ADMIN_USERNAME` and
  `ELM_ADMIN_EMAIL`.
- The password is checked against Django's password validators and is never
  printed.
- Re-running is safe: an existing user is made an active `ADMIN` (with Django
  admin site access) and keeps their password. Add `--update-password` to set a
  new one.

### Recovering administrator access

The app does not stop the last administrator from removing their own `ADMIN`
role or clearing their own **Active** flag. To recover, run:

```bash
.venv/bin/python manage.py create_admin --username <name> --no-input
```

For an existing user this reactivates the account and restores the `ADMIN`
role (with staff and superuser access) without changing the password, so no
password is needed. Add `--update-password` only if the password must also be
reset.

## Creating employee accounts

Until employee management is built into the app, sign in to the Django admin
site at http://localhost:8000/admin/ as the administrator, then **Users → Add
user**. Set the password and save. New users start as `Employee`; to change
the role, choose it in the **Profile** section of the user's change page (the
page that opens after saving) and save again.

## Deactivating an account

In the Django admin site, open the user and clear **Active**. The account loses
access on its next request, including any session that is already open, and can
no longer sign in.

## Checks

```bash
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/python manage.py test
```

The test suite covers login, logout, CSRF, roles, inactive accounts and the
`create_admin` command. After pulling changes that add migrations (for example
the `accounts` app), run `.venv/bin/python manage.py migrate`.

## Stopping and resetting

```bash
docker compose stop           # stop the database, keep data
docker compose down           # remove the container, keep data
docker compose down -v        # remove the container AND delete all database data
```

## Troubleshooting

- **CORS error in the browser console** — add the frontend origin to
  `CORS_ALLOWED_ORIGINS` in `.env`.
- **403 "CSRF Failed" on login or logout** — add the frontend origin to
  `CSRF_TRUSTED_ORIGINS` in `.env`, and make sure the frontend sends the token
  from `GET /api/auth/csrf/` in the `X-CSRFToken` header.
- **Signed in, but the next request is 401** — the session cookie is not being
  sent. Open the frontend and the API on the same hostname (see "Same hostname
  rule"), use `credentials: "include"`, and keep `CORS_ALLOW_CREDENTIALS=true`.
- **`docker` not found in WSL** — enable WSL integration for your distribution in
  Docker Desktop → Settings → Resources → WSL integration.
- **Port 5433 already in use** — set `POSTGRES_HOST_PORT` and `POSTGRES_PORT` in
  `.env` to the same free port.
