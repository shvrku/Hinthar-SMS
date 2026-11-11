# Hinthar SMS — Backend API Endpoints, Permissions & Engine Functions Reference

**Repository:** `Hinthar-SMS/Hinthar-SMS`  
**Base URL:** `/api/v1/`  
**Interactive Docs (when `DEBUG=True`):** `/api/v1/docs/` (Swagger UI) · `/api/v1/redoc/` · `/api/v1/schema/`  
**Source of Truth Files:**
- Root Router: [`config/urls.py`](../config/urls.py), [`config/views.py`](../config/views.py)
- Roles, Permissions & Auth: [`people/roles.py`](../people/roles.py), [`people/permissions.py`](../people/permissions.py), [`people/authentication.py`](../people/authentication.py), [`people/clerk_backend.py`](../people/clerk_backend.py), [`people/user_guards.py`](../people/user_guards.py)
- Audit & Code Generation: [`people/audit.py`](../people/audit.py), [`people/signals.py`](../people/signals.py), [`people/utils.py`](../people/utils.py)
- App Views & Engines:
  - [`people/views.py`](../people/views.py), [`people/webhooks.py`](../people/webhooks.py)
  - [`timetable/views.py`](../timetable/views.py), [`timetable/utils.py`](../timetable/utils.py), [`timetable/conflicts.py`](../timetable/conflicts.py)
  - [`class_sessions/views.py`](../class_sessions/views.py), [`class_sessions/utils.py`](../class_sessions/utils.py), [`class_sessions/overview_stats.py`](../class_sessions/overview_stats.py), [`class_sessions/datetime_bounds.py`](../class_sessions/datetime_bounds.py)
  - [`communications/views.py`](../communications/views.py)
  - Next-Pass Modules: [`academics/views.py`](../academics/views.py), [`payroll/views.py`](../payroll/views.py)

---

## 1. Backend Request, Auth & Engine Informatics (ASCII)

### 1.1 Clerk JWT Authentication & Role Authorization Pipeline

```text
+-----------------------------------------------------------------------------------+
| 1. INCOMING HTTP REQUEST (/api/v1/*)                                              |
|    Header: Authorization: Bearer <Clerk_RS256_JWT>                                |
+-----------------------------------------+-----------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
| 2. ClerkJWTAuthentication (people/authentication.py)                              |
|    +-- [DEBUG + ENABLE_MOCK_AUTH + "mock_token_*"] -> _authenticate_mock() (<=50) |
|    +-- Fetch JWKS from CLERK_JWKS_URL (cached 3600s in 'clerk_jwks')              |
|        +-- If JWT header 'kid' missing from cache -> Bust cache & refetch once    |
|    +-- Verify RS256 signature, 'iss' (CLERK_JWT_ISSUER), 'aud', 60s leeway        |
|    +-- Extract 'sub' -> clerk_id, email, username                                 |
|    +-- upsert_from_clerk(): Get or create people.User (default role='pending')    |
+-----------------------------------------+-----------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
| 3. DRF PERMISSION GATE (people/permissions.py + people/roles.py)                  |
|    +-- GET /api/v1/me/ -> IsAuthenticated (Allows is_active=False so UI can       |
|                           redirect deactivated accounts to /account-locked)       |
|    +-- All Other Routes -> Requires is_active_account(user) == True               |
|    +-- Role Rank Evaluation (role_rank(user)):                                    |
|        [5] admin    -> IsAdmin (User management, Clerk sync, profile linking)     |
|        [4] staff    -> IsStaffOrAbove (Full CRUD on people, cohorts, schedule)    |
|        [3] terminal -> CanCheckIn / IsTerminalOrAbove (Gate QR & manual check-in) |
|        [2] teacher  -> IsTeacherOwnerOrStaffOrAdmin (Own profile, timetable, sum) |
|        [1] student  -> IsStudentOwnerOrStaffOrAdmin (Own profile, QR token, sum)  |
|        [0] pending  -> Blocked on operational APIs (403 Forbidden)                |
+-----------------------------------------------------------------------------------+
```

### 1.2 Campus Check-In to Lesson Attendance Auto-Propagation Flow

```text
+-----------------------------------------------------------------------------------+
| GATE ARRIVAL COMMIT                                                               |
| POST /api/v1/check-ins/qr/ {"check_in_token"}  OR  /manual/ {"student_id"}        |
+-----------------------------------------+-----------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
| 1. PESSIMISTIC LOCK & GUARD (transaction.atomic)                                  |
|    +-- Student.objects.select_for_update()                                        |
|    +-- Verify student.check_in_token_active == True (else 403 Forbidden)          |
|    +-- Check unique (student, today_local_date) (if exists -> 409 Conflict)       |
|    +-- Insert class_sessions.CheckIn(student, date=today, check_in_type, user)    |
+-----------------------------------------+-----------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
| 2. AUTO-MARK TODAY'S LESSON ROLLS (process_checkin_attendance in utils.py)        |
|    +-- Find today's SessionAttendance & AdHocSessionAttendance for student        |
|        WHERE status == 'absent' (Never overwrites manual staff/teacher marks!)    |
|    +-- Compare checkin.timestamp against session window:                          |
|        +-- timestamp <= start_time + 15 min  --> status = 'present'               |
|        +-- timestamp <= end_time             --> status = 'late'                  |
|        +-- timestamp >  end_time             --> stays 'absent'                   |
|    +-- Set auto_marked_by_checkin = checkin                                       |
+-----------------------------------------+-----------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
| 3. UNDO / REVERT SAFEGUARD (DELETE /api/v1/check-ins/{id}/)                       |
|    +-- revert_checkin_auto_attendance(checkin):                                   |
|        Reverts ONLY attendance rows where auto_marked_by_checkin == checkin       |
|        back to status='absent'. Any row manually edited by staff is preserved.    |
+-----------------------------------------------------------------------------------+
```

---

## 2. Role Hierarchy & Permission Classes (`people/roles.py`, `people/permissions.py`)

### 2.1 Canonical Role Ranks (`ROLE_RANK`)

| Rank | Role String | Helper Check | Operational Scope |
| :---: | :--- | :--- | :--- |
| **5** | `'admin'` | `is_admin(user)` | Full system control + `/users/` administration, Clerk sync/import, and `link_user`/`unlink_user`. |
| **4** | `'staff'` | `is_staff_or_above(user)` | Day-to-day school operations: full CRUD on students, teachers, staff, cohorts, courses, slots, sessions, attendance, check-ins, announcements, and events. |
| **3** | `'terminal'` | `is_terminal_or_above(user)` / `can_check_in(user)` | Kiosk gate operator: allowed to call `/check-ins/lookup/`, `/check-ins/qr/`, and `/check-ins/manual/`. |
| **2** | `'teacher'` | `is_teacher_or_above(user)` | Scoped read access to own `Teacher` profile, own weekly timetable (`/timetable/teacher/{id}/`), and own attendance summary. |
| **1** | `'student'` | `is_at_least(user, 'student')` | Scoped read access to `/me/student/`, `/me/attendance-summary/`, own `Student` record, own QR token, own timetable, and event registration. |
| **0** | `'pending'` | `role_rank == 0` | Newly signed-up Clerk account awaiting admin linking. Can only call `GET /api/v1/me/`. |
| **-1** | Inactive / Anon | `is_active_account(user) == False` | Deactivated user (`is_active=False`) or unauthenticated visitor. |

### 2.2 DRF Permission Classes (`people/permissions.py`)
- **`IsActiveAuthenticated`:** Requires `is_active_account(request.user)`. Rejects `is_active=False` with `403`.
- **`IsStaffOrAbove` (alias `IsStaffOrAdmin`):** Requires `role_rank >= 4` (`admin` or `staff`).
- **`IsAdmin`:** Requires `role_rank >= 5` (`admin`).
- **`CanCheckIn`:** Requires `is_active_account(user) and user.role in {'admin', 'staff', 'terminal'}`.
- **`IsTeacherOwnerOrStaffOrAdmin`:** Allows `staff`/`admin` for any record, or active `teacher` when `obj == user.teacher_profile`.
- **`IsStudentOwnerOrStaffOrAdmin`:** Allows `staff`/`admin` for any record, or active `student` when `obj == user.student_profile`.
- **`IsStaffOrAboveOrReadOnly`:** Allows `GET`/`HEAD`/`OPTIONS` for any active authenticated user; requires `IsStaffOrAbove` for writes.

---

## 3. Complete API Endpoint Catalog (`/api/v1/*`)

### 3.1 Health & OpenAPI Schema (`config/urls.py`)

| Method | Path | View | Permission | Description |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/health/` | `config.views.health` | Public (`AllowAny`) | Health check returning `{"status": "ok"}` (`200`) |
| `GET` | `/api/v1/schema/` | `SpectacularAPIView` | `DEBUG=True` | OpenAPI 3.0 YAML/JSON schema |
| `GET` | `/api/v1/docs/` | `SpectacularSwaggerView` | `DEBUG=True` | Interactive Swagger UI |
| `GET` | `/api/v1/redoc/` | `SpectacularRedocView` | `DEBUG=True` | Interactive ReDoc UI |

---

### 3.2 Identity, People & User Administration (`people/urls.py`)

#### Self-Service & Clerk Webhooks
| Method | Path | View | Permission | Query Params / Payload | Response & Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/me/` | `MeView` | `IsAuthenticated` | None | Returns `UserSerializer` (`id`, `username`, `email`, `role`, `clerk_id`, `teacher_profile_id`, `student_profile_id`, `staff_profile_id`, `is_active`). **Allowed when `is_active=False`**. |
| `GET` | `/api/v1/me/student/` | `MeStudentView` | `IsActiveAuthenticated` (`student`) | None | Returns linked `StudentSerializer` including `check_in_token` (`200`, `403`, `404`). |
| `GET` | `/api/v1/me/attendance-summary/` | `MeAttendanceSummaryView` | `IsActiveAuthenticated` (`student`) | `range` (`week\|month\|all`, required) | Returns student's own `campus` and `lesson` attendance analytics (`200`, `400`, `403`, `404`). |
| `POST` | `/api/v1/webhooks/clerk/` | `ClerkWebhookView` | Svix Signature (`CLERK_WEBHOOK_SECRET`) | Clerk webhook event (`user.created`, `user.updated`, `user.deleted`) | Syncs Clerk user creation/updates or sets `is_active=False` on deletion (`200`, `400`, `401`). |

#### Students (`/api/v1/students/` — `StudentViewSet`)
*Paginated (`50`/page default, max `200`). `check_in_token` is omitted on `list` and included only on single-record `retrieve` or token actions.*

| Method | Path | Action | Permission | Query Params / Payload | Response & Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/students/` | `list` | `IsStaffOrAbove` | `q`, `school_code`, `class_id`, `linked` (`true\|false`), `page`, `page_size` | `Paginated<StudentSerializer>` (`check_in_token` omitted) |
| `POST` | `/api/v1/students/` | `create` | `IsStaffOrAbove` | `name`, `dob`, `contact`, `school_code`, `exam_candidate_number` | `201 Created` (`unique_code` & `check_in_token` auto-generated) |
| `GET` | `/api/v1/students/{id}/` | `retrieve` | `IsStudentOwnerOrStaffOrAdmin` | None | `StudentSerializer` (with `check_in_token`, `class_ids`, `class_labels`) |
| `PUT/PATCH` | `/api/v1/students/{id}/` | `update` / `partial_update` | `IsStaffOrAbove` | Partial or full `StudentSerializer` fields | Updated `StudentSerializer` (`200`) |
| `DELETE` | `/api/v1/students/{id}/` | `destroy` | `IsStaffOrAbove` | None | `204 No Content` |
| `POST` | `/api/v1/students/bulk_create/` | `bulk_create` | `IsStaffOrAbove` | `{"items": [...]}` | `{"created_count": int, "items": [...]}` (`201`) |
| `DELETE` | `/api/v1/students/bulk_delete/` | `bulk_delete` | `IsStaffOrAbove` | `{"ids": [int, ...]}` | `{"deleted_count": int, "deleted_ids": [...]}` (`200`) |
| `GET` | `/api/v1/students/{id}/check_in_token/` | `check_in_token` | `IsStudentOwnerOrStaffOrAdmin` | None | `{"check_in_token": "..."}` (`200`) |
| `POST` | `/api/v1/students/{id}/regenerate_check_in_token/` | `regenerate_check_in_token` | `IsStaffOrAbove` | None | Rotates secret token & sets active: `{"check_in_token": "...", "check_in_token_active": true}` (`200`) |
| `POST` | `/api/v1/students/{id}/activate_check_in_token/` | `activate_check_in_token` | `IsStaffOrAbove` | None | `{"check_in_token_active": true}` (`200`) |
| `POST` | `/api/v1/students/{id}/deactivate_check_in_token/` | `deactivate_check_in_token` | `IsStaffOrAbove` | None | `{"check_in_token_active": false}` (`200`) |
| `GET` | `/api/v1/students/{id}/attendance-summary/` | `attendance_summary` | `IsStudentOwnerOrStaffOrAdmin` | `range` (`week\|month\|all`) | Campus check-in + lesson roll breakdown (`200`) |
| `POST` | `/api/v1/students/{id}/link_user/` | `link_user` | `IsAdmin` | `{"user_id": int}` | Links `User` ↔ `Student` and sets `user.role = 'student'` (`200`) |
| `POST` | `/api/v1/students/{id}/unlink_user/` | `unlink_user` | `IsAdmin` | None | Unlinks `User` and resets `user.role = 'pending'` (`200`) |

#### Teachers (`/api/v1/teachers/` — `TeacherViewSet`)
*Paginated (`50`/page default, max `200`).*

| Method | Path | Action | Permission | Query Params / Payload | Response & Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/teachers/` | `list` | `IsStaffOrAbove` | `q`, `school_code`, `employment_type`, `linked` (`true\|false`), `page`, `page_size` | `Paginated<TeacherSerializer>` |
| `POST` | `/api/v1/teachers/` | `create` | `IsStaffOrAbove` | `name`, `employment_type` (`full_time\|tutor`), `contact`, `join_date`, `school_code` | `201 Created` (`unique_code` auto-generated) |
| `GET` | `/api/v1/teachers/{id}/` | `retrieve` | `IsTeacherOwnerOrStaffOrAdmin` | None | `TeacherSerializer` (`200`) |
| `PUT/PATCH` | `/api/v1/teachers/{id}/` | `update` / `partial_update` | `IsStaffOrAbove` | `TeacherSerializer` fields | Updated `TeacherSerializer` (`200`) |
| `DELETE` | `/api/v1/teachers/{id}/` | `destroy` | `IsStaffOrAbove` | None | `204 No Content` |
| `POST` | `/api/v1/teachers/bulk_create/` | `bulk_create` | `IsStaffOrAbove` | `{"items": [...]}` | `{"created_count": int, "items": [...]}` (`201`) |
| `DELETE` | `/api/v1/teachers/bulk_delete/` | `bulk_delete` | `IsStaffOrAbove` | `{"ids": [int, ...]}` | `{"deleted_count": int, "deleted_ids": [...]}` (`200`) |
| `GET` | `/api/v1/teachers/{id}/attendance-summary/` | `attendance_summary` | `IsTeacherOwnerOrStaffOrAdmin` | `range` (`week\|month\|all`) | Accountability & personal teaching coverage analytics (`200`) |
| `POST` | `/api/v1/teachers/{id}/link_user/` | `link_user` | `IsAdmin` | `{"user_id": int}` | Links `User` ↔ `Teacher` and sets `user.role = 'teacher'` (`200`) |
| `POST` | `/api/v1/teachers/{id}/unlink_user/` | `unlink_user` | `IsAdmin` | None | Unlinks `User` and resets `user.role = 'pending'` (`200`) |

#### Subjects (`/api/v1/subjects/` — `SubjectViewSet`) & Staff (`/api/v1/staff/` — `StaffViewSet`)
- **`/api/v1/subjects/` (`IsStaffOrAbove`, unpaginated array):** `GET`, `POST`, `GET /{id}/`, `PUT/PATCH /{id}/`, `DELETE /{id}/` (cascades related `Session`, `AdHocSession`, `TimetableSlot`), `POST /bulk_create/`, `DELETE /bulk_delete/`.
- **`/api/v1/staff/` (`IsStaffOrAbove`, paginated):** `GET`, `POST`, `GET /{id}/`, `PUT/PATCH /{id}/`, `DELETE /{id}/`, `POST /bulk_create/`, `DELETE /bulk_delete/`.

#### User Administration & Clerk Sync (`/api/v1/users/` — `UserViewSet`)
*Strictly `IsAdmin` (Role Rank 5). Direct `POST /api/v1/users/` is disabled (`405`).*

| Method | Path | Action | Query Params / Payload | Response & Notes |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/users/` | `list` | `q`, `role`, `is_active`, `linked`, `linked_target` (`student\|teacher\|staff\|any`), `linkable`, `linkable_target` (`student\|teacher`), `page`, `page_size` | `Paginated<AdminUserSerializer>` with `can_delete`, `delete_blocked_reason`, `can_deactivate`, `deactivate_blocked_reason` |
| `GET` | `/api/v1/users/{id}/` | `retrieve` | None | `AdminUserSerializer` (`200`) |
| `PUT/PATCH` | `/api/v1/users/{id}/` | `update` / `partial_update` | `{"role": "...", "is_active": bool}` | Guarded by `deactivate_blockers` (cannot deactivate self or last admin) |
| `DELETE` | `/api/v1/users/{id}/` | `destroy` | None | Guarded by `delete_blockers` (cannot delete self, last admin, or linked user) |
| `GET` | `/api/v1/users/clerk_sync/` | `clerk_sync` | None | Compares live Clerk directory against Django DB: `{clerk_unlinked, django_unlinked, clerk_dashboard_users_url}` |
| `POST` | `/api/v1/users/clerk_import/` | `clerk_import` | `{"clerk_ids": ["user_..."]}` (optional) | Batch imports unlinked Clerk users into Django as `role='pending'` (`201`) |
| `POST` | `/api/v1/users/{id}/clerk_link/` | `clerk_link` | `{"clerk_id": "user_..."}` | Links an orphaned Django user row to a Clerk `user_...` ID (`200`) |

#### Audit Logs (`/api/v1/audit-logs/` — `AuditLogViewSet`)
- **`GET /api/v1/audit-logs/` (`IsStaffOrAbove`, paginated):** Filters by `category` (`student`, `teacher`, `staff`, `class`, `session`, `check_in`, `user`, `other`), `page`, `page_size`.
- **`GET /api/v1/audit-logs/{id}/` (`IsStaffOrAbove`):** Single audit entry detail.

---

### 3.3 Cohorts, Courses & Timetable (`timetable/urls.py`)

| Method | Path | View / Action | Permission | Query Params / Payload | Response & Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/classes/` *(alias `/cohorts/`)* | `ClassViewSet.list` | `IsStaffOrAbove` | None | Unpaginated list of all `Class` cohorts (`200`) |
| `POST` | `/api/v1/classes/` | `ClassViewSet.create` | `IsStaffOrAbove` | `education_level`, `cohort_identifier`, `cohort_sub_category` | `201 Created` |
| `GET/PUT/PATCH/DELETE` | `/api/v1/classes/{id}/` | `ClassViewSet` | `IsStaffOrAbove` | Standard fields | `DELETE` cascades associated `Session` & `TimetableSlot` rows |
| `POST / DELETE` | `/api/v1/classes/bulk_create/` & `/bulk_delete/` | `ClassViewSet` | `IsStaffOrAbove` | `{"items": [...]}` / `{"ids": [...]}` | Batch create / delete cohorts |
| `GET` | `/api/v1/classes/{id}/attendance-summary/` | `attendance_summary` | `IsStaffOrAbove` | `range` (`week\|month\|all`), `subject_id` (optional) | Cohort campus check-in & lesson attendance analytics (`200`) |
| `GET/POST` | `/api/v1/courses/` | `CourseViewSet` | `IsStaffOrAbove` | Query: `class_id`/`cohort_id`, `subject_id` · Body: `class_obj_id`, `subject_id`, `default_teacher_id` | Manage cohort subject offerings (`Course`) |
| `GET/PUT/PATCH/DELETE` | `/api/v1/courses/{id}/` | `CourseViewSet` | `IsStaffOrAbove` | Standard fields | Includes `/bulk_create/`, `/bulk_delete/`, and `/{id}/attendance-summary/` |
| `GET/POST` | `/api/v1/class-students/` | `ClassStudentViewSet` | `IsStaffOrAbove` | Query: `class_id`, `student_id` · Body: `class_obj_id`, `student_id` | Enrolls student in primary cohort; runs `detect_student_conflicts` and returns conflict warnings |
| `DELETE` | `/api/v1/class-students/{id}/` & `/bulk_delete/` | `ClassStudentViewSet` | `IsStaffOrAbove` | `{"ids": [...]}` | Unenrolls student(s) from primary cohort |
| `GET/POST/DELETE` | `/api/v1/student-subject-enrollments/` *(alias `/course-enrollments/`)* | `StudentSubjectEnrollmentViewSet` | `IsStaffOrAbove` | Query: `class_id`, `student_id`, `subject_id`, `course_id`, `status` (`enrolled\|dropped`) | Cross-cohort elective enrollment or drop override; auto-syncs future `SessionAttendance` rows |
| `GET` | `/api/v1/timetable-slots/` | `TimetableSlotViewSet.list` | `IsStaffOrAbove` | `class_id` / `cohort_id` / `course_id` (**required**), `subject_id` | Weekly slots for the cohort (`400` if `class_id` omitted) |
| `POST` | `/api/v1/timetable-slots/` | `TimetableSlotViewSet.create` | `IsStaffOrAbove` | `class_obj_id`, `subject_id`, `teacher_id`, `day_of_week` (`0`–`6`), `start_time`, `end_time`, `room` | Validates teacher/room overlaps; **auto-generates dated sessions through month-end** (`201`) |
| `PUT/PATCH/DELETE` | `/api/v1/timetable-slots/{id}/` & `/bulk_delete/` | `TimetableSlotViewSet` | `IsStaffOrAbove` | Slot fields | `PUT/PATCH` re-validates overlaps & generates sessions; `DELETE` cascades `Session` rows |
| `GET` | `/api/v1/timetable/teacher/{teacher_id}/` | `TeacherTimetableView` | `IsActiveAuthenticated` (Staff+ or owner teacher) | None | Plain array of weekly `TimetableSlot` rows for the teacher |
| `GET` | `/api/v1/timetable/class/{class_id}/` | `ClassTimetableView` | `IsActiveAuthenticated` (Staff+ or enrolled student) | None | Plain array of weekly `TimetableSlot` rows for the cohort |
| `GET` | `/api/v1/timetable/student/{student_id}/` *(alias `/students/{id}/timetable-conflicts/`)* | `StudentTimetableAndConflictsView` | `IsActiveAuthenticated` (Staff+ or owner student) | `candidate_course_id`, `candidate_class_id`, `candidate_subject_id` | Returns effective weekly timetable slots + non-blocking overlap conflict report |

---

### 3.4 Sessions, Lesson Attendance, Check-In & Overview (`class_sessions/urls.py`)

| Method | Path | View / Action | Permission | Query Params / Payload | Response & Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/stats/` | `StatsView` | `IsStaffOrAbove` | None | Cached (`300s`) dashboard KPIs, 30-day trends, 12-month enrollment series, and 8 recent audit events |
| `POST` | `/api/v1/sessions/generate/{class_id}/` | `GenerateClassSessionsView` | `IsStaffOrAbove` | `{"start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD"}` | Batch-generates dated `Session` + initial `'absent'` `SessionAttendance` rows for the cohort (`200`) |
| `GET/POST` | `/api/v1/sessions/` | `SessionViewSet` | `IsStaffOrAbove` | Query: `class_id`, `teacher_id`, `subject_id`, `timetable_slot_id`, `date_from`, `date_to`, `month`, `year`, `status`, `q`, `page`, `page_size` | Paginated dated sessions (`start_time`/`end_time` in ISO-8601) |
| `GET/PUT/PATCH/DELETE` | `/api/v1/sessions/{id}/` | `SessionViewSet` | `IsStaffOrAbove` | `teacher_id`, `actual_teacher_id` (substitute), `status`, `start_time`, `end_time` | Manage single session occurrence; includes `PATCH /{id}/status/`, `/bulk_create/`, `/bulk_delete/` |
| `GET/POST/PUT/PATCH/DELETE` | `/api/v1/session-attendances/` | `SessionAttendanceViewSet` | `IsStaffOrAbove` | Query: `session_id`, `student_id`, `status`, `teacher_id`, `class_id`, `date_from`, `date_to` | Per-student lesson attendance CRUD |
| `POST` | `/api/v1/session-attendances/bulk_upsert/` | `bulk_upsert` | `IsStaffOrAbove` | `{"records": [{"session_id": int, "student_id": int, "status": "present\|late\|absent\|excused"}]}` | Atomic batch create/update of lesson roll marks (`200`) |
| `GET` | `/api/v1/attendance/matrix/` | `AttendanceMatrixView` | `IsStaffOrAbove` | `class_id` (**required**), `subject_id`, `teacher_id`, `date_from`, `date_to`, `month`, `year` | Returns `{class, sessions (<=400), students, attendance}` where unmarked cells are `null` (`200`, `400` if no `class_id`) |
| `GET/POST/PUT/PATCH/DELETE` | `/api/v1/adhoc-sessions/` | `AdHocSessionViewSet` | `IsStaffOrAbove` | Query: `teacher_id`, `subject_id`, `date`, `date_from`, `date_to`, `status`, `q` | One-off tutoring sessions + `PATCH /{id}/status/`, `/bulk_create/`, `/bulk_delete/` |
| `GET/POST/PUT/PATCH/DELETE` | `/api/v1/adhoc-session-attendances/` | `AdHocSessionAttendanceViewSet` | `IsStaffOrAbove` | Query: `ad_hoc_session_id`, `student_id`, `status` | Includes `POST /adhoc-session-attendances/bulk_upsert/` |
| `GET` | `/api/v1/adhoc-attendance/matrix/` | `AdHocAttendanceMatrixView` | `IsStaffOrAbove` | `subject_id`, `teacher_id`, `date_from`, `date_to`, `month`, `year` | Cross-session matrix for ad-hoc tutoring sessions (`200`) |
| `POST` | `/api/v1/check-ins/lookup/` | `CheckInLookupView` | `CanCheckIn` (`120/min` throttle) | `{"check_in_token": "..."}` OR `{"unique_code": "..."}` | Pre-commit terminal lookup returning `CheckInLookup` without writing a check-in (`200`, `403` if token inactive, `404`) |
| `POST` | `/api/v1/check-ins/qr/` | `QRCheckInView` | `CanCheckIn` (`120/min` throttle) | `{"check_in_token": "..."}` | Commits daily QR check-in + auto-marks today's lesson roll (`201`, `403` if inactive, `409` if already checked in) |
| `POST` | `/api/v1/check-ins/manual/` | `ManualCheckInView` | `CanCheckIn` (`120/min` throttle) | `{"student_id": int}` | Commits daily manual check-in + auto-marks today's lesson roll (`201`, `403`, `404`, `409`) |
| `GET` | `/api/v1/check-ins/` | `CheckInViewSet.list` | `IsStaffOrAbove` | `student_id`, `date`, `date_from`, `date_to`, `check_in_type`, `q`, `page`, `page_size` | Paginated scan log (`CheckInListSerializer`) |
| `DELETE` | `/api/v1/check-ins/{id}/` & `/bulk_delete/` | `CheckInViewSet` | `IsStaffOrAbove` | `{"ids": [...]}` on bulk | Deletes check-in(s) and runs `revert_checkin_auto_attendance` |
| `GET` | `/api/v1/check-ins/overview/` | `CheckInViewSet.overview` | `IsStaffOrAbove` | `date`, `class_id` (`"all"` or `<int>`), `status` (`missing\|arrived`), `search`, `page`, `page_size` | Daily Roll aggregate: per-class summary counts or roster split by arrived vs missing |

---

### 3.5 School Communications (`communications/urls.py`)

| Method | Path | View / Action | Permission | Query Params / Payload | Response & Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/tags/` & `/tags/{slug}/` | `TagViewSet` | `IsActiveAuthenticated` | `scope` (`announcement\|event`) | List or retrieve topic tags |
| `GET` | `/api/v1/announcements/` | `AnnouncementViewSet.list` | `IsStaffOrAboveOrReadOnly` | `tag`, `q`, `page`, `page_size` | Published feed for members; Staff+ also sees archived/drafts |
| `POST` | `/api/v1/announcements/` | `AnnouncementViewSet.create` | `IsStaffOrAbove` | `title`, `body`, `status`, `is_featured`, `is_pinned`, `tag_names` | Creates announcement (`author = request.user`) (`201`) |
| `GET/PUT/PATCH/DELETE` | `/api/v1/announcements/{slug}/` | `AnnouncementViewSet` | `IsStaffOrAboveOrReadOnly` | Lookup by `slug` | Read or mutate single announcement |
| `GET` | `/api/v1/events/` & `/events/{slug}/` | `EventViewSet` | `AllowAny` (Public sees `external`; signed-in sees `internal` + `external`) | `tag`, `q`, `when` (`upcoming\|past`) | Event timeline & detail |
| `POST/PUT/PATCH/DELETE` | `/api/v1/events/` & `/events/{slug}/` | `EventViewSet` | `IsStaffOrAbove` | `title`, `summary`, `body`, `audience`, `registration_mode`, `status`, `starts_at`, `ends_at`, `location`, `capacity`, `tag_names`, etc. | Staff event authoring & lifecycle management |
| `POST` | `/api/v1/events/{slug}/register/` | `register` | `IsActiveAuthenticated` | None | Registers user: `'confirmed'`, `'waitlisted'` (if full), or `'pending'` (if `approval_required`) |
| `POST` | `/api/v1/events/{slug}/cancel-registration/` | `cancel_registration` | `IsActiveAuthenticated` | None | Sets caller's registration status to `'cancelled'` |
| `GET` | `/api/v1/events/my-registrations/` | `my_registrations` | `IsActiveAuthenticated` | None | Caller's active event registrations with nested event objects |
| `GET` | `/api/v1/events/{slug}/registrations/` | `registrations` | `IsStaffOrAbove` | None | Full participant roster for staff event management |
| `POST` | `/api/v1/events/{slug}/registrations/{registration_id}/review/` | `review_registration` | `IsStaffOrAbove` | `{"action": "approve\|reject\|promote", "staff_note": "..."}` | Staff approval/rejection/waitlist promotion workflow |

---

### 3.6 Upcoming Next-Pass Endpoints (`academics` & `payroll`)

> [!NOTE]
> These endpoints exist in the backend (`academics/urls.py` and `payroll/urls.py`) and are tested at the API layer, awaiting Frontend UI integration in the upcoming **Exam Tracking** and **Teacher/Student Payroll** pass.

- **Exam Tracking (`academics/urls.py` — `IsStaffOrAbove`, `CanReadReportCards`):**
  - `GET / POST /api/v1/academic-years/` & `GET /api/v1/terms/?academic_year_id=`
  - `GET / POST / PUT / PATCH /api/v1/subject-offerings/` (weights must sum to `100.00`)
  - `GET / POST / PUT / PATCH /api/v1/assessments/` (`exam`, `quiz`, `assignment`)
  - `GET / POST / PUT / PATCH /api/v1/assessment-results/`
  - `GET / POST /api/v1/report-cards/` & `POST /api/v1/report-cards/{id}/publish/`
- **Payroll & Student Fees (`payroll/urls.py` — `IsFinanceAdministrator`):**
  - `GET / POST / PUT / PATCH / DELETE /api/v1/student-fees/`
  - `GET / POST / PUT / PATCH / DELETE /api/v1/fee-payments/`
  - `GET / POST / PUT / PATCH / DELETE /api/v1/staff-salaries/`

---

## 4. Backend Engine & Utility Functions Reference

| Module & Function | Signature & Parameters | Exact Responsibility & Algorithm |
| :--- | :--- | :--- |
| **[`people.utils.generate_unique_code`](../people/utils.py)** | `generate_unique_code(instance)` | Generates concurrency-safe sequential IDs inside `transaction.atomic()` with `select_for_update()`:<br>• Student: `{SchoolCode}{Year}-{Seq:05d}` (`HIS24-00143`)<br>• Teacher: `{SchoolCode}T{Year}-{Seq:05d}` (`HIST22-00007`)<br>• Staff: `{SchoolCode}S{Year}-{Seq:05d}` (`HISS24-00001`) |
| **[`people.audit.log_event`](../people/audit.py)** | `log_event(*, category, action, summary, user=None, model_name='', record_id='', field_name=None, old_value=None, new_value=None)` | Writes an `AuditLog` record attributing the action to `user` or the active `_actor` ContextVar (`AuditActorMixin`). Suppressed when inside `with mute_audit():` (e.g. during batch session generation). |
| **[`people.user_guards.delete_blockers`](../people/user_guards.py)** | `delete_blockers(user, actor, other_admin_count)` | Returns human-readable blocker reasons if an admin attempts to delete their own account, the last remaining admin, or a user still linked to a `Student`, `Teacher`, or `Staff` profile. |
| **[`people.user_guards.deactivate_blockers`](../people/user_guards.py)** | `deactivate_blockers(user, actor, other_active_admin_count)` | Prevents an admin from deactivating their own account or deactivating the last active admin. |
| **[`timetable.utils.generate_sessions_for_slots`](../timetable/utils.py)** | `generate_sessions_for_slots(slots, start_date=None, end_date=None)` | Iterates each day in `[start_date, end_date]` (default: today through month-end) under `mute_audit()`. Matches `weekday() == slot.day_of_week`, calls `Session.objects.get_or_create()`, and bulk-creates initial `'absent'` `SessionAttendance` rows for `(primary_cohort_students - dropped_students) \| cross_enrolled_students`. |
| **[`timetable.conflicts.detect_student_conflicts`](../timetable/conflicts.py)** | `detect_student_conflicts(student_id, candidate_pairs=None)` | Computes a student's active `(class_obj_id, subject_id)` pairs (applying `StudentSubjectEnrollment` enrolled/dropped overrides), fetches all `TimetableSlot` rows, and detects pairwise day/time overlaps (`start_a < end_b and end_a > start_b`). |
| **[`class_sessions.utils.process_checkin_attendance`](../class_sessions/utils.py)** | `process_checkin_attendance(checkin)` | Triggered on QR/manual campus check-in. Finds today's `SessionAttendance` and `AdHocSessionAttendance` rows for the student where `status == 'absent'`. Marks `'present'` if `timestamp <= start_time + 15m`, or `'late'` if `timestamp <= end_time`, stamping `auto_marked_by_checkin = checkin`. |
| **[`class_sessions.utils.revert_checkin_auto_attendance`](../class_sessions/utils.py)** | `revert_checkin_auto_attendance(checkin)` | Triggered when a `CheckIn` is deleted. Reverts only attendance rows where `auto_marked_by_checkin_id == checkin.id` back to `'absent'`, preserving any manual teacher/staff overrides. |
| **[`class_sessions.overview_stats.build_overview_stats`](../class_sessions/overview_stats.py)** | `build_overview_stats()` | Cached for `300s` under `stats_overview_v2`. Runs a single 11-subselect `COUNT(*)` SQL query, computes 30-day vs prior-30-day deltas, builds a 12-month cumulative `TruncMonth` student enrollment series, and returns the 8 latest non-noisy `AuditLog` items. |
| **[`class_sessions.datetime_bounds`](../class_sessions/datetime_bounds.py)** | `parse_date_bounds(date_from, date_to)` | Converts `YYYY-MM-DD` date strings into timezone-aware start-of-day (`00:00:00`) and end-of-day (`23:59:59.999999`) bounds for accurate `Session.start_time` filtering. |
| **[`academics.models.build_report_snapshot`](../academics/models.py)** | `build_report_snapshot(student, class_obj, term)` | *(Next-Pass Engine)* Aggregates weighted marks across `exam`, `quiz`, and `assignment` categories (`ROUND_HALF_UP`), assigns letter grades (`A >= 80`, `B >= 70`, `C >= 60`, `D >= 50`, `F < 50`), and returns an immutable JSON snapshot for `ReportCard`. |
