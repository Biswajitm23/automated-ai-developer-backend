# Employee Leave Management — Backend

This repository contains the Django REST Framework API and the PostgreSQL
Docker Compose setup. The Next.js frontend lives in a separate repository:
https://github.com/Biswajitm23/automated-ai-developer-frontend

## Task source
- Trello is the source of task requirements.
- Board: Employee Leave Management — ID `6ab23ef82a4c8c74db67b5c7`
  (https://trello.com/b/uWtRCnyB/employee-leave-management)
- Project Brief card: https://trello.com/c/ql171MlA
- Work only on this board and the two project repositories.

## Workflow
- Process one Ready task at a time, respecting priority labels
  (P0 — Foundation, P1 — MVP, P2 — Later) and card dependencies.
- Read complete card descriptions (via `get_card`, not list previews) and all
  comments before implementation.
- If blocked, post a specific question on the card and move it to
  Needs Clarification.
- Move completed implementation to Review. The owner accepts work as Done;
  never move cards to Done yourself.
- A card that spans both repositories needs a matching task branch in each.

## Git
- Work on a task branch per card (e.g. `feature/ELM-002-user-roles-authentication`).
- Commit relevant source code, tests, configuration, and documentation
  (including `.env.example` with placeholder values).
- Never commit `.env` or any real environment file, credentials, `.venv/`,
  `__pycache__/`, collected static files, or local tool state.
- Review `git status` and the staged diff before each commit.

## Local environment
- PostgreSQL runs via Docker Compose (`docker compose up -d db`), database
  `elm_dev`, role `elm`, on `127.0.0.1:5433`. Do not modify the Windows
  PostgreSQL installation.
- Django runs directly in WSL. See README.md for exact commands.
- `.env` is shared by Docker Compose and Django; keep the database values
  consistent within it.
- Permissions must be enforced in the backend; the frontend is not a trust
  boundary.

## Security
- Keep credentials out of source code, Git, logs, and Trello comments.
- Never print secrets to the terminal; generate them directly into ignored files.

## Reporting
- Report actual verification results, including failures.
- Never report an unrun check as passed.
