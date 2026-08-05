# Scaling Standards — Implementation Plan

Canonical copy for the SMS repo. Prefer the Dashboard copy if both diverge during edits: `Hinthar-Dashboard/docs/SCALING_IMPLEMENTATION_PLAN.md`.

Cross-repo plan to align **Hinthar-SMS** and **Hinthar-Dashboard** with:

- `docs/API_STANDARDS.md` (this repo)
- `Hinthar-Dashboard/docs/FRONTEND_STANDARDS.md`

---

## Principles

1. Standards first; migrate old endpoints with temporary aliases.
2. Backend enforces authorization; frontend gates are UX only.
3. Phased, shippable PRs — no big-bang rewrite.
4. Payroll frozen (`payroll/` unmounted); remove live residue next.

---

## Phase overview

| Phase | Focus | Effort |
|------:|-------|--------|
| 0 | Docs truthfulness, freeze payroll scope, remove dead nav | 0.5–1d |
| 1 | `people/roles.py` hierarchy helpers + DRF permission audit + frontend `RequireRole` | 2–4d |
| 2 | Scrap payroll UI; then deprecate `paid` / rate / bank in API | 1–2d + follow-up |
| 3 | Standard page pagination (50/max 200); migrate list pages off fetch-all | 3–5d |
| 4 | Matrix: honor `subject_id`/`teacher_id`; require `class_id`; split attendance UX routes | 3–5d |
| 5 | Bulk/filter/OpenAPI hygiene | 2–3d |
| 6 | shadcn preset, merge `/` + `/dashboard`, shared dialogs | ongoing |

---

## Phase 1 — Permissions (detail)

**Hierarchy:** Admin (5) > Staff (4) > Terminal (3) > Teacher (2) / Student (1).

Add:

```python
# people/roles.py
ROLE_RANK = {'student': 1, 'teacher': 2, 'terminal': 3, 'staff': 4, 'admin': 5}
# is_admin, is_staff_or_above, is_terminal_or_above, is_teacher_or_above, is_at_least
```

Wire into `people/permissions.py`. Default mutating access: **staff+**. Terminal: read + check-in write only. Teachers/students: **scoped querysets**, not school-wide `IsAuthenticated` lists.

---

## Phase 3 — Adding a paginated route (backend checklist)

1. ViewSet with filtered `get_queryset()`.
2. Use default `StandardPageNumberPagination` (`page`, `page_size`).
3. Register kebab-case plural route.
4. Document filters; canonical names `class_id`, `date_from`, `date_to`.
5. Tests for page disjointness + stable `count`.
6. Frontend consumes envelope — no client-only slice of full download.

Aggregates (`/attendance/matrix/`, `/stats/`) stay **unpaginated** but **strictly scoped**.

---

## Phase 4 — Matrix routes

Keep:

- `GET /api/v1/attendance/matrix/?class_id=&month=&year=` (or date range + subject/teacher)
- `GET /api/v1/adhoc-attendance/matrix/?…`

Frontend target: `/attendance/class/[classId]?…` with filters in the query string; pass all scopes to the API.

---

## PR sequence

```text
PR-A  docs (standards + plan)
PR-B  roles + permissions (SMS)
PR-C  role gates (Dashboard)
PR-D  scrap payroll UI (Dashboard)
PR-E  pagination backend + client envelope
PR-F  paginated list pages (Dashboard)
PR-G  matrix filters + attendance UX split
PR-H  payroll field deprecation (SMS)
PR-I  design system / overview merge
```

---

## Open decisions

1. Terminal allowed to read attendance matrix, or staff+ only?
2. Teacher portal this quarter vs staff-only?
3. Drop `paid` entirely vs keep as non-payroll flag?
4. Clerk role sync vs Django as source of truth (recommend Django until designed)?

See the Dashboard plan doc for full task tables, success metrics, and UX rationale.
