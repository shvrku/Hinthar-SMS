# Scaling Standards — Implementation Plan

Canonical status and full task tables live in the Dashboard copy — **edit that file first**:

`Hinthar-Dashboard/docs/SCALING_IMPLEMENTATION_PLAN.md`

This SMS copy is a short pointer so backend contributors see the same phase language.

Cross-repo plan aligns **Hinthar-SMS** and **Hinthar-Dashboard** with:

- `docs/API_STANDARDS.md` (this repo)
- `Hinthar-Dashboard/docs/FRONTEND_STANDARDS.md`

**Last status update:** 2026-08-06 (Phase 5 API hygiene done; global exception handler deferred).

---

## Status at a glance

| Phase | Focus | Status |
|------:|-------|--------|
| 0 | Docs / payroll freeze | Mostly done |
| 1 | `people/roles.py` + permissions + frontend gates | **Done** |
| 2 | Scrap payroll UI + drop `paid` / rate / bank | **Done** |
| 3 | Pagination 50/max 200 + server list/`q` search | **Done** |
| 4 | Matrix filters + route split + `class_id` 400 + Take roll | **Done** |
| 5 | Bulk / OpenAPI / filter hygiene | **Done** (global exception handler deferred) |
| 6 | Design system / check-in UX / QR lifecycle | **Mostly done** — QR activate/deactivate **done** |
| 7 | Entity detail hubs + analytics + teacher cover | **In progress** — student hub **done**; class/teacher next |

### Backend leftovers that matter

- Teacher (and student) **scoped** querysets before teacher portal.
- Regenerate Spectacular export when env allows (`python manage.py spectacular --file docs/openapi-schema.yml`).
- **Next:** class attendance summary aggregate; teacher attendance + substitute models.

### Shipped recently (SMS)

- Default pagination; `q` filters on people/session/check-in lists.
- Matrix payloads include student `unique_code`.
- Ad-hoc attendance `bulk_upsert` uses `SessionAttendance.STATUS_CHOICES`.
- Payroll fields removed; excused attendance status exists.
- Attendance matrix rejects missing/`all`/`adhoc` `class_id` with **400**; unknown class **404**.
- `DELETE /check-ins/{id}/` (+ bulk) with `auto_marked_by_checkin` revert.
- **`GET /check-ins/overview/`** — classes / class / school (`class_id=all`, `status=`, paginated) / search modes + tests.
- **`Student.check_in_token_active`** + activate/deactivate/regenerate actions; QR + lookup reject inactive tokens.
- Lookup deactivated QR → **403** with nested safe `student` summary (for terminal card).
- **`GET /students/{id}/attendance-summary/?range=week|month|all`** — campus vs lesson labeled separately.
- **Phase 5:** `bulk_upsert` OpenAPI (`records` preferred); `class_id` canonical on session-attendances + class-students; page-boundary tests; error freeze without global handler.

---

## Principles

1. Standards first; migrate old endpoints with temporary aliases.
2. Backend enforces authorization; frontend gates are UX only.
3. Phased, shippable PRs — no big-bang rewrite.
4. Payroll frozen (`payroll/` unmounted); live residue removed.

---

## Phase 3 — Adding a paginated route (backend checklist)

1. ViewSet with filtered `get_queryset()` (support `q` when the UI searches).
2. Use default `StandardPageNumberPagination` (`page`, `page_size`).
3. Register kebab-case plural route.
4. Document filters; canonical names `class_id`, `date_from`, `date_to`.
5. Tests for page disjointness + stable `count`.
6. Frontend consumes envelope — no client-only slice of full download.

Aggregates (`/attendance/matrix/`, `/adhoc-attendance/matrix/`, `/stats/`, `/check-ins/overview/`, `/students/{id}/attendance-summary/`) stay **scoped** (overview school/search modes are paginated).

---

## Moving forward

See Dashboard plan **Phase 7** and **Moving forward**. SMS-first next slices:

```text
1  Class attendance summary aggregate
2  Teacher attendance + substitute models/API (design spike first)
3  Teacher-scoped querysets (if teacher login imminent)
4  Optional: regenerate OpenAPI schema file + global exception handler (deferred from Phase 5)
```
