# Backend Performance Recommendations Implementation Plan

Implement backend performance optimizations outlined in `backend_performance_recommendations.md`, skipping Redis caching as requested due to single-node infrastructure constraints.

## User Review Required

> [!IMPORTANT]
> **Redis Caching Skipped**: As per your instruction ("skip Redis Caching if we require more infra for it"), section 5 (Redis In-Memory Caching) is skipped to avoid adding infrastructure dependencies (Redis daemon/container). All other database, query, filtering, projection, and matrix endpoint optimizations will be fully implemented.

> [!NOTE]
> **API Unified Structure Compliance**: All endpoints, serializers, and matrix payloads strictly maintain API Unified Structure standards:
> - Deterministic ordering (`ordering = ['id']`) to prevent paginated duplicates.
> - Preserving both flat IDs (`teacher_id`, `class_obj_id`, `subject_id`) and nested objects in serializations.
> - Retaining `paid=True` safeguards on delete actions.

## Proposed Changes

---

### 1. Database Indexing Optimizations

#### [MODIFY] [class_sessions/models.py](file:///d:/SchoolClubActivity/Hinthar-SMS/Hinthar-SMS/class_sessions/models.py)
* Add composite indexes to `Session` (`['class_obj', 'start_time']`, `['teacher', 'start_time']`, `['status', 'paid']`).
* Add composite index to `SessionAttendance` (`['session', 'student']`).

#### [MODIFY] [timetable/models.py](file:///d:/SchoolClubActivity/Hinthar-SMS/Hinthar-SMS/timetable/models.py)
* Add composite index to `ClassStudent` (`['class_obj', 'student']`).

*Generate database migrations using `python manage.py makemigrations` and apply with `python manage.py migrate`.*

---

### 2. DRF Queryset Eager Loading (`select_related` & `prefetch_related`)

#### [MODIFY] [class_sessions/views.py](file:///d:/SchoolClubActivity/Hinthar-SMS/Hinthar-SMS/class_sessions/views.py)
* Update `SessionViewSet.queryset` with `select_related('teacher__user', 'class_obj', 'timetable_slot__subject', 'timetable_slot__teacher__user', 'timetable_slot__class_obj')` and `prefetch_related('attendances')`.
* Update `SessionAttendanceViewSet.queryset` with `select_related('session__teacher', 'session__class_obj', 'session__timetable_slot__subject', 'student__user')`.

---

### 3. Server-Side Range Filtering

#### [MODIFY] [class_sessions/views.py](file:///d:/SchoolClubActivity/Hinthar-SMS/Hinthar-SMS/class_sessions/views.py)
* Enhance `SessionViewSet.get_queryset()` to parse and apply range parameters (`start_date`, `end_date`, `month`, `year`, `class_id`, `teacher_id`, `subject_id`) in addition to existing query parameters before DRF pagination slicing.

---

### 4. Sparse Field Projections

#### [MODIFY] [people/views.py](file:///d:/SchoolClubActivity/Hinthar-SMS/Hinthar-SMS/people/views.py)
#### [MODIFY] [timetable/views.py](file:///d:/SchoolClubActivity/Hinthar-SMS/Hinthar-SMS/timetable/views.py)
* Add support for lightweight/sparse responses or `only()` query projections when fetching reference combobox data (`/teachers/`, `/subjects/`, `/classes/`).

---

### 5. Attendance Matrix Aggregated Endpoint

#### [MODIFY] [class_sessions/views.py](file:///d:/SchoolClubActivity/Hinthar-SMS/Hinthar-SMS/class_sessions/views.py)
* Implement `AttendanceMatrixView` (APIView) supporting `GET /api/v1/attendance/matrix/?class_id=X&month=Y&year=Z`.
* Fetches sessions, enrolled students, and attendance status matrix for a given class & month/year in a single optimized DB query pass.

#### [MODIFY] [class_sessions/urls.py](file:///d:/SchoolClubActivity/Hinthar-SMS/Hinthar-SMS/class_sessions/urls.py)
* Add route `path('attendance/matrix/', views.AttendanceMatrixView.as_view(), name='attendance-matrix')`.

---

### 6. Documentation & Technical History Log

#### [MODIFY] [docs/API_UNIFIED_STRUCTURE_HISTORY.md](file:///d:/SchoolClubActivity/Hinthar-SMS/Hinthar-SMS/docs/API_UNIFIED_STRUCTURE_HISTORY.md)
* Record all performance optimizations implemented (Composite DB Indexes, Eager Loading, Range Filtering, Sparse Field Projections, Attendance Matrix Endpoint) and document the explicit exclusion of Redis Caching.

---

## Verification Plan

### Automated Tests
- Run existing and new unit tests via Django test runner:
  `python manage.py test class_sessions timetable people`
- Add unit tests in `class_sessions/tests.py` verifying:
  1. `AttendanceMatrixView` returns expected JSON structure and matrix records.
  2. `SessionViewSet` range filtering works with `start_date`, `end_date`, `month`, `year`, `subject_id`, and `class_id`.

### Manual Verification
- Execute test queries against local server endpoints (`/api/v1/sessions/`, `/api/v1/attendance/matrix/`) and verify performance and response contracts.
