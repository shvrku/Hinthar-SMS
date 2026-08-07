# Hinthar-SMS API Standards

Standards for the Django REST Framework backend as the school management system scales (students, teachers, classes, sessions, attendance). **Payroll is out of scope** — leave the archived `payroll/` app alone; live model residue (`paid`, rates, bank) has been removed (see implementation plan).

Base path: `/api/v1/`

---

## 1. Role hierarchy

Canonical order (highest privilege first):

| Level | Role        | Intent |
|------:|-------------|--------|
| 5     | `admin`     | Full system control |
| 4     | `staff`     | Day-to-day school operations (CRUD people, classes, sessions, attendance) |
| 3     | `terminal`  | Slightly elevated kiosk account: **read** most operational data + **write** only on check-in / terminal routes |
| 2     | `teacher`   | Own timetable, own sessions, own class attendance (scoped) |
| 1     | `student`   | Own profile, own attendance/check-in token (scoped) |

Roles live on `people.User.role` (Django), not Clerk public metadata, until an explicit sync policy is adopted.

### Hierarchy helpers (target API)

Prefer **level checks** over ad-hoc `role in (...)` lists sprinkled across views.

```python
# people/roles.py (implemented)
ROLE_RANK = {
    'student': 1,
    'teacher': 2,
    'terminal': 3,
    'staff': 4,
    'admin': 5,
}

def role_rank(user) -> int:
    if not user or not user.is_authenticated:
        return 0
    return ROLE_RANK.get(getattr(user, 'role', None), 0)

def is_admin(user) -> bool:
    return role_rank(user) >= ROLE_RANK['admin']

def is_staff_or_above(user) -> bool:
    return role_rank(user) >= ROLE_RANK['staff']

def is_terminal_or_above(user) -> bool:
    return role_rank(user) >= ROLE_RANK['terminal']

def is_teacher_or_above(user) -> bool:
    return role_rank(user) >= ROLE_RANK['teacher']

def is_at_least(user, role: str) -> bool:
    return role_rank(user) >= ROLE_RANK[role]
```

### Permission classes (target naming)

Map helpers to DRF permission classes with **predictable names**:

| Class | Meaning |
|-------|---------|
| `IsAdmin` | Admin only |
| `IsStaffOrAbove` | Admin + staff (write ops default) |
| `IsTerminalOrAbove` | Admin + staff + terminal |
| `IsTeacherOrAbove` | Admin + staff + terminal + teacher |
| `IsAuthenticatedRole` | Any provisioned role |
| `IsOwnerTeacher` / `IsOwnerStudent` | Object ownership (keep) |
| `CanCheckIn` | Terminal write + staff/admin/teacher for manual check-in |
| `ReadForTerminalWriteForStaff` | SAFE for terminal+; write for staff+ |

**Default** (`REST_FRAMEWORK['DEFAULT_PERMISSION_CLASSES']`):

- Keep denying unauthenticated users.
- Prefer `IsStaffOrAbove` for mutating ViewSets.
- Do **not** use bare `IsAuthenticated` for list endpoints that return school-wide data — teachers/students must be queryset-scoped.

### Terminal rules

- **Read:** most list/retrieve endpoints allowed when `IsTerminalOrAbove` (or SAFE methods under a mixed class).
- **Write:** only check-in routes (`POST /check-ins/qr/`, `POST /check-ins/manual/`) and any future terminal-specific actions.
- Terminal must **not** create/update/delete students, teachers, classes, sessions, or attendance matrices.

---

## 2. Route naming conventions

### Resource collections (CRUD)

Use **kebab-case plural nouns**:

| Good | Avoid |
|------|--------|
| `/students/` | `/student/`, `/getStudents/` |
| `/class-students/` | `/timetable-students/` (stale docs) |
| `/timetable-slots/` | `/slots/` |
| `/session-attendances/` | `/attendances/` (ambiguous with check-ins) |
| `/adhoc-sessions/` | `/ad-hoc-sessions/` (pick one; current code uses `adhoc`) |

Detail: `/resource/{id}/` with trailing slash (Django `APPEND_SLASH`).

### Action routes (non-CRUD)

| Kind | Pattern | Example |
|------|---------|---------|
| Nested resource action | `POST/PATCH /resource/{id}/{action}/` | `/sessions/{id}/status/` |
| Collection action | `POST\|DELETE /resource/{action}/` | `/students/bulk_create/` |
| Aggregate / report | `GET /{domain}/{report}/` | `/attendance/matrix/` |
| Generation | `POST /resource/generate/{scope_id}/` | `/sessions/generate/{class_id}/` |
| Identity | `GET /me/` | current user |

Action names: **snake_case** matching DRF `@action(url_path=...)` defaults (`bulk_create`, `bulk_delete`, `bulk_upsert`).

### Fetch vs bulk vs aggregate

| Type | When | Shape |
|------|------|--------|
| **Fetch (list)** | Browse / tables / selects | Paginated envelope (see §3) |
| **Fetch (detail)** | Single entity edit | Single object |
| **Bulk create** | CSV import, mass enroll | `POST .../bulk_create/` |
| **Bulk delete** | Multi-select delete | `DELETE .../bulk_delete/` |
| **Bulk upsert** | Grid saves (attendance) | `POST .../bulk_upsert/` |
| **Aggregate** | Matrices, stats, dashboards | Dedicated GET under domain prefix |

Do **not** overload list endpoints with `?summary=true` for matrix data — use aggregate routes.

---

## 3. Pagination standard

### Current state

Global pagination is **on** via `config.pagination.StandardPageNumberPagination`:

- Default `page_size` = **50**
- `max_page_size` = **200**
- Query params: `page`, `page_size`

List ViewSets that can grow (students, teachers, sessions, attendances, check-ins, users, …) return the DRF envelope. Tiny catalogs (subjects, classes, timetable-slots) may set `pagination_class = None`.

Unbounded list UIs must also support server-side search (`q`) and structured filters — never fetch-all then filter in the browser.

### Standard envelope

```json
{
  "count": 1234,
  "next": "https://…/api/v1/sessions/?page=3&page_size=50",
  "previous": "https://…/api/v1/sessions/?page=1&page_size=50",
  "results": [ … ]
}
```

| Query param | Meaning |
|-------------|---------|
| `page` | 1-based page index |
| `page_size` | Optional override (capped at `max_page_size`) |

### Which endpoints stay unpaginated

| Endpoint | Reason |
|----------|--------|
| `GET /attendance/matrix/` | Scoped aggregate; size bounded by filters |
| `GET /adhoc-attendance/matrix/` | Same |
| `GET /check-ins/overview/` | Scoped aggregate; class/summary bounded; search + `class_id=all` paginated |
| `GET /stats/` | Fixed small payload |
| `GET /me/` | Single object |
| Small catalogs optionally | subjects / classes — may stay unpaginated **or** paginated for consistency |

Timetable helper views that currently fake `{count, next: null, previous: null, results}` should either use real pagination or return a plain list — do not fake envelopes.

### How to add a new paginated list route

Follow this checklist every time:

1. **ViewSet** inherits `ModelViewSet` (or `ReadOnlyModelViewSet`) with a filtered `get_queryset()`.
2. Do **not** set `pagination_class = None` unless the resource is intentionally unbounded-safe and tiny.
3. Register on the router: `router.register(r'my-resources', MyResourceViewSet, basename='my-resource')`.
4. Document OpenAPI parameters: `page`, `page_size`, plus domain filters.
5. Support filters via query params (prefer `django-filter` `FilterSet` going forward):
   - FKs: `student_id`, `class_id` / `class_obj_id` (document one canonical name; accept alias only if documented)
   - Dates: `date_from`, `date_to` (ISO `YYYY-MM-DD`); optional aliases `start_date` / `end_date`
6. Frontend: call with `page` / `page_size`; render `StandardTablePagination` from `count` / `next` / `previous` — **do not** fetch-all then slice.
7. Add a test: page 1 size N, page 2 disjoint, `count` stable.
8. If the UI needs “all for a select”, add either:
   - `page_size` up to max for small sets, or
   - a dedicated lightweight endpoint (e.g. `/students/options/?class_id=`) returning `{id, label}[]` capped.

### Filter aliases policy

Pick **one canonical name** per filter in new code:

| Canonical | Deprecated aliases (keep temporarily) |
|-----------|----------------------------------------|
| `class_id` | `class_obj_id` (internal FK may remain `class_obj`) |
| `date_from` / `date_to` | `start_date` / `end_date` |
| `adhoc_session_id` | `ad_hoc_session_id` (model FK remains `ad_hoc_session` / `ad_hoc_session_id`) |

Document aliases in OpenAPI `deprecated=True` until removed.

**`class_id` is canonical** on:

- `GET /session-attendances/` (filters `session__class_obj_id`; `class_obj_id` alias)
- `GET /class-students/` (filters enrollment `class_obj_id`; `class_obj_id` alias)
- `GET /timetable-slots/` (filters `class_obj_id`; `class_obj_id` alias) — **required** for Find sessions / class editors; do not return all-school slots when the UI is class-scoped
- `GET /sessions/` and matrix/overview aggregates (already documented)

Clients should send `class_id`; servers may still accept `class_obj_id` during the alias window.

### Session list filters (Find sessions)

`GET /sessions/` supports (among others):

| Param | Meaning |
|-------|---------|
| `timetable_slot_id` | Occurrences generated from that weekly slot |
| `class_id` | Sessions for one class cohort |
| `date_from` / `date_to` | Inclusive calendar bounds on `start_time` date (`YYYY-MM-DD`) |
| `teacher_id` | Assigned teacher filter (existing) |

Paginate as usual. Dashboard Find sessions loads the slot table with `timetable_slot_id` + date range — not a fetch-all of school sessions.

---

## 4. Bulk route standard

Shared mixin: `people.views.BulkOperationsMixin` (keep as the single implementation).

| Action | Method | Path | Body | Response |
|--------|--------|------|------|----------|
| Bulk create | `POST` | `/resource/bulk_create/` | `{"items":[…]}` or `[…]` | `{created_count, items}` `201` |
| Bulk delete | `DELETE` | `/resource/bulk_delete/` | `{"ids":[…]}` | `{deleted_count, deleted_ids}` `200` |
| Bulk upsert | `POST` | `/resource/bulk_upsert/` | Prefer `{"records":[…]}`; bare `[…]` fallback | `{created_count, updated_count}` `200` |

Rules:

- Prefer `{"records":[…]}` for bulk upsert request bodies; accept a bare list only as a temporary client fallback.
- Always wrap writes in `transaction.atomic()`.
- Validate with the same serializer as create/update where possible.
- Block deletes that violate business rules (document any remaining locks in the action docstring).
- Bulk upsert is **attendance-only** unless a new domain proves the same pattern.
- Ad-hoc attendance records use client field **`adhoc_session_id`** (aliases `ad_hoc_session_id` / nested keys may be accepted in code). The model FK remains `ad_hoc_session` / `ad_hoc_session_id`.

---

## 5. Aggregate / matrix routes

### Class session attendance matrix (keep as dedicated route)

```
GET /api/v1/attendance/matrix/
```

**Required / recommended query params:**

| Param | Required | Purpose |
|-------|----------|---------|
| `class_id` | **Yes** (integer) | Scope to one class cohort |
| `month` + `year` | One of range modes | Calendar month (default: current local month if no dates) |
| `date_from` + `date_to` | One of range modes | Inclusive date window |
| `subject_id` | Optional | Filter sessions by subject |
| `teacher_id` | Optional | Filter sessions by teacher |

Reject `class_id` missing / `all` / `adhoc` with **400**. Unknown integer IDs return **404**.

**Response contract** (stable):

```json
{
  "class_id": 12,
  "sessions": [
    {
      "id": 1,
      "start_time": "ISO-8601",
      "end_time": "ISO-8601",
      "subject": "…",
      "subject_id": 3,
      "teacher_id": 2,
      "teacher_name": "…",
      "class_obj_id": 12,
      "class_name": "…",
      "status": "scheduled|completed|…"
    }
  ],
  "students": [
    {
      "id": 5,
      "name": "…",
      "user_id": null,
      "records": { "1": "present|absent|late" }
    }
  ],
  "attendances": [
    { "id": 9, "session_id": 1, "student_id": 5, "status": "present" }
  ]
}
```

Datetime: **ISO-8601 everywhere** for API `DateTimeField` **responses** (including
`Session.start_time` / `end_time`, nested session times on attendance lists, and
generate-summary timestamps). Date-only fields and query params use
`YYYY-MM-DD`. Clock-only fields (timetable / ad-hoc) use `HH:MM:SS`.
Legacy `dd/mm/yy HH:MM:SS` may still be accepted on **input** for older clients;
do **not** emit it on serializers. Dashboard parses via `parseBackendDateTime` /
related helpers in `lib/utils.ts` — never rely on bare `new Date(string)` for
backend values.

### Ad-hoc matrix

```
GET /api/v1/adhoc-attendance/matrix/
```

Filters: `subject_id`, `teacher_id`, `date_from`/`date_to`, `month`/`year`.

Do **not** fall back to “all students in the school” when no rows match — return empty `students: []`.

### Check-in overview aggregate

```
GET /api/v1/check-ins/overview/
```

Server-side aggregate for the campus check-in overview so the client never pulls
whole tables (`students`, `class-students`, `check-ins`) and filters in the
browser. `IsStaffOrAbove`. All modes are scoped to a single day via `date`
(`YYYY-MM-DD`, defaults to server local date). Three mutually exclusive modes,
chosen by query params (checked in this order):

| Params | `mode` | Returns |
|--------|--------|---------|
| `search=<text>` | `search` | Paginated student matches (`name`/`unique_code` `icontains`) across **all** classes; each row has `student_id`, `name`, `unique_code`, `class_id`, `class_label`, and that day's `check_in` (or `null`). Envelope: `count`, `page`, `page_size`, `num_pages`, `results`. `page_size` default 50, max 200. |
| `class_id=all` | `school` | Paginated unique students across every class. Full-day `arrived`/`total` always returned. Optional `status=missing\|arrived` filters one column for the dual Missing / Checked-in UI (each side paginated independently). Envelope: `count`, `page`, `page_size`, `num_pages`, `students[]` with `class_id`/`class_label` + `check_in`\|`null`; echoes `status` when filtered. Same page defaults as search. |
| `class_id=<int>` | `class` | One class roster joined to the day's status: `class`, `arrived`, `total`, `students[]` (`id`, `name`, `unique_code`, `check_in`\|`null`). Unknown id → 404. Unpaginated (bounded by class size). |
| _(none)_ | `classes` | Lightweight picker summary: `classes[]` with `id`, `label`, `arrived`, `total` per class (ordered by level then cohort). |

`check_in` is `null` or `{ id, timestamp, check_in_type }`. Campus presence only —
independent of lesson attendance (`/attendance/matrix/`). Invalid `date`,
`class_id`, `status`, `page`, or `page_size` → 400.

### Student attendance summary aggregate

```
GET /api/v1/students/{id}/attendance-summary/?range=week|month|all
```

Staff+ only. Scoped to one student and a preset window (`week` = Mon–today local,
`month` = month start–today, `all` = enrollment_date–today). Returns campus
check-in and lesson roll **as separate objects** — never a single blended rate.

Shape (conceptual):

```json
{
  "range": "month",
  "date_from": "2026-08-01",
  "date_to": "2026-08-06",
  "campus": {
    "days_in_range": 6,
    "days_checked_in": 4,
    "rate": 0.666…,
    "daily": [{"date": "…", "checked_in": true}]
  },
  "lesson": {
    "total_sessions": 12,
    "present": 8,
    "late": 1,
    "absent": 2,
    "excused": 1,
    "rate_attended": 0.818…,
    "by_status": [{"status": "present", "count": 8}],
    "by_class": [{"class_id": 1, "class_label": "…", "present": …, "total": …}],
    "trend": [{"date": "…", "present": 1, "late": 0, "absent": 0, "excused": 0}]
  }
}
```

Invalid / missing `range` → **400** `{"error": "range must be one of: …"}`.

### Class / teacher attendance summary aggregates

```
GET /api/v1/classes/{id}/attendance-summary/?range=week|month|all
GET /api/v1/teachers/{id}/attendance-summary/?range=week|month|all
```

Staff+ only. Same `range` semantics as the student summary. Campus check-in and
lesson roll stay **separately labeled** in the payload (never one blended rate).

- **Class:** roster-scoped campus presence + lesson marks for that cohort.
- **Teacher:** accountability (student rolls on sessions taught) + personal
  presence derived from session status and assigned vs `actual_teacher`.

`actual_teacher` on `Session` / `AdHocSession` is nullable: `null` means taught
as assigned; a set FK means a **substitute**. Same-as-assigned values normalize
to null on save. Teacher check-in writing this field is deferred.

### Student check-in QR token lifecycle

| Action | Method / path | Notes |
|--------|---------------|--------|
| Read token | `GET /students/{id}/check_in_token/` | Owner student, staff, or admin |
| Regenerate | `POST /students/{id}/regenerate_check_in_token/` | Staff+; returns new token and sets `check_in_token_active: true` |
| Activate | `POST /students/{id}/activate_check_in_token/` | Staff+; `{ "check_in_token_active": true }` |
| Deactivate | `POST /students/{id}/deactivate_check_in_token/` | Staff+; soft-disable without rotating secret |

`Student.check_in_token_active` defaults to `true`. Inactive tokens:

- `POST /check-ins/qr/` → **403** `{"error": "Check-in token is deactivated"}`
- `POST /check-ins/lookup/` (token path) → **403** with `error` **and** a safe nested `student` summary for the terminal confirmation card (`id`, `name`, `unique_code`, `class_name`, `checked_in_today`, `method`, `check_in_token_active: false`). Never returns the raw token.

Student list/detail serializers expose `check_in_token_active` only to staff/admin (same visibility rules as the token itself).

### When to add a new matrix / overview route

Add a dedicated aggregate route when:

1. The UI needs a **student × session (or day) grid**, or
2. Building the same view would require N+1 list calls, or
3. Scope is naturally bounded by class + date range.

Suggested future routes (if product needs them):

| Route | Scope |
|-------|--------|
| `GET /attendance/matrix/` | Class lesson roll (exists) |
| `GET /adhoc-attendance/matrix/` | Tutoring roll (exists) |
| `GET /check-ins/overview/` | Daily campus presence by class/date + school-wide search (**implemented**, see above) |
| `GET /students/{id}/attendance-summary/` | Per-student campus + lesson analytics (**implemented**, see above) |
| `GET /classes/{id}/attendance-summary/` | Per-class campus + lesson analytics (**implemented**, see above) |
| `GET /teachers/{id}/attendance-summary/` | Teacher accountability + personal (**implemented**, see above) |
| `GET /attendance/session/{id}/roster/` | Single-session roster + statuses (optional split from matrix) |

---

## 6. Error & response conventions

**Error freeze (this cycle):** domain handlers return `{"error": "…"}` plus an optional nested safe context object when the UI needs it (e.g. deactivated QR lookup `student`). DRF field validation errors stay as DRF’s default shape. **No global exception handler** this cycle — do not invent new top-level keys beyond `error` / DRF norms / documented nested context.

| Situation | Status | Body |
|-----------|--------|------|
| Validation | 400 | DRF field errors or `{"error": "…"}` for non-field |
| Auth missing | 401 | DRF default |
| Forbidden role | 403 | DRF default |
| Domain forbid (e.g. deactivated QR) | 403 | `{"error": "…"}`; may include a **safe** nested context object (e.g. `student`) for UI — never secrets |
| Not found | 404 | DRF default |
| Conflict (e.g. duplicate check-in) | 409 | `{"error": "…"}` |
| Success create | 201 | Object or bulk payload |
| Success other | 200 | Object / envelope / aggregate |

A uniform `{detail, code, fields?}` global handler remains deferred to a later hygiene pass.

---

## 7. Payroll (scrap / freeze)

- Keep `payroll/` app **unmounted** and commented.
- Live residue removed: `Session.paid`, `AdHocSession.paid`, `Teacher.default_rate`, `Teacher.bank_details`, paid-delete guards.
- Do not advertise payroll in README or OpenAPI tags.
- No new payroll fields or routes until a dedicated finance milestone.

---

## 8. Docs that must stay truthful

When changing list pagination or route names, update in the same PR:

- This file (`docs/API_STANDARDS.md`)
- OpenAPI descriptions on the view
- Dashboard `lib/api.ts` client helpers
- `docs/SCALING_IMPLEMENTATION_PLAN.md` status if phase completion changes
- Dashboard `docs/FRONTEND_STANDARDS.md` when UX contracts change
