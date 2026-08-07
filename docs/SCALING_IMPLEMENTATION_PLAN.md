# Scaling Standards — Implementation Plan

Canonical status and full task tables live in the Dashboard copy — **edit that file first**:

`Hinthar-Dashboard/docs/SCALING_IMPLEMENTATION_PLAN.md`

This SMS copy is a short pointer so backend contributors see the same phase language.

Cross-repo plan aligns **Hinthar-SMS** and **Hinthar-Dashboard** with:

- `docs/API_STANDARDS.md` (this repo)
- `Hinthar-Dashboard/docs/FRONTEND_STANDARDS.md`

**Last status update:** 2026-08-07 (Phase 8 Find sessions filters + ISO DateTime + Phase 7 hubs).

---

## Status at a glance

| Phase | Focus | Status |
|------:|-------|--------|
| 0–6 | Docs, roles, payroll scrap, pagination, matrix, API hygiene, check-in/QR | **Done** |
| 7 | Entity detail hubs + analytics + teacher cover (`actual_teacher`) | **Done** |
| 8 | Find sessions API filters + ISO Session DateTimes | **Done** |

### Backend leftovers that matter

- Teacher (and student) **scoped** querysets before teacher portal.
- Regenerate Spectacular export when env allows (`python manage.py spectacular --file docs/openapi-schema.yml`).
- Optional global DRF exception handler.
- Future: teacher check-in writing `actual_teacher` (staff assign substitute via Sessions / Find sessions today).

### Shipped recently (SMS)

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

---

## Moving forward

```text
1  Optional: regenerate OpenAPI schema file + global exception handler
2  Teacher-scoped querysets (if teacher login imminent)
3  Teacher check-in → actual_teacher (when product asks)
```
