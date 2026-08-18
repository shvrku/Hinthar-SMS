# Scaling Standards — Implementation Plan

Canonical write-up: **`Hinthar-Dashboard/docs/SCALING_IMPLEMENTATION_PLAN.md`**.

This SMS copy is a pointer so backend contributors see the same phase language.

Cross-repo plan aligns **Hinthar-SMS** and **Hinthar-Dashboard** with:

- `docs/API_STANDARDS.md` (this repo)
- `Hinthar-Dashboard/docs/FRONTEND_STANDARDS.md`

**Last status update:** 2026-08-17 — **this plan is complete** (phases 0–9).

Historical pointer only. Live contracts: `docs/API_STANDARDS.md` (this repo) and Dashboard `FRONTEND_STANDARDS.md`. Matching, owner hubs, and owner-read timetables landed after this table froze.

---

## Status at a glance

| Phase | Focus | Status |
|------:|-------|--------|
| 0–6 | Docs, roles, payroll scrap, pagination, matrix, API hygiene, check-in/QR | **Done** |
| 7 | Entity detail hubs + analytics + teacher cover (`actual_teacher`) | **Done** |
| 8 | Find sessions API filters + ISO Session DateTimes | **Done** |
| 9 | Matrix `null` vs absent, datetime bounds, audit `category`/`summary`, `GET /stats/` overview | **Done** |

### Shipped (SMS)

**Phase 9**

- Attendance matrix: missing cells are `null` (unmarked), not filled as `'absent'`.
- `people.AuditLog.category` + `summary`; `people.audit.log_event()`; generate-sessions muted to one summary.
- `GET /audit-logs/` is `IsStaffOrAbove`.
- `GET /stats/` adds `trends`, `student_series`, `recent_activity` (`class_sessions/overview_stats.py`). Migration: `people/0014_auditlog_category_summary`.
- Session list date filters via `class_sessions.datetime_bounds`.
- `GET /me/student/`, `GET /me/attendance-summary/`; student `link_user` / `unlink_user`.
- Check-in throttle `120/minute`.

**Phase 8**

- `GET /sessions/?timetable_slot_id=` (+ `date_from` / `date_to`) for slot occurrence lists.
- `GET /timetable-slots/?class_id=` (canonical; `class_obj_id` alias) — required for Find sessions / editors.
- Session DateTime **output** ISO-8601 (`SessionSerializer`, attendance-list nested times, generate summaries). Legacy `dd/mm/yy HH:MM:SS` still accepted on **input**.

**Phase 7**

- `GET /classes/{id}/attendance-summary/?range=` — campus + lesson separate.
- `GET /teachers/{id}/attendance-summary/?range=` — accountability + personal (derived).
- `Session.actual_teacher` / `AdHocSession.actual_teacher` (nullable; empty = taught as assigned).

**Earlier**

- Student attendance-summary, check-in overview, QR activate/deactivate, pagination, matrix `class_id` 400.

### Not part of this plan

Teacher portal / scoped querysets, a dedicated audit-logs UI (home already previews events), a global exception handler, and academic records are **new product work** — not incomplete scaling phases. Live OpenAPI: `/api/v1/docs/`.
