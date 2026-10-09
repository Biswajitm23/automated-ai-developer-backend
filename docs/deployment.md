# Demo deployment (ELM-011)

Trello card: ELM-011 (https://trello.com/c/jzNxTkHE). Owner decisions of
30 Sep 2026: website on **Render**, backend and database on **Railway**, free
plans or trial credit only, owner creates the accounts, the login page is public
and everything else requires sign-in, fictional data only, no public sign-up.

```
Browser ──► Render (Next.js website) ──/api/...──► Railway (Django + gunicorn) ──► Railway PostgreSQL
```

The browser only talks to the Render address. Next.js forwards `/api/...` to
Django (`BACKEND_ORIGIN`, see the frontend `next.config.ts`), so the sign-in
cookie belongs to the website. Calling Railway directly from the browser would
make it a third-party cookie, which Safari and private windows block.

## Free-plan limits (checked 30 Sep 2026)

| Service | What is free | Limits that matter |
|---|---|---|
| Render web service (website) | Free plan | Sleeps after 15 minutes without traffic; the next visit takes about a minute. 750 instance hours per workspace per month. Free Render Postgres expires after 30 days, so it is **not** used. |
| Railway (backend + PostgreSQL) | Trial: one-time $5 credit, up to 30 days | Trial: 1 GB RAM per service, 0.5 GB volume. Afterwards the Free plan gives $1 credit a month (0.5 GB RAM), which is unlikely to keep Django and PostgreSQL running. The Hobby plan is $5 a month. **Ask the owner before any payment.** |

Sources: https://render.com/docs/free, https://docs.railway.com/reference/pricing/free-trial,
https://docs.railway.com/reference/pricing/plans

## Access Jarvis needs

The owner creates both accounts with their own email ("Sign in with GitHub"),
gives the hosting apps access to the two repositories, and puts two keys in
`deploy-access.env` in the workspace folder (not a Git repository), never on
Trello:

- `RENDER_API_KEY`: Render > Account Settings > API Keys.
- `RAILWAY_TOKEN`: a **project token** for the `production` environment
  (Railway > project > Settings > Tokens). It only reaches that one environment.

## 1. Backend on Railway

1. New project > Deploy from GitHub repo > backend repository, branch
   `main`. `railway.json` sets the build, runs `migrate` before each release,
   starts gunicorn and checks `/api/health/`.
2. Add a PostgreSQL database to the project.
3. Backend service variables (Railway references in `${{ }}`):

   | Variable | Value |
   |---|---|
   | `DJANGO_SECRET_KEY` | new random value, generated straight into Railway |
   | `DJANGO_DEBUG` | `false` |
   | `DJANGO_ALLOWED_HOSTS` | the Railway domain, e.g. `elm-backend.up.railway.app` |
   | `DJANGO_BEHIND_HTTPS_PROXY` | `true` |
   | `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` | `true` |
   | `CSRF_TRUSTED_ORIGINS`, `CORS_ALLOWED_ORIGINS` | the Render address, e.g. `https://elm-frontend.onrender.com` |
   | `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | `${{Postgres.PGDATABASE}}` / `${{Postgres.PGUSER}}` / `${{Postgres.PGPASSWORD}}` |
   | `POSTGRES_HOST` / `POSTGRES_PORT` | `${{Postgres.PGHOST}}` / `${{Postgres.PGPORT}}` |
   | `DRF_NUM_PROXIES` | `0` (see "Known limits") |

   No SMTP settings: email is pending the owner's decision (P2-002), so
   "Forgot password" codes are not delivered on the demo.
4. Settings > Networking > Generate domain. Check
   `https://<domain>/api/health/` returns `{"status":"ok","database":"ok"}`.

## 2. Website on Render

1. New > Blueprint > frontend repository; `render.yaml` creates the free web
   service `elm-frontend`.
2. Set `BACKEND_ORIGIN` to the Railway address (`https://<domain>`, no
   trailing slash). `NEXT_PUBLIC_API_BASE_URL=/` is already in the blueprint.
   Both are read at build time, so redeploy after changing them.
3. Put the Render address into the backend's `CSRF_TRUSTED_ORIGINS` and
   `CORS_ALLOWED_ORIGINS`.

## 3. Demo data and accounts

Load fictional data once, into the empty demo database, from the development
computer using the database's public connection values (Railway > Postgres >
Connect > Public network), exported in the shell for this one command only:

```bash
.venv/bin/python manage.py seed_demo --credentials-file ~/elm-demo-accounts.txt
```

It creates one administrator (DM001) and two employees (DM002, DM003) with
allowances and a few requests, and writes generated passwords **only** to that
file (it refuses to overwrite one, and refuses a database that has non-demo
users). Share the file with the owner privately, never on Trello. Re-running
sets new passwords. There is no public sign-up: accounts are created by Admin.

## 4. Verify on the deployed site

- Signed out: the login page opens; any other page sends you to the login page,
  and `/api/leave-requests/` answers 401.
- Employee: sign in, apply for leave, see it as Pending.
- Admin: sign in, approve it; the employee then sees Approved.
- Record the results on the card.

## Recovery

- **Bad release:** Railway > service > Deployments > previous deployment >
  Redeploy. Render > service > Events/Deploys > roll back to the previous
  deploy.
- **Service asleep or stopped:** Render wakes on the next visit (about a
  minute). If Railway credit is used up, services stop until the owner decides
  on a plan.
- **Database copy:** `pg_dump` with the public connection values; Railway
  trial and free plans have no automatic backups (P2-015 covers backups).
- **Lost demo passwords:** run `seed_demo` again with a new file.

## Known limits of the demo

- After 5 wrong passwords for one username within 15 minutes, that username
  is locked for the rest of the 15 minutes (`LOGIN_MAX_FAILURES`,
  `LOGIN_LOCKOUT_SECONDS`). The count is kept in the database, so all workers
  share it. Someone who knows a username can lock it this way; it unlocks by
  itself after 15 minutes.
- The older per-address limit (20 sign-in attempts a minute) still applies.
  All requests reach Django through Render, so it is shared by all demo users.
- Emails are not sent (P2-002 pending).
