# Hinthar SMS — School Management System

API-first school management for people, classes, timetabling, sessions, attendance, and campus check-in.

**Payroll is archived / out of scope** for the current product cycle (`payroll/` app is unmounted).

## Standards & plans


| Doc                                                                          | Purpose                                                                         |
| ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| `[docs/API_STANDARDS.md](docs/API_STANDARDS.md)`                             | Route naming, pagination, bulk/fetch/aggregate patterns, role hierarchy helpers |
| `[docs/SCALING_IMPLEMENTATION_PLAN.md](docs/SCALING_IMPLEMENTATION_PLAN.md)` | Phased migration to those standards                                             |


Interactive OpenAPI: `/api/v1/docs/` (Swagger UI).

## API Endpoints (live)

All under `/api/v1/`.


| Endpoint                                                                           | Description                                        |
| ---------------------------------------------------------------------------------- | -------------------------------------------------- |
| `GET /me/`                                                                         | Current user profile                               |
| `/users/`, `/audit-logs/`                                                          | Accounts / audit (admin)                           |
| `/teachers/`, `/students/`, `/staff/`, `/subjects/`                                | People & catalog (+ `bulk_create` / `bulk_delete`) |
| `/classes/`, `/class-students/`                                                    | Cohorts & enrollment                               |
| `/timetable-slots/`                                                                | Recurring weekly slots                             |
| `/timetable/teacher/{id}/`, `/timetable/class/{id}/`                               | Scoped timetable helpers                           |
| `/sessions/`, `/session-attendances/`                                              | Dated sessions & lesson attendance                 |
| `GET /attendance/matrix/`                                                          | Class attendance aggregate (scoped)                |
| `/adhoc-sessions/`, `/adhoc-session-attendances/`, `GET /adhoc-attendance/matrix/` | Tutoring / ad-hoc                                  |
| `/check-ins/` (+ `qr/`, `manual/`)                                                 | Daily campus check-in                              |
| `GET /stats/`                                                                      | System-wide counts                                 |




## What It Does

- **People** — Teachers, students, staff, subjects
- **Classes** — Cohorts and enrollment
- **Timetable → sessions** — Recurring slots generate dated sessions
- **Lesson attendance** — Per-session status + class matrices
- **Campus check-in** — QR / manual daily presence
- **Auth** — Clerk JWT; roles on Django `User` (`admin` > `staff` > `terminal` > `teacher` / `student`)



## Tech Stack


| Layer    | Technology                       |
| -------- | -------------------------------- |
| Backend  | Django 5 + Django REST Framework |
| Database | PostgreSQL                       |
| Auth     | Clerk (OIDC/JWT)                 |
| API Docs | drf-spectacular (OpenAPI 3)      |




## Roadmap

- [ ] Role helpers + queryset scoping (see API standards)
- [ ] Re-enable list pagination for unbounded resources
- [ ] Attendance matrix filter honesty + frontend route split
- [ ] Remove payroll residue (`paid`, teacher rate/bank) from live models
- [ ] Academic records (exams / results) — future



## License

Private — internal school administration use.