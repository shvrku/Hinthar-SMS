# API Unified Structure — History & Technical Specification

## 📜 Historical Context & Motivation

During early iterations of the Hinthar School Management System (SMS) API, endpoint response formats evolved organically across different Django apps (`people`, `timetable`, `class_sessions`, `payroll`). 

This resulted in core API contract inconsistencies between backend responses and frontend consumption (Next.js client) across both **GET (Read)** and **POST / PUT / PATCH / DELETE (Write & Bulk)** operations:

1. **Unstable DRF Pagination Slicing (Apparent Duplicate Records)**:
   * **Symptom**: The frontend observed identical student or attendance records appearing across multiple pages (e.g. page 1 and page 2).
   * **Root Cause**: Django REST Framework (DRF) global `PageNumberPagination` (page size = 50) was active, but ModelViewSet querysets lacked explicit deterministic `ordering` (e.g. `ordering = ['id']`). In PostgreSQL, executing `LIMIT/OFFSET` queries without an explicit `ORDER BY` clause produces non-deterministic tuple ordering between page requests.
2. **Hidden Flat Relation IDs in POST/PUT/GET Responses (`write_only=True`)**:
   * **Symptom**: When client applications submitted payloads using flat primary keys (e.g., `{"class_obj_id": 1, "subject_id": 2}`), the backend accepted the write, but returned JSON responses containing **only** nested objects (`class_obj`, `subject`), completely stripping out flat keys (`class_obj_id`, `subject_id`).
   * **Root Cause**: Serializers defined relational `PrimaryKeyRelatedField`s with `write_only=True`. Frontends inspecting `response.data.class_obj_id` evaluated to `undefined` after POST, PUT, or GET calls.
3. **`User` POST Creation `clerk_id` Serialization Bug**:
   * **Symptom**: Creating a user via `POST /api/v1/users/` with a `clerk_id` failed with a database integrity error.
   * **Root Cause**: `clerk_id` was marked as `read_only=True` in `UserSerializer`, causing DRF to strip `clerk_id` from write payloads before reaching database model validation.
4. **APIView vs ViewSet Envelope Mismatch**:
   * **Symptom**: Most list endpoints returned a paginated envelope `{ count, next, previous, results }`, but custom `APIView` list endpoints (such as `TeacherTimetableView` and `ClassTimetableView`) returned raw JSON arrays `[...]`. Client code attempting to unwrap `res.data.results` crashed.

---

## 🔒 Data Protection & Deletion Rules (`CASCADE` vs `PROTECT`)

### How Foreign Key `on_delete` Behaviors Work in Django:

1. **`CASCADE`**: 
   * Deleting the parent record automatically deletes all child records pointing to it.
   * *Example*: Deleting a `Session` cascade-deletes all its `SessionAttendance` records (`SessionAttendance.session` has `on_delete=CASCADE`).
2. **`PROTECT`**:
   * Prevents deletion of the parent record if any child record references it, raising a `django.db.models.ProtectedError`.
   * *Example*: `Session.teacher`, `Session.class_obj`, and `Session.timetable_slot` use `on_delete=PROTECT`. A teacher or class cannot be deleted while historical sessions reference them, protecting payroll and schedule history.
3. **`SET_NULL`**:
   * Sets the child record's foreign key to `NULL` when the parent is deleted.
   * *Example*: `Teacher.user` uses `on_delete=SET_NULL`. Deleting a `User` login account leaves the `Teacher` profile intact with `user_id = null`.
4. **`RESTRICT`**:
   * Prevents deletion unless the protected object is also deleted in the same cascade chain.

---

## 🛡️ Model Data Protection Audit & Mismatch Safeguards

### 1. Paid Session Deletion Protection (`paid = True`)
* **Rule**: Sessions (`Session` and `AdHocSession`) marked as `paid=True` have already been processed for teacher payroll.
* **Safeguard**: `SessionViewSet.destroy()`, `SessionViewSet.bulk_delete()`, `AdHocSessionViewSet.destroy()`, and `AdHocSessionViewSet.bulk_delete()` strictly reject deleting any session where `paid=True`, returning a `400 Bad Request` (`{"error": "Cannot delete a session that has already been paid in payroll."}`).

### 2. Timetable Slot Protection
* `TimetableSlot.teacher`, `TimetableSlot.subject`, and `TimetableSlot.class_obj` use `PROTECT` to prevent accidental deletion of teachers, subjects, or classes while active recurring schedules depend on them.

---

## ⚡ Performance Impact Analysis

### Returning Both Flat IDs & Nested Objects
* **Database Query Overhead**: **Zero (0) extra database queries**.
  * In Django ORM, accessing foreign key integer IDs on model instances (e.g., `instance.teacher_id`, `instance.class_obj_id`) reads directly from Python object memory. It does not issue any SQL query.
  * Nested objects (`instance.teacher`, `instance.class_obj`) are already efficiently pre-fetched via `select_related()` on all viewsets.
* **Payload Overhead**: **Negligible (~15 to 30 bytes per record)**.

---

## 🚀 Bulk Operations Specification (Bulk Insert & Bulk Delete)

### 1. Bulk Insert / Create Endpoint
* **HTTP Method & URL**: `POST /api/v1/{resource}/bulk_create/`
* **Request Body**: `{"items": [...]}`
* **Success Response (201 Created)**: `{"created_count": N, "items": [...]}`

### 2. Bulk Delete Endpoint
* **HTTP Method & URL**: `DELETE /api/v1/{resource}/bulk_delete/`
* **Request Body**: `{"ids": [10, 11, 12]}`
* **Success Response (200 OK)**: `{"deleted_count": N, "deleted_ids": [...]}`

---

## 📋 Comprehensive Endpoint Reference Table

| Endpoint Route | HTTP Methods | Response Shape / Status | Protection & Write Rules |
|---|---|---|---|
| `/api/v1/students/` | GET, POST | GET: Paginated envelope<br>POST: 201 Created | Supports `POST /bulk_create/` & `DELETE /bulk_delete/` |
| `/api/v1/teachers/` | GET, POST | GET: Paginated envelope<br>POST: 201 Created | Protected if referenced by sessions |
| `/api/v1/subjects/` | GET, POST | GET: Paginated envelope<br>POST: 201 Created | Protected if referenced by slots |
| `/api/v1/classes/` | GET, POST | GET: Paginated envelope<br>POST: 201 Created | Protected if referenced by slots |
| `/api/v1/class-students/` | GET, POST, DELETE | GET: Paginated envelope<br>POST: 201 Created | Includes flat IDs & `DELETE /bulk_delete/` |
| `/api/v1/timetable-slots/` | GET, POST, PUT, PATCH, DELETE | GET: Paginated envelope<br>POST: 201 Created | Protected if referenced by sessions |
| `/api/v1/timetable/teacher/{id}/` | GET | Paginated envelope | Standardized list envelope |
| `/api/v1/timetable/class/{id}/` | GET | Paginated envelope | Standardized list envelope |
| `/api/v1/sessions/` | GET, POST, PUT, PATCH, DELETE | GET: Paginated envelope<br>POST: 201 Created | **Protected if `paid=True`**. Filterable & bulk delete. |
| `/api/v1/sessions/{id}/status/` | PATCH | 200 OK (Session object) | Accepts `{"status": "..."}` |
| `/api/v1/sessions/generate/{class_id}/` | POST | 200 OK (Generation Summary) | Batch session generation |
| `/api/v1/session-attendances/` | GET, POST, PUT, PATCH, DELETE | GET: Paginated envelope<br>POST: 201 Created | Supports `POST /bulk_create/` & `DELETE /bulk_delete/` |
| `/api/v1/check-ins/` | GET | Paginated envelope | Filterable by `student_id` & `date` |
| `/api/v1/check-ins/qr/` | POST | 201 Created / 409 Conflict | Accepts `check_in_token` |
| `/api/v1/check-ins/manual/` | POST | 201 Created / 409 Conflict | Accepts `student_id` |
| `/api/v1/adhoc-sessions/` | GET, POST, PUT, PATCH, DELETE | GET: Paginated envelope<br>POST: 201 Created | **Protected if `paid=True`**. Filterable & bulk delete. |
| `/api/v1/adhoc-session-attendances/` | GET, POST, PUT, PATCH, DELETE | GET: Paginated envelope<br>POST: 201 Created | Supports `POST /bulk_create/` & `DELETE /bulk_delete/` |
| `/api/v1/users/` | GET, POST, PUT, PATCH | GET: Paginated envelope<br>POST: 201 Created | `clerk_id` writable on create |
