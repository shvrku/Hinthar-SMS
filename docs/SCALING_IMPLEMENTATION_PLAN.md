# Scaling Standards — Implementation Plan

Canonical status and full task tables live in the Dashboard copy — **edit that file first**:

`Hinthar-Dashboard/docs/SCALING_IMPLEMENTATION_PLAN.md`

This SMS copy is a short pointer so backend contributors see the same phase language.

Cross-repo plan aligns **Hinthar-SMS** and **Hinthar-Dashboard** with:

- `docs/API_STANDARDS.md` (this repo)
- `Hinthar-Dashboard/docs/FRONTEND_STANDARDS.md`

**Last status update:** 2026-08-06.

---

## Status at a glance

| Phase | Focus | Status |
|------:|-------|--------|
| 0 | Docs / payroll freeze | Mostly done |
| 1 | `people/roles.py` + permissions + frontend gates | **Done** |
| 2 | Scrap payroll UI + drop `paid` / rate / bank | **Done** |
| 3 | Pagination 50/max 200 + server list/`q` search | **Done** |
| 4 | Matrix filters + route split + `class_id` 400 + Take roll | **Done** |
| 5 | Bulk / OpenAPI / filter hygiene | **Partial** |
| 6 | Design system / check-in UX / QR activate-deactivate | **Partial** |

### Backend leftovers that matter

- Refresh Spectacular/OpenAPI to match live routes and pagination/`q` params.
- Page-boundary tests on hot list ViewSets where missing.
- Teacher (and student) **scoped** querysets before teacher portal.
- Check-in: overview aggregate by class, QR token activate/deactivate (correction delete shipped).
- Analytics aggregates (student/teacher/class summaries) — not started.

### Shipped recently (SMS)

- Default pagination; `q` filters on people/session/check-in lists.
- Matrix payloads include student `unique_code`.
- Ad-hoc attendance `bulk_upsert` uses `SessionAttendance.STATUS_CHOICES` (fix AttributeError).
- Payroll fields removed via migrations; excused attendance status exists.
- Attendance matrix rejects missing/`all`/`adhoc` `class_id` with **400**; unknown class **404**.
- `DELETE /check-ins/{id}/` for staff mis-tap correction (terminal cannot delete).

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

Aggregates (`/attendance/matrix/`, `/adhoc-attendance/matrix/`, `/stats/`) stay **unpaginated** but **strictly scoped**.

---

## Moving forward

See Dashboard plan **“Moving forward (recommended next work)”**. For SMS-first slices: check-in correction + QR activate/deactivate → Phase 5 OpenAPI + tests → teacher scoping → analytics summary endpoints.
