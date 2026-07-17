# Hinthar SMS — School Management System

An API-first school management system for class organization, timetabling, session and attendance tracking, and teacher payroll.

## API Endpoints

All endpoints are versioned under `/api/v1/`. Full interactive docs at `/api/v1/docs/` (Swagger UI).

| Endpoint | Description |
|---|---|
| `GET /api/v1/me` | Current user profile |
| `/api/v1/teachers/` | Teacher CRUD |
| `/api/v1/students/` | Student CRUD |
| `/api/v1/staff/` | Staff CRUD |
| `/api/v1/classes/` | Class & enrollment management |
| `/api/v1/subjects/` | Subject management |
| `/api/v1/timetable-slots/` | Recurring timetable definitions |
| `/api/v1/timetable-students/` | Per-slot student assignments |
| `/api/v1/sessions/` | Session generation, status & attendance |
| `/api/v1/session-attendances/` | Per-student attendance records |
| `/api/v1/check-ins/` | Daily check-in records |
| `/api/v1/payslips/` | Payroll preview, confirmation & history |
| `/api/v1/adjustments/` | Payroll corrections |
| `/api/v1/stats/` | System-wide record counts |

## What It Does

- **People Management** — Manage teachers, students, staff, and subjects.
- **Class Structure** — Organize students into classes by education level and cohort.
- **Timetabling** — Define recurring weekly schedules with overlap validation. Support for stream splits when clashes occur.
- **Sessions & Attendance** — Batch-generate dated sessions from timetable templates. Teachers record session status and student attendance.
- **Teacher Payroll** — Preview-then-confirm workflow with frozen payslip snapshots. Corrections handled through a dedicated adjustments system.
- **Authentication & Permissions** — Clerk-based authentication with role-based access control (admin, teacher, staff, terminal).
- **Audit Trail** — Automatic logging of payslip and session changes for accountability.

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Django + Django REST Framework |
| Database | PostgreSQL |
| Auth | Clerk (OIDC/JWT) |
| API Docs | drf-spectacular (OpenAPI 3) |

## Roadmap

- [ ] **Payroll Management** — Payroll periods, bulk payslip generation, payment tracking, and reporting.
- [ ] **Timetable & Session Logic** — Polish session generation edge cases, handle cancellations and rescheduling.
- [ ] **Academic Records** — Exams, results, and report cards.

## License

Private — intended for internal school administration use.
