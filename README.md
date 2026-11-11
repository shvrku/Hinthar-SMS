# Hinthar SMS — School Management System Backend

API-first Django REST Framework backend for the Hinthar Education Center & School Management System. Powers identity & role management, student/teacher/staff directories, cohorts & courses, 7-day flexible timetabling, batch session generation, lesson attendance matrices, campus QR check-in with automatic lesson roll propagation, and school communications (announcements & events).

---

## Documentation Suite

| Document | Contents |
| :--- | :--- |
| **[`docs/BACKEND_DATA_MODELS_AND_SCHEMA.md`](docs/BACKEND_DATA_MODELS_AND_SCHEMA.md)** | ASCII Entity-Relationship diagrams, complete model-by-model field dictionaries, constraints (`UniqueConstraint`, `CheckConstraint`), indexes, and lifecycle hooks across `people`, `timetable`, `class_sessions`, `communications`, plus next-pass `academics` and `payroll`. |
| **[`docs/BACKEND_ENDPOINTS_AND_FUNCTIONS.md`](docs/BACKEND_ENDPOINTS_AND_FUNCTIONS.md)** | ASCII request/auth/check-in pipelines, role rank hierarchy (`ROLE_RANK`), DRF permission classes, complete `/api/v1/*` endpoint catalog, and internal engine functions (`generate_sessions_for_slots`, `process_checkin_attendance`, `detect_student_conflicts`, `build_overview_stats`, `log_event`). |
| **[`payroll/README.md`](payroll/README.md)** | Implementation and rules reference for the upcoming Payroll & Student Fees module pass. |

Interactive OpenAPI documentation (when `DEBUG=True`):
- **Swagger UI:** `/api/v1/docs/`
- **ReDoc:** `/api/v1/redoc/`
- **Raw OpenAPI 3 Schema:** `/api/v1/schema/`

---

## Live API Surface (`/api/v1/`)

| Domain | Base Endpoints | Key Capabilities |
| :--- | :--- | :--- |
| **Self-Service & Auth** | `GET /me/`, `GET /me/student/`, `GET /me/attendance-summary/`, `POST /webhooks/clerk/` | Clerk RS256 JWT auth, JIT user provisioning, role dispatcher support (`is_active=False` allowed on `/me/`), student self-service QR & analytics. |
| **User Administration** | `/users/`, `/users/clerk_sync/`, `/users/clerk_import/`, `/users/{id}/clerk_link/` | Admin-only account management, guarded delete/deactivate checks, live Clerk directory diff & import. |
| **Directory & Catalog** | `/students/`, `/teachers/`, `/staff/`, `/subjects/` | Paginated lists (`q` search, filters), `bulk_create`/`bulk_delete`, QR token lifecycle (`regenerate`/`activate`/`deactivate`), Clerk `link_user`/`unlink_user`, attendance summaries. |
| **Cohorts & Timetable** | `/classes/` (`/cohorts/`), `/courses/`, `/class-students/`, `/student-subject-enrollments/`, `/timetable-slots/`, `/timetable/{teacher\|class\|student}/{id}/` | Single-primary-cohort enforcement, cross-cohort elective overrides, 7-day (`Mon`–`Sun`) flexible weekly slots, teacher/room overlap validation, student conflict detection. |
| **Sessions & Attendance** | `/sessions/`, `/sessions/generate/{class_id}/`, `/session-attendances/`, `/attendance/matrix/`, `/adhoc-sessions/`, `/adhoc-session-attendances/`, `/adhoc-attendance/matrix/` | Batch session generation, substitute cover (`actual_teacher`), atomic `bulk_upsert` roll marking, scoped attendance matrices (`null` = unmarked). |
| **Campus Check-In** | `/check-ins/`, `/check-ins/lookup/`, `/check-ins/qr/`, `/check-ins/manual/`, `/check-ins/overview/` | `120/min` throttled QR & manual gate check-in, 15-minute grace period auto-propagation to today's lesson roll, safe undo/revert (`revert_checkin_auto_attendance`). |
| **Overview & Audit** | `GET /stats/`, `GET /audit-logs/` | Multi-subselect KPI counts, 30-day delta trends, 12-month cumulative enrollment series, and categorized audit trail. |
| **Communications** | `/announcements/`, `/events/`, `/tags/` | Markdown announcements feed, internal/external events, capacity & waitlist registration (`instant_waitlist` / `approval_required`), staff registration review. |

---

## Project Pass Status

### Completed in This Pass
- [x] **Authentication, Role Rank Hierarchy & Guards** (`admin` > `staff` > `terminal` > `teacher` > `student` > `pending`, deactivated user gates, Clerk webhook & directory sync)
- [x] **People Directory & Account Matching** (Students, Teachers, Staff, Subjects, concurrency-safe `unique_code` generation, Admin Clerk ↔ Profile linking)
- [x] **Cohorts, Courses & Cross-Cohort Enrollments** (`Class`, `Course`, `ClassStudent` single-primary-cohort constraint, `StudentSubjectEnrollment` elective/drop overrides & conflict detection)
- [x] **7-Day Flexible Timetable & Batch Session Engine** (`TimetableSlot` collision checks, `generate_sessions_for_slots`, `actual_teacher` substitute tracking)
- [x] **Lesson Attendance & Scoped Matrices** (`SessionAttendance` & `AdHocSessionAttendance` `bulk_upsert`, `/attendance/matrix/` & `/adhoc-attendance/matrix/` with `null` unmarked semantics)
- [x] **Campus Check-In & Lesson Auto-Propagation** (QR & manual terminal check-in, `check_in_token` rotate/activate/deactivate, daily overview aggregate, automatic lesson roll marking & safe undo revert)
- [x] **Overview Analytics & Audit Logging** (`GET /stats/` cached 30-day trends & 12-month series, `AuditLog` categories & summaries)
- [x] **School Communications** (Announcements markdown feed, Events timeline, capacity/waitlist registration & staff review workflow)

### Remaining for Next Pass
- [ ] **Pay-Roll for Teachers & Student Fee Payments** (Backend models & CRUD scaffolded in `payroll/`; full product workflow & frontend integration scheduled for next pass)
- [ ] **Exam Tracking & Academic Report Cards** (Backend models & weighted snapshot calculator scaffolded in `academics/`; full assessment entry, grading & report card workflow scheduled for next pass)

---

## Tech Stack & Local Setup

| Layer | Technology |
| :--- | :--- |
| **Framework** | Django 5 + Django REST Framework |
| **Database** | PostgreSQL |
| **Authentication** | Clerk (RS256 OIDC JWT + Svix Webhooks) |
| **OpenAPI Schema** | `drf-spectacular` (OpenAPI 3.0) |

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Optional static OpenAPI schema export:
```bash
python manage.py spectacular --file docs/openapi-schema.yml
```

---

## License

Private — internal school administration use.
