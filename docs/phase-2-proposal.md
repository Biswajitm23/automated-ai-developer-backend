# Employee Leave Management: Phase 1 status and Phase 2 proposal

Trello card: ELM-P2-PLAN (https://trello.com/c/254KqMBB)
Prepared by Jarvis on 30 Sep 2026. This is a proposal: nothing in Phase 2 is
built until the owner approves it. Each feature below can be approved,
removed or deferred on its own.

---

## 1. Phase 1: what really works today

Checked on 30 Sep 2026 against the latest code (backend branch
`feature/ELM-009-admin-dashboard-filters` 8f7cbc9, frontend branch
`feature/ELM-010-responsive-full-flow` d0e79db), not against card status.

Evidence run today:
- Backend: all **188 automated checks pass**; no database changes missing.
- Frontend: type check and lint pass.
- Browser (Chromium, test admin account): admin dashboard shows the right
  counts; the Leave requests list shows all 12 requests with filters.

| Area | Status | Evidence / note |
|---|---|---|
| Sign-in, sign-out, roles (Employee / Admin) | Done, verified | Auth and permission tests; browser checks on ELM-002 and ELM-010 |
| Remember me, logout confirmation | Done, verified | Tests; browser check |
| Forgot password (6-digit code) | Built, **not usable by staff** | Codes are only printed on the server; no email account is connected |
| Employee and allowance management | Done, verified | Tests; browser check |
| Leave rules (working days, overlaps, balance) | Done, verified | 33 rule tests incl. simultaneous requests |
| Apply, approve, reject, cancel | Done, verified | Tests incl. two admins deciding at once; browser full flow |
| Employee dashboard and history | Done, verified | Tests; browser check |
| Admin dashboard and request list | Done, verified | Tests; re-checked in browser today |
| Responsive screens | Done in Chrome only | Safari and Firefox not tested |
| Code merged into the main version | **Not done** | 16 pull requests (8 per repository) are open and stacked; `main` still has only the empty starting project |
| BP080 as administrator | **Waiting on owner** | Account is still an Employee; the owner needs to run one command |
| Demo deployment (ELM-011) | Not started | Waiting for hosting decisions |
| Automatic task worker (AUTO-002) | Not started | Waiting for two decisions |
| Jarvis identity and comments | Done | Own Trello account (jarvis62); own comments skipped by member ID; card moves checked before commenting; duplicate comments skipped; Done left to the owner |
| Website automated tests | **Missing** | Only type check, lint and build; no screen-level tests |

**Gaps to close before Phase 2 starts** (proposed as Milestone 1 tasks
P2-001 to P2-003): merge Phase 1 into `main`, connect a real email account,
and add basic website tests.

What Phase 1 does *not* have, so Phase 2 is not duplicating anything:
no managers or departments beyond a free-text department field, no holidays,
no half days, fixed leave types (Casual, Sick), no notifications apart from
the password-reset email, no calendar, no reports or export, and no change
history apart from who approved or rejected a request and when.

---

## 2. Decisions needed from the owner

Short answers are enough. Our suggestion is in brackets.

1. **Approvals:** one manager approves, or manager then HR? *(One manager,
   with Admin as fallback.)*
2. **Half days:** allowed? Morning / afternoon only? *(Yes, morning or
   afternoon.)*
3. **Working days and holidays:** Monday–Friday plus a yearly holiday list
   entered by Admin? *(Yes.)*
4. **Email:** which account sends emails (for example a company no-reply
   mailbox)? This also unblocks Forgot password today.
5. **Team calendar:** can employees see teammates' approved leave dates
   (never reasons)? *(Not at first; own calendar only.)*
6. **Hosting and data retention:** where will the live system run, and how
   long must history be kept? *(Same answer as ELM-011; keep history for at
   least 7 years.)*
7. **Scope:** keep carry-forward and accrual out of Phase 2? *(Yes.)*

---

## 3. Phase 2 features and tasks

Estimates are in developer-days for Jarvis, as ranges, and include tests and
browser checks. They assume the decisions above go with our suggestion and
that Phase 1 is merged first. `→` shows what a task depends on.

### Milestone 1: Foundation

| ID | Task | Done when | Estimate |
|---|---|---|---|
| P2-001 | Merge Phase 1 into `main` in both repositories | All 16 PRs merged in order; `main` passes all checks and runs the full flow | 0.5–1 |
| P2-002 | Connect the email account | A real reset code arrives in an inbox; failures are logged without codes or passwords | 0.5 (→ decision 4) |
| P2-003 | Website test setup | Automated browser tests cover sign-in, apply, approve, cancel; run with one command | 1–2 |
| P2-004 | Departments and reporting managers | Admin manages departments and assigns each employee a manager; new Manager role | 2–3 |
| P2-005 | Change history (audit) foundation | Changes to allowances, employee status, roles and decisions are recorded with who, when, before and after; Admin only | 2–3 |

### Milestone 2: Daily workflows

| ID | Task | Done when | Estimate |
|---|---|---|---|
| P2-006 | Manager approvals | Managers see and decide their team's requests; nobody can approve their own; Admin handles employees without a manager | 2–3 (→ P2-004, decision 1) |
| P2-007 | Holiday calendar and working days | Admin sets holidays per year; day counts skip them; existing requests keep their original count | 2–3 (→ decision 3) |
| P2-008 | Half-day leave | Employees can choose a morning or afternoon half day; balances use 0.5 days | 2–3 (→ P2-007, decision 2) |
| P2-009 | Configurable leave types | Admin can add or retire leave types without code changes; history keeps old types | 1–2 |
| P2-010 | In-app and email notifications | Submit, approve, reject and cancel notify the right people once, in the app and by email; failed emails retry without duplicates | 3–4 (→ P2-002, P2-006) |
| P2-011 | First-password setup for new employees | New employees get a single-use, expiring link to set their own password | 1–2 (→ P2-002) |

### Milestone 3: Visibility

| ID | Task | Done when | Estimate |
|---|---|---|---|
| P2-012 | Team leave calendar | Monthly view of approved leave; managers see their team, Admin sees all; filters by department and employee; no reasons shown | 2–3 (→ P2-004, P2-008, decision 5) |
| P2-013 | Leave reports | Admin filters by dates, department, employee, type and status; shows allowance, used, pending and remaining | 2–3 |
| P2-014 | CSV export | The filtered report downloads as a spreadsheet-safe CSV; only permitted users can export | 1 (→ P2-013) |

### Milestone 4: Reliability

| ID | Task | Done when | Estimate |
|---|---|---|---|
| P2-015 | Backup and restore | Written steps; a restore is tested on a separate database | 1–2 (→ decision 6) |
| P2-016 | Operations guide | Settings, health check and how to roll back a release are documented | 1 |
| P2-017 | Jarvis worker (extends AUTO-002) | Start, stop and status commands; one card at a time by priority; survives restarts without repeating work or comments; handles failed tests and expired access | 3–5 (→ AUTO-002 decisions) |

**Total:** about 27–42 developer-days across 17 tasks. No delivery date is
set yet: that depends on the decisions above and on how quickly each
milestone is reviewed.

If the worker (P2-017) is needed to run the milestones unattended, it can
move to Milestone 1.

---

## 4. Rollout and data safety

- Every database change keeps existing employees, leave history and
  balances. Existing requests keep the day count they were approved with.
- New features ship behind the existing roles; nothing becomes visible to
  employees until its milestone is accepted.
- Each milestone is merged into `main` only after the owner accepts it, so
  `main` always matches what has been approved.
- Nothing is changed on a live server as part of this proposal.

## 5. Outside Phase 2

Payroll, biometric attendance, native mobile apps, multi-company billing,
AI approving or rejecting leave, and accrual / carry-forward (unless
approved separately).

## 6. After approval

Jarvis creates one Trello card per approved task, labelled Phase-2 and with
its milestone, linked to this proposal and to the cards it depends on. No
card is started automatically. The brief says to create them in Backlog, but
that list is now called Ready, where cards get picked up. So the owner should
say whether to add them to Ready, or to a separate list until released.
