# Hinthar School Management System (SMS) — Historical Architecture, Domain Logic & API Specification

**Document Version:** 2.0 (Up-to-Date Technical Specification & System History)  
**Scope:** Complete Backend System Architecture, Database Models, Business Logic Safeguards, Authentication/Authorization, Serialization Standards, and Unified API Endpoint Documentation.

---

## 📜 1. Historical Evolution & Key Technical Decisions

The Hinthar School Management System (SMS) backend was designed to manage institutional operations including user account management, academic structure, recurring timetables, dated class session tracking, daily QR/manual check-ins, audit logging, and teacher payroll.

Over the system's development iterations, key technical refinements and architectural standardizations were established to resolve early contract mismatches between backend services (Django REST Framework) and client applications (Next.js frontend):

### Key Historical Bugs Resolved & Structural Upgrades

1. **Deterministic Pagination Ordering (Preventing Tuple Drift)**:
   * **Issue**: Global `PageNumberPagination` (size = 50) caused duplicate records to appear across consecutive page reads (e.g. Page 1 and Page 2).
   * **Root Cause**: SQL `LIMIT/OFFSET` queries executed without explicit `ORDER BY` clauses produce non-deterministic row ordering in PostgreSQL.
   * **Solution**: Explicit deterministic ordering (`ordering = ['id']` or `['-id']`) was enforced across all ModelViewSets.

2. **Dual Representation of Relational Fields (Flat IDs + Pre-fetched Objects)**:
   * **Issue**: Relational fields declared with `write_only=True` omitted primary key IDs (`class_obj_id`, `teacher_id`, `subject_id`) in GET/POST responses, breaking frontend form binding.
   * **Solution**: Serializers now return **both** flat integer IDs (`*_id`) for straightforward frontend state mapping AND pre-fetched nested objects (`class_obj`, `teacher`, `subject`) for UI display rendering.
   * **Performance Impact**: Zero extra database queries. Accessing foreign key integer attributes in Django ORM (`instance.teacher_id`) reads directly from Python memory, and nested objects are pre-fetched via `select_related()`.

3. **User Creation & `clerk_id` Serialization**:
   * **Issue**: Creating users via `POST /api/v1/users/` with a `clerk_id` failed due to `clerk_id` being marked `read_only=True`.
   * **Solution**: `clerk_id` was updated to be writable during `POST` creation while enforcing uniqueness at the database level.

4. **Paid Session Protection (`paid = True`)**:
   * **Issue**: Deleting historical sessions that had already been processed in payroll corrupted financial history.
   * **Solution**: `SessionViewSet` and `AdHocSessionViewSet` overrides for `destroy()` and `bulk_delete()` strictly reject deleting any session where `paid=True`, returning `400 Bad Request`.

5. **Role-Based Dynamic Field Filtering**:
   * **Issue**: Sensitive student `check_in_token` values needed to be accessible by QR check-in terminals and staff/admin, but hidden from unauthorized roles.
   * **Solution**: Serializers dynamically evaluate request user permissions in `to_representation()` to conditionally exclude or include sensitive fields.

6. **Standardized Bulk Operations**:
   * Unified endpoints for `POST /api/v1/{resource}/bulk_create/` and `DELETE /api/v1/{resource}/bulk_delete/` were introduced to optimize network operations and batch updates.

---

## 🏗️ 2. Core System Architecture & Tech Stack

| Layer | Technology Choice | Architectural Purpose & Justification |
|---|---|---|
| **Backend Framework** | Django 5.x + Django REST Framework (DRF) | Built-in admin interface, robust ORM, mature authentication middleware, and permission frameworks. |
| **API Versioning & Specs** | DRF OpenAPI 3 (`drf-spectacular`) | Mounted at `/api/v1/` with Swagger UI (`/docs/`) and ReDoc (`/redoc/`). |
| **Database Store** | PostgreSQL (Hosted on Neon) | Enterprise-grade relational DB supporting foreign key constraints, indexes, unique constraints, and ACID transactions. |
| **Identity & Auth** | Clerk (OIDC / JWT) | Decoupled identity management. Frontend authenticates with Clerk; backend validates JWTs via Clerk's public JWKS endpoint. |
| **Frontend Stack** | Next.js (TypeScript) | Consumes REST API over HTTPS using JSON envelopes. Decoupled development model. |
| **Deployment & Hosting** | Render (Backend) / Vercel (Frontend) | Auto-deploy via git integration; blueprint configuration specified in `render.yaml`. |

---

## 🔐 3. Authentication & Access Control

### Auth Handshake Flow

```
+----------+      1. Authenticate       +----------+
| Next.js  | -------------------------> |  Clerk   |
| Frontend | <------------------------- |   Auth   |
+----------+   2. JWT Access Token      +----------+
     |
     | 3. API Request with 'Authorization: Bearer <JWT>'
     v
+--------------------------------------------------+
| Django REST Framework Backend                     |
|  a. JWT Authentication (`authentication.py`)     |
|     - Verifies JWT signature against Clerk JWKS  |
|     - Maps clerk_id to Django User record        |
|  b. Permission Check                              |
|     - Validates role permissions (Admin, etc.)   |
+--------------------------------------------------+
```

### Authorization Roles & Permission Classes

| Role Enum | Scope & Permissions | DRF Permission Class |
|---|---|---|
| `admin` | Full system read, write, update, delete across all endpoints. | `IsAdmin` |
| `staff` | Operational management (Students, Teachers, Timetable, Attendance, Check-Ins). | `IsStaffOrAdmin` |
| `teacher` | Read assigned classes/timetable; update status/attendance for owned sessions. | `IsTeacher`, `IsOwnerTeacher` |
| `student` | Read owned profile, enrolled classes, and own attendance records. | `IsStudent`, `IsOwnerStudent` |
| `terminal` | Read student check-in tokens; perform QR/manual check-in actions. | `IsTerminalOrStaffOrAdmin` |

---

## 📊 4. Database Structure & Model Specifications

The database schema is divided into 5 primary Django applications: `people`, `timetable`, `class_sessions`, `payroll` (archived), and core audit infrastructure.

### 4.1. People App (`people`)

#### `User` (Extends `AbstractUser`)
* `id` (PK, Auto)
* `clerk_id` (CharField, unique, index) — OIDC identifier from Clerk.
* `role` (CharField, choices: `admin`, `staff`, `teacher`, `student`, `terminal`, default: `student`)

#### `Subject`
* `id` (PK, Auto)
* `name` (CharField, unique)

#### `Teacher`
* `id` (PK, Auto)
* `name` (CharField)
* `employment_type` (CharField, choices: `full_time`, `tutor`, default: `tutor`)
* `default_rate` (DecimalField, max_digits=10, decimal_places=2, default=0.00)
* `contact` (CharField, nullable)
* `bank_details` (TextField, nullable)
* `user` (OneToOneField -> `User`, `on_delete=SET_NULL`, nullable, related_name=`teacher_profile`)

#### `Student`
* `id` (PK, Auto)
* `name` (CharField)
* `dob` (DateField, nullable)
* `enrollment_date` (DateField, auto_now_add=True)
* `contact` (CharField, nullable)
* `check_in_token` (CharField, max_length=64, unique, editable=False) — Auto-generated URL-safe token.
* `user` (OneToOneField -> `User`, `on_delete=SET_NULL`, nullable, related_name=`student_profile`)

#### `Staff`
* `id` (PK, Auto)
* `name` (CharField)
* `contact` (CharField, nullable)
* `user` (OneToOneField -> `User`, `on_delete=SET_NULL`, nullable, related_name=`staff_profile`)

#### `AuditLog`
* `id` (PK, Auto)
* `user` (ForeignKey -> `User`, `on_delete=SET_NULL`, nullable)
* `model_name` (CharField, index)
* `record_id` (CharField, index)
* `action` (CharField, choices: `create`, `update`, `delete`)
* `field_name` (CharField, nullable)
* `old_value` (TextField, nullable)
* `new_value` (TextField, nullable)
* `timestamp` (DateTimeField, auto_now_add=True, index)
* *Index*: `(model_name, record_id)`

---

### 4.2. Class & Timetable App (`timetable`)

#### `Class` (DB Model for Cohorts)
* `id` (PK, Auto)
* `education_level` (CharField, choices: `IAL`, `IG`, `Year1` .. `Year9`)
* `cohort_identifier` (CharField, max_length=1, e.g. 'E', 'F', 'K')
* `cohort_sub_category` (CharField, max_length=1, nullable, e.g. '1', '2', '3')
* *Constraints*: Unique constraint on `(education_level, cohort_identifier, cohort_sub_category)`.
* *String Representation*: e.g. `"IAL E"` or `"IG K3"`.

#### `ClassStudent` (Join Table)
* `id` (PK, Auto)
* `class_obj` (ForeignKey -> `Class`, `on_delete=CASCADE`, related_name=`class_students`)
* `student` (ForeignKey -> `Student`, `on_delete=CASCADE`, related_name=`enrolled_classes`)
* *Constraints*: Unique constraint on `(class_obj, student)`.

#### `TimetableSlot` (Recurring Template)
* `id` (PK, Auto)
* `class_obj` (ForeignKey -> `Class`, `on_delete=CASCADE`, related_name=`timetable_slots`)
* `subject` (ForeignKey -> `Subject`, `on_delete=CASCADE`, related_name=`timetable_slots`)
* `teacher` (ForeignKey -> `Teacher`, `on_delete=CASCADE`, related_name=`timetable_slots`)
* `day_of_week` (IntegerField, choices: 0=Monday .. 6=Sunday)
* `start_time` (TimeField)
* `end_time` (TimeField)
* `room` (CharField, max_length=100, nullable)
* *Validation*: `end_time` must be after `start_time`.
* *Index*: `(teacher, day_of_week)`.

---

### 4.3. Class Sessions & Attendance App (`class_sessions`)

#### `Session` (Dated Occurrence Generated from Timetable Slot)
* `id` (PK, Auto)
* `timetable_slot` (ForeignKey -> `TimetableSlot`, `on_delete=PROTECT`, related_name=`sessions`)
* `teacher` (ForeignKey -> `Teacher`, `on_delete=PROTECT`, related_name=`sessions`)
* `class_obj` (ForeignKey -> `Class`, `on_delete=PROTECT`, related_name=`sessions`)
* `start_time` (DateTimeField)
* `end_time` (DateTimeField)
* `status` (CharField, choices: `scheduled`, `completed`, `cancelled`, `no_show`, default=`scheduled`)
* `paid` (BooleanField, default=False) — Lock flag for payroll processing.
* *Constraints*: Unique constraint on `(timetable_slot, start_time)`.
* *Indexes*: `(teacher, start_time)`, `(start_time)`, `(status)`, `(paid)`.

#### `SessionAttendance`
* `id` (PK, Auto)
* `session` (ForeignKey -> `Session`, `on_delete=CASCADE`, related_name=`attendances`)
* `student` (ForeignKey -> `Student`, `on_delete=CASCADE`, related_name=`attendances`)
* `status` (CharField, choices: `present`, `absent`, `late`, default=`absent`)
* *Constraints*: Unique constraint on `(session, student)`.

#### `AdHocSession` (Non-recurring / One-off Sessions)
* `id` (PK, Auto)
* `teacher` (ForeignKey -> `Teacher`, `on_delete=PROTECT`, related_name=`adhoc_sessions`)
* `subject` (ForeignKey -> `Subject`, `on_delete=PROTECT`, related_name=`adhoc_sessions`)
* `date` (DateField, index)
* `start_time` (TimeField)
* `end_time` (TimeField)
* `status` (CharField, choices: `scheduled`, `completed`, `cancelled`, `no_show`, default=`scheduled`)
* `paid` (BooleanField, default=False)
* *Constraints*: Unique constraint on `(teacher, subject, date, start_time)`.

#### `AdHocSessionAttendance`
* `id` (PK, Auto)
* `ad_hoc_session` (ForeignKey -> `AdHocSession`, `on_delete=CASCADE`, related_name=`attendances`)
* `student` (ForeignKey -> `Student`, `on_delete=CASCADE`, related_name=`adhoc_attendances`)
* `status` (CharField, choices: `present`, `absent`, `late`, default=`absent`)

#### `CheckIn` (Daily Campus / QR Attendance)
* `id` (PK, Auto)
* `student` (ForeignKey -> `Student`, `on_delete=CASCADE`, related_name=`check_ins`)
* `date` (DateField, index)
* `timestamp` (DateTimeField, auto_now_add=True)
* `check_in_type` (CharField, choices: `qr`, `manual`, default=`qr`)
* `checked_by` (ForeignKey -> `User`, `on_delete=SET_NULL`, nullable)
* *Constraints*: Unique constraint on `(student, date)`.

---

### 4.4. Archived Payroll App (`payroll`)

*Note: Payroll models exist in codebase but URLs are currently archived/disabled until explicit feature activation.*

* `PayPeriod`: `start_date`, `end_date`.
* `Payslip`: Frozen snapshot containing calculated session count, rate, gross pay, deductions, net pay.
* `Adjustment`: Corrections (+/- signed amounts) absorbed into subsequent payslips without mutating locked session histories.

---

## 🛡️ 5. Data Integrity, Foreign Key Deletion Rules & Paid Lock Rules

### Foreign Key Deletion Behaviors Matrix

| Model | Referenced Field | `on_delete` Strategy | Rationale & Protection Logic |
|---|---|---|---|
| `Teacher` | `user` | `SET_NULL` | Deleting a user login leaves historical teacher record intact. |
| `Student` | `user` | `SET_NULL` | Deleting a user login leaves historical student record intact. |
| `Staff` | `user` | `SET_NULL` | Deleting a user login leaves historical staff record intact. |
| `ClassStudent` | `class_obj`, `student` | `CASCADE` | Removing class or student removes the join table entry. |
| `TimetableSlot` | `class_obj`, `subject`, `teacher` | `CASCADE` | Slot definition is deleted if parent class/subject/teacher is removed. |
| `Session` | `timetable_slot`, `teacher`, `class_obj` | `PROTECT` | Prevents deleting teachers/classes/slots if active historical sessions exist. |
| `AdHocSession` | `teacher`, `subject` | `PROTECT` | Prevents deleting teachers or subjects associated with ad-hoc sessions. |
| `SessionAttendance` | `session` | `CASCADE` | Deleting a session removes its specific attendance roster entries. |
| `SessionAttendance` | `student` | `CASCADE` | Deleting a student removes their attendance entries. |

### Business Logic Deletion Safeguards

1. **Paid Session Protection (`paid = True`)**:
   * Executing `DELETE /api/v1/sessions/{id}/` or `DELETE /api/v1/sessions/bulk_delete/` checks if any targeted session has `paid=True`.
   * **Behavior**: If `paid=True`, deletion is rejected with `400 Bad Request`:
     ```json
     {
       "error": "Cannot delete a session that has already been paid in payroll."
     }
     ```

---

## 📐 6. Unified API Serialization & Response Standards

### 6.1. Response Format (Paginated Envelope)

All GET list requests return a unified DRF `PageNumberPagination` envelope:

```json
{
  "count": 105,
  "next": "http://localhost:8000/api/v1/students/?page=2",
  "previous": null,
  "results": [
    {
      "id": 1,
      "name": "Student Name",
      ...
    }
  ]
}
```

### 6.2. Dual Relational Structure (Flat IDs + Pre-fetched Objects)

To eliminate client-side transformation issues while keeping database query counts minimal, DRF serializers output both representation types:

```json
{
  "id": 10,
  "day_of_week": 0,
  "start_time": "09:00:00",
  "end_time": "10:30:00",
  "room": "Room 101",
  "class_obj_id": 1,
  "class_obj": {
    "id": 1,
    "education_level": "IAL",
    "cohort_identifier": "E",
    "cohort_sub_category": null
  },
  "subject_id": 2,
  "subject": {
    "id": 2,
    "name": "Mathematics"
  },
  "teacher_id": 3,
  "teacher": {
    "id": 3,
    "name": "Jane Doe",
    "employment_type": "full_time"
  }
}
```

### 6.3. Writable Input Format

Frontend POST / PUT / PATCH requests submit primary key integer values using the `*_id` fields:

```json
{
  "class_obj_id": 1,
  "subject_id": 2,
  "teacher_id": 3,
  "day_of_week": 0,
  "start_time": "09:00:00",
  "end_time": "10:30:00",
  "room": "Room 101"
}
```

---

## ⚡ 7. Bulk Operations Specification

Bulk operations are available on high-frequency resources (`students`, `class-students`, `session-attendances`, `adhoc-session-attendances`, `sessions`, `adhoc-sessions`).

### 7.1. Bulk Create Endpoint
* **HTTP Method**: `POST /api/v1/{resource}/bulk_create/`
* **Payload Structure**:
  ```json
  {
    "items": [
      { "field1": "val1", "field2": "val2" },
      { "field1": "val3", "field2": "val4" }
    ]
  }
  ```
* **Success Response (201 Created)**:
  ```json
  {
    "created_count": 2,
    "items": [...]
  }
  ```

### 7.2. Bulk Delete Endpoint
* **HTTP Method**: `DELETE /api/v1/{resource}/bulk_delete/`
* **Payload Structure**:
  ```json
  {
    "ids": [10, 11, 12]
  }
  ```
* **Success Response (200 OK)**:
  ```json
  {
    "deleted_count": 3,
    "deleted_ids": [10, 11, 12]
  }
  ```

---

## 📋 8. Comprehensive Endpoint Directory

### 8.1. Auth & System Meta Endpoints

| Route | HTTP Method | Access Level | Description & Notes |
|---|---|---|---|
| `/api/v1/me/` | GET | Authenticated | Returns authenticated user info & linked role profile. |
| `/api/v1/schema/` | GET | Open | OpenAPI 3 JSON schema endpoint. |
| `/api/v1/docs/` | GET | Open | Interactive Swagger UI API documentation. |
| `/api/v1/redoc/` | GET | Open | ReDoc API documentation. |

---

### 8.2. People Module (`/api/v1/`)

| Route | HTTP Methods | Response / Payload | Access & Validation Rules |
|---|---|---|---|
| `/api/v1/users/` | GET, POST | Paginated Envelope / `User` Object | Admin only. `clerk_id` writable on POST. |
| `/api/v1/users/{id}/` | GET, PUT, PATCH, DELETE | `User` Object | Admin only. Supports updating username, email, role, is_active. |
| `/api/v1/teachers/` | GET, POST | Paginated Envelope / `Teacher` Object | Read: Staff/Admin/Teacher. Write: Admin. |
| `/api/v1/teachers/{id}/` | GET, PUT, PATCH, DELETE | `Teacher` Object | Protected if referenced by historical sessions. |
| `/api/v1/students/` | GET, POST | Paginated Envelope / `Student` Object | `check_in_token` visible to Admin/Staff/Terminal & self. |
| `/api/v1/students/{id}/` | GET, PUT, PATCH, DELETE | `Student` Object | Supports `POST /bulk_create/` & `DELETE /bulk_delete/`. |
| `/api/v1/staff/` | GET, POST | Paginated Envelope / `Staff` Object | Staff & Admin only. |
| `/api/v1/subjects/` | GET, POST | Paginated Envelope / `Subject` Object | Read: All authenticated. Write: Admin. |
| `/api/v1/audit-logs/` | GET | Paginated Envelope | Read-only. System activity history logs. |

---

### 8.3. Timetable Module (`/api/v1/`)

| Route | HTTP Methods | Response / Payload | Access & Validation Rules |
|---|---|---|---|
| `/api/v1/classes/` | GET, POST | Paginated Envelope / `Class` Object | Unique constraint on level + cohort + sub_category. |
| `/api/v1/classes/{id}/` | GET, PUT, PATCH, DELETE | `Class` Object | Protected if referenced by active timetable slots. |
| `/api/v1/class-students/` | GET, POST, DELETE | Paginated Envelope / Join Object | Class student enrollment roster mapping. Supports bulk operations. |
| `/api/v1/timetable-slots/` | GET, POST, PUT, PATCH, DELETE | Paginated Envelope / Slot Object | Writable via `class_obj_id`, `subject_id`, `teacher_id`. |
| `/api/v1/timetable/teacher/{teacher_id}/` | GET | Paginated Envelope | Pivoted timetable grid for a specific teacher. |
| `/api/v1/timetable/class/{class_id}/` | GET | Paginated Envelope | Pivoted timetable grid for a specific class cohort. |

---

### 8.4. Class Sessions, Attendance & Check-Ins (`/api/v1/`)

| Route | HTTP Methods | Response / Payload | Access & Validation Rules |
|---|---|---|---|
| `/api/v1/sessions/` | GET, POST, PUT, PATCH, DELETE | Paginated Envelope / `Session` Object | Filterable by `teacher_id`, `class_id`, `start_time`. **Protected if `paid=True`**. |
| `/api/v1/sessions/{id}/status/` | PATCH | `Session` Object | Quick status update (`scheduled`, `completed`, `cancelled`, `no_show`). |
| `/api/v1/sessions/generate/{class_id}/` | POST | `{"created_count": N, "sessions": [...]}` | Batch generates dated sessions from timetable slots. Payload: `{"start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD"}`. |
| `/api/v1/session-attendances/` | GET, POST, PUT, PATCH, DELETE | Paginated Envelope / Attendance Object | Bulk roster recording via `/bulk_create/` & `/bulk_delete/`. |
| `/api/v1/adhoc-sessions/` | GET, POST, PUT, PATCH, DELETE | Paginated Envelope / AdHoc Object | One-off tutor/makeup sessions. **Protected if `paid=True`**. |
| `/api/v1/adhoc-session-attendances/` | GET, POST, PUT, PATCH, DELETE | Paginated Envelope / Attendance Object | Attendance roster for ad-hoc sessions. |
| `/api/v1/check-ins/` | GET | Paginated Envelope | Daily check-in log. Filterable by `student_id` & `date`. |
| `/api/v1/check-ins/qr/` | POST | 201 Created (`CheckIn` Object) | Accepts `{"check_in_token": "..."}`. Returns 409 Conflict if already checked in today. |
| `/api/v1/check-ins/manual/` | POST | 201 Created (`CheckIn` Object) | Accepts `{"student_id": N}`. Executed by Terminal/Staff/Admin. |
| `/api/v1/stats/` | GET | `{"total_students": N, "today_checkins": N, ...}` | Summary statistics dashboard endpoint. |

---

## 🔮 9. Deferred Modules & Future Expansion Roadmap

1. **Payroll Module Reactivation**:
   * The `payroll` application is structurally fully implemented with frozen snapshot payslips and signed adjustments logic (`models.py`, `views.py`, `serializers.py`).
   * Reactivation requires un-commenting routes in `payroll/urls.py` and adding `path('', include('payroll.urls'))` in `config/urls.py`.

2. **Academic Records Module (Phase 2 Roadmap)**:
   * Exams, subject grades, GPA calculations, and student report card generation can be attached via a dedicated `academic_records` Django app without mutating existing timetable or session tracking models.