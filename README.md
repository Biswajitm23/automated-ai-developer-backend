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
| `POST /api/auth/login/` `{"username", "password", "remember_me"?}` | public, CSRF token required | 200 `{"user": {...}}` and `sessionid` cookie | 400 `{"detail": "Invalid username or password."}` (also for inactive accounts); 400 field errors; 403 CSRF; 429 too many attempts |
| `POST /api/auth/logout/` | public, CSRF token required | 204, session deleted on the server | 403 CSRF |
| `POST /api/auth/password-reset/request/` `{"email"}` | public, CSRF token required | 200, always the same message | 400 field errors; 403 CSRF; 429 |
| `POST /api/auth/password-reset/verify/` `{"email", "code"}` | public, CSRF token required | 200, code not used up | 400 `{"code": [...]}`; 403 CSRF; 429 |
| `POST /api/auth/password-reset/confirm/` `{"email", "code", "new_password"}` | public, CSRF token required | 200, password changed | 400 `{"code": [...]}` or `{"new_password": [...]}`; 403 CSRF; 429 |
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
session cookie is `HttpOnly` and `SameSite=Lax`.

**Remember me:** without `remember_me` the cookie ends when the browser closes,
and the server also ends the session after `SESSION_COOKIE_AGE` seconds (8 hours
by default). With `"remember_me": true` the cookie persists for
`REMEMBER_ME_SESSION_AGE` seconds (30 days by default).

### Forgot password

1. `request` emails a 6-digit code to every active account with that email
   address (case-insensitive). The response is identical for unknown addresses,
   so the endpoint does not reveal which emails are registered. A new code
   replaces the previous one; within `PASSWORD_RESET_RESEND_COOLDOWN` seconds
   (60) no new code is sent.
2. `verify` checks the code without using it up, so the frontend can move on to
   the new-password step.
3. `confirm` checks the code again, validates the new password with Django's
   password validators, sets it, and emails a "password changed" notice.
   Changing the password signs the user out of every existing session; they then
   sign in with the new password.

Codes expire after `PASSWORD_RESET_CODE_TTL` seconds (10 minutes), stop working
after `PASSWORD_RESET_MAX_ATTEMPTS` wrong guesses (5), and are stored only as an
HMAC. All three endpoints share the `PASSWORD_RESET_THROTTLE_RATE` limit (20 per
hour per IP). Accounts without an email address cannot use this flow; an
administrator resets their password in the Django admin site.

**Email delivery:** with `SMTP_HOST` empty (the default) emails are printed to
the `runserver` console, which is how you read the code locally. To send real
emails, set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`,
`SMTP_USE_TLS` / `SMTP_USE_SSL` and `DEFAULT_FROM_EMAIL` in `.env`.

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

## Employees and allowances (admin API)

Administrators manage employees in the app (**Admin → Employees**), which uses
these endpoints. All of them require the `ADMIN` role (403 for employees, 401
when signed out) and a CSRF token on changes. Only accounts with role
`EMPLOYEE` are listed and managed; admin accounts return 404 here.

| Method & path | Body / query | Success | Errors |
|---|---|---|---|
| `GET /api/leave-types/` | – (any signed-in user) | `[{"code": "CASUAL", "name": "Casual Leave"}, {"code": "SICK", "name": "Sick Leave"}]` | 401 |
| `GET /api/admin/employees/` | `q` (name, email, username, department or Employee ID), `status` = `active`/`inactive`/`all` (default), `ordering` = `name` (default) / `-created_at`, `page`, `page_size` (default 20, max 100) | `{count, next, previous, page, page_size, total_pages, results}` | 400 bad `status`/`ordering`; 404 `{"detail": "Invalid page."}` |
| `POST /api/admin/employees/` | `first_name`, `last_name` (optional), `email`, `department`, `username`, `password`, `employee_code` (optional) | 201 employee (never the password) | 400 field errors: duplicate email/username/Employee ID (all case-insensitive), password validators, blank fields |
| `GET /api/admin/employees/{id}/` | – | 200 employee | 404 |
| `PATCH /api/admin/employees/{id}/` | any of `first_name`, `last_name`, `email`, `department`, `employee_code` | 200 employee | 400, 404. Role, username, password and `is_active` cannot be changed here |
| `POST /api/admin/employees/{id}/deactivate/` · `…/reactivate/` | `{}` | 200 employee. Idempotent | 404 |
| `GET /api/admin/employees/{id}/allowances/?year=2026` | `year` required, 2000–2100 | `{employee_id, year, allowances: [...]}`, one row per leave type; unset rows have `days: 0`, `updated_at: null` | 400 `{"year": [...]}`, 404 |
| `PUT /api/admin/employees/{id}/allowances/{year}/{CASUAL\|SICK}/` | `{"days": 12}` (JSON integer 0–366) | 200 allowance row (created or updated) | 400 `{"days": [...]}`, incl. "Allowance cannot be less than approved plus pending leave (N days)."; 404 unknown employee, year or leave type |

An employee is `{id, username, first_name, last_name, full_name, email,
department, employee_code, is_active, created_at, updated_at}`. An allowance row
is `{employee_id, year, leave_type, days, approved, pending, available,
minimum_allowed, updated_at}`, where `available = days - approved - pending` and
`minimum_allowed = approved + pending`.

Rules:

- **Unique email.** Checked case-insensitively against every account (admins
  too), and also enforced by a PostgreSQL index on `LOWER(email)`.
- **Employee ID** (`employee_code`, e.g. `BP081`) is optional, stored upper-case,
  and unique when set.
- **Passwords** are write-only, checked by Django's password validators and
  stored hashed. They are never returned. Employees can later change theirs
  with "Forgot password".
- **Deactivating** keeps the account and all its data (allowances and, from
  ELM-005, leave requests). The employee is refused on their next request and
  cannot sign in. Reactivating restores access.
- **Allowances** are whole days per employee, leave type and calendar year. No
  row means 0 days. Negative values are rejected. An allowance cannot go below
  approved plus pending leave for that type and year; the check runs while the
  employee row is locked. Until leave requests exist (ELM-005), approved and
  pending are always 0 (`leave/usage.py` is where ELM-005 plugs in).
- Employees have no endpoint that changes their role, allowance or profile.

Administrator accounts are still created with `create_admin` or in the Django
admin site (**Users → Add user**, then choose the role in the **Profile**
section, which also has Department and Employee ID).

## Leave rules and balances (ELM-004)

The rules from the Project Brief live in the `leave` app and are used by every
endpoint that creates or changes a leave request (ELM-005 onwards):

- `leave/rules.py` — pure functions: `count_working_days` (Monday–Friday,
  inclusive, O(1)), `date_errors` (past start, reversed range, two calendar
  years, no working days — same messages as the frontend preview) and
  `today_in_app_zone` (Asia/Kolkata).
- `leave/usage.py` — approved (used) and pending (reserved) days per leave type
  for an employee and year. A request counts in the year of its start date.
  Rejected and cancelled requests count for nothing.
- `leave/services.py` — the only way to create or change a request:
  `check_request` / `create_request` (validation, overlap with the employee's
  pending or approved requests, balance), `approve_request` (rechecks status
  and allowance), `reject_request` and `cancel_request` (pending only; releases
  the reservation once). Errors are DRF `ValidationError` (400) or `Conflict`
  (409).

**Available = allowance − approved − pending.** Every balance-affecting
operation, including allowance edits, first locks the employee's user row
(`SELECT … FOR UPDATE`) inside a transaction, so for one employee they run one
at a time. Two simultaneous requests cannot both spend the same days, and an
approval cannot race a cancellation. Lock order is employee, then request.
Tests in `leave/tests/test_concurrency.py` check this with real concurrent
database connections.

Leave requests are visible read-only in the Django admin site.

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
