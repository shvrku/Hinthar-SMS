# Hinthar SMS — School Management System

API-first school management for people, classes, timetabling, sessions, attendance, campus check-in, and school communications (announcements / events).

**Payroll is archived / out of scope** for the current product cycle (`payroll/` app is unmounted).

## Standards & plans

| Doc | Purpose |
|-----|---------|
| [`docs/API_STANDARDS.md`](docs/API_STANDARDS.md) | Route naming, pagination, bulk/fetch/aggregate patterns, role hierarchy |
| [`docs/SCALING_IMPLEMENTATION_PLAN.md`](docs/SCALING_IMPLEMENTATION_PLAN.md) | Status pointer — **phases 0–9 complete** (full tables in the Dashboard copy) |


Interactive OpenAPI: `/api/v1/docs/` (Swagger UI).

## API Endpoints (live)

All under `/api/v1/`.


| Endpoint                                                                           | Description                                        |
| ---------------------------------------------------------------------------------- | -------------------------------------------------- |
| `GET /me/`                                                                         | Current user; **allowed when deactivated** (`is_active: false`) |
| `GET /me/student/`, `GET /me/attendance-summary/`                                  | Linked student profile / own analytics; **active accounts only** |
| `GET /students/{id}/`, `GET /students/{id}/attendance-summary/`                    | Staff+ any; owner student own record only          |
| `/users/`                                                                          | Accounts (admin; matching filters `linked` / `linkable`) |
| `POST /students/{id}/link_user/`, `POST …/unlink_user/`                            | Admin match Clerk account ↔ student                      |
| `POST /teachers/{id}/link_user/`, `POST …/unlink_user/`                            | Admin match Clerk account ↔ teacher                      |
| `GET /teachers/{id}/`, `GET /teachers/{id}/attendance-summary/`                    | Staff+ any; owner teacher own record only                |
| `GET /audit-logs/`                                                                 | Important events (staff+; `category` + `summary`)  |
| `/teachers/`, `/students/`, `/staff/`, `/subjects/`                                | People & catalog (+ `bulk_create` / `bulk_delete`) |
| `/classes/`, `/class-students/`                                                    | Cohorts & enrollment                               |
| `/timetable-slots/`                                                                | Recurring weekly slots                             |
| `/timetable/teacher/{id}/`, `/timetable/class/{id}/`                               | Weekly slot **lists** (plain arrays; staff+ / owner) |
| `/sessions/`, `/session-attendances/`                                              | Dated sessions & lesson attendance                 |
| `GET /attendance/matrix/`                                                          | Class attendance aggregate (scoped)                |
| `/adhoc-sessions/`, `/adhoc-session-attendances/`, `GET /adhoc-attendance/matrix/` | Tutoring / ad-hoc                                  |
| `/check-ins/` (+ `qr/`, `manual/`, `overview/`)                                    | Daily campus check-in                              |
| `GET /stats/`                                                                      | Counts, 30-day trends, enrollment series, recent activity |
| `/announcements/`, `/events/`, `/tags/`                                            | School communications (feed, registration, staff manage) |


## What It Does

- **People** — Teachers, students, staff, subjects; student QR activate / deactivate / regenerate
- **Classes** — Cohorts and enrollment
- **Timetable → sessions** — Recurring slots generate dated sessions; `actual_teacher` substitute
- **Lesson attendance** — Per-session status + class matrices (`null` = unmarked, not absent)
- **Campus check-in** — QR / manual daily presence + school/class overview
- **Overview** — `GET /stats/` for dashboard KPIs and a filtered audit preview
- **Auth** — Clerk JWT; roles on Django `User` (`admin` > `staff` > `terminal` > `teacher` > `student` > `pending`)



## Tech Stack


| Layer    | Technology                       |
| -------- | -------------------------------- |
| Backend  | Django 5 + Django REST Framework |
| Database | PostgreSQL                       |
| Auth     | Clerk (OIDC/JWT)                 |
| API Docs | drf-spectacular (OpenAPI 3)      |



## Status

See [`docs/SCALING_IMPLEMENTATION_PLAN.md`](docs/SCALING_IMPLEMENTATION_PLAN.md). Current cycle is **done**:

- [x] Role helpers + frontend gates
- [x] List pagination + server `q` search
- [x] Attendance matrix filters + route split + ad-hoc Add Students
- [x] Matrix `class_id` required (400) + Sessions Take roll deep links
- [x] Remove payroll residue from live models
- [x] Check-in correction UI (`DELETE /check-ins/{id}/` + `/check-in/corrections`)
- [x] Check-in overview aggregate (class-first, checked-in / missing)
- [x] QR token activate / deactivate
- [x] Student / class / teacher attendance summaries
- [x] Live `GET /stats/` (trends, enrollment series, recent activity)
- [x] Audit logs with `category` / `summary` (staff+)
- [x] OpenAPI live at `/api/v1/docs/`

Later product (not this plan): teacher portal queryset scoping, academic records (exams / results).


## OpenAPI schema

Interactive docs: `/api/v1/docs/` (Swagger UI).

Optional: regenerate a checked-in schema file when the environment has DB settings available:

```bash
python manage.py spectacular --file docs/openapi-schema.yml
```



## License

Private — internal school administration use.
