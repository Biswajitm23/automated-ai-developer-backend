# Employee Leave Management: Phase 1 status and Phase 2 proposal

Trello card: ELM-P2-PLAN (https://trello.com/c/254KqMBB)
Prepared by Jarvis on 30 Sep 2026; updated the same day with the owner's
decisions (section 2). Task cards P2-001 to P2-017 are created in the Backlog
list and stay there until the owner moves them to Ready.

---

## 1. Phase 1: what really works today

Checked on 30 Sep 2026 against the latest code (backend branch
`feature/ELM-009-admin-dashboard-filters` 8f7cbc9, frontend branch
`feature/ELM-010-responsive-full-flow` d0e79db), not against card status.

**Passed** (re-run on 30 Sep 2026 after the owner's review):
- Backend: 188 automated tests pass; no database changes missing
  (backend branch at fa4563f, which contains all Phase 1 backend work).
- Frontend: TypeScript type check and lint pass (d0e79db).
- Browser, by hand (Chromium, test admin account): admin dashboard shows the
  right counts; the Leave requests list shows all 12 requests with filters.
  Earlier cards (ELM-002 to ELM-010) have their own browser checks.

**Not verified** (the earlier "all checks pass" meant the backend tests
only, and should have said so):
- Frontend automated tests: there are none yet (P2-003).
- Safari and Firefox: not tested.
- Password-reset email delivery: no email account is connected (P2-002).
- The merged result on `main`: nothing is merged yet, so `main` has not
  been tested with Phase 1 in it (P2-001).
- Deployment: not started (ELM-011).

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

## 2. Owner decisions (30 Sep 2026)

1. **Approvals:** one reporting manager approves each request; Admin is the
   fallback when no manager is assigned. Nobody can approve their own request.
2. **Half days:** yes, morning and afternoon.
3. **Public holidays:** yes; Admin manages a yearly holiday list and those
   days do not count as leave.
4. **Email sender:** **pending.** The owner will confirm the sender address
   and provide the configuration securely. The sender must be configurable;
   no placeholder sender in production. Tracked as a blocker (P2-002).
5. **Team visibility:** employees see only their own leave; managers see
   their assigned team; Admin sees everyone.
6. **Hosting and retention:** **pending.** Do not assume a retention period
   and never delete leave history automatically.
7. **Carry-forward:** outside Phase 2.

Tasks affected by the pending decisions carry the **Pending decision** label:
P2-002, P2-010 and P2-011 (decision 4); P2-015 and P2-016 (decision 6).

---

## 3. Phase 2 features and tasks

Estimates are in developer-days for Jarvis, as ranges, and include tests and
browser checks. They assume the decisions above go with our suggestion and
that Phase 1 is merged first. Decisions 4 and 6 are still pending. `→` shows what a task depends on.

### Milestone 1: Foundation

| ID | Task | Done when | Estimate |
|---|---|---|---|
| P2-001 | Merge Phase 1 into `main` in both repositories | All 16 PRs merged in order; `main` passes all checks and runs the full flow | 0.5–1 |
| P2-002 | Connect the email account | A real reset code arrives in an inbox; failures are logged without codes or passwords | 0.5 (→ decision 4, pending) |
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
| P2-015 | Backup and restore | Written steps; a restore is tested on a separate database | 1–2 (→ decision 6, pending) |
| P2-016 | Operations guide | Settings, health check and how to roll back a release are documented | 1 (→ decision 6, pending) |
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

## 6. Task cards

One Trello card per task (P2-001 to P2-017) is in the **Backlog** list,
labelled Phase-2 plus a priority, with its milestone, dependencies and
acceptance criteria in the description. Nothing is started until the owner
moves a card to Ready. P2-001 to P2-003 close the Phase 1 gaps and come
first.

| Task | Labels | Card |
|---|---|---|
| P2-001 | CRITICAL, P0 | https://trello.com/c/UUT03bqC |
| P2-002 | CRITICAL, P0, Pending decision | https://trello.com/c/bEEl3Zjq |
| P2-003 | CRITICAL, P0 | https://trello.com/c/2Wg9YYoM |
| P2-004 | P0 | https://trello.com/c/WtupJL3P |
| P2-005 | P0 | https://trello.com/c/U8kMJfHE |
| P2-006 | P0 | https://trello.com/c/C64P0Aza |
| P2-007 | P1 | https://trello.com/c/8yRFhj9Y |
| P2-008 | P1 | https://trello.com/c/ZsKTxqJY |
| P2-009 | P2 | https://trello.com/c/JgPQQMhz |
| P2-010 | P1, Pending decision | https://trello.com/c/HbwK9auT |
| P2-011 | P1, Pending decision | https://trello.com/c/Lr5Tee8V |
| P2-012 | P1 | https://trello.com/c/W7xEE1Q0 |
| P2-013 | P1 | https://trello.com/c/Oa31Ia5S |
| P2-014 | P2 | https://trello.com/c/4b808RRH |
| P2-015 | P1, Pending decision | https://trello.com/c/3UhiLW8W |
| P2-016 | P2, Pending decision | https://trello.com/c/BSp1wGhF |
| P2-017 | P1 | https://trello.com/c/BFOHqU7K |
