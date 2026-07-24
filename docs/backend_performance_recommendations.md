# Backend Query & Filtering Performance Recommendations

This document outlines technical recommendations for optimizing data querying and filtering performance in the **Hinthar School Management System (SMS)** backend (Django REST Framework + PostgreSQL).

---

## 1. Database Indexing Optimizations (PostgreSQL & Django ORM)

Adding target composite indexes on frequently filtered column pairs accelerates SQL query execution and eliminates sequential table scans.

### Proposed Index Definitions

Add the following index configurations in the respective Django models (`Meta.indexes`):

```python
# class_sessions/models.py
class Session(models.Model):
    ...
    class Meta:
        indexes = [
            # Speeds up filtering sessions by class & start time date range
            models.Index(fields=['class_obj', 'start_time'], name='idx_session_class_start'),
            # Speeds up filtering sessions by teacher & start time date range
            models.Index(fields=['teacher', 'start_time'], name='idx_session_teacher_start'),
            # Speeds up status & payroll state checks
            models.Index(fields=['status', 'paid'], name='idx_session_status_paid'),
        ]

class SessionAttendance(models.Model):
    ...
    class Meta:
        indexes = [
            # Speeds up attendance lookup by session & student
            models.Index(fields=['session', 'student'], name='idx_attendance_sess_stud'),
        ]

# timetable/models.py
class ClassStudent(models.Model):
    ...
    class Meta:
        indexes = [
            # Speeds up looking up active roster students per class
            models.Index(fields=['class_obj', 'student'], name='idx_class_student_rel'),
        ]
```

---

## 2. DRF Queryset Eager Loading (`select_related` & `prefetch_related`)

Eliminate **N+1 database query issues** across DRF ViewSets by eager-loading foreign keys and child relations in a single query:

```python
# class_sessions/views.py
class SessionViewSet(viewsets.ModelViewSet):
    def get_queryset(self):
        return Session.objects.select_related(
            'teacher',
            'class_obj',
            'timetable_slot__subject',
            'timetable_slot__teacher'
        ).prefetch_related('attendances').all()

class SessionAttendanceViewSet(viewsets.ModelViewSet):
    def get_queryset(self):
        return SessionAttendance.objects.select_related(
            'session',
            'student'
        ).all()
```

---

## 3. Server-Side Range Filtering (`django-filter`)

Add explicit date range parameters (`start_date`, `end_date`, `month`, `year`) on list endpoints so the backend filters querysets before pagination. This avoids forcing the frontend to paginate through years of historical sessions.

```python
# class_sessions/filters.py
import django_filters
from .models import Session

class SessionFilter(django_filters.FilterSet):
    start_date = django_filters.DateFilter(field_name="start_time", lookup_expr='gte')
    end_date = django_filters.DateFilter(field_name="start_time", lookup_expr='lte')
    class_id = django_filters.NumberFilter(field_name="class_obj__id")
    teacher_id = django_filters.NumberFilter(field_name="teacher__id")
    subject_id = django_filters.NumberFilter(field_name="timetable_slot__subject__id")

    class Meta:
        model = Session
        fields = ['class_id', 'teacher_id', 'subject_id', 'status', 'start_date', 'end_date']
```

---

## 4. Sparse Field Selection & Projections (`drf-flex-fields`)

When client comboboxes fetch reference lists (`/api/v1/teachers/`, `/api/v1/subjects/`, `/api/v1/classes/`), they only require `id` and `name`. 

Using `drf-flex-fields` or `only()` in Django ORM defers unused database text columns (`bank_details`, `contact`, `user`), reducing payload sizes by up to **80%**.

---

## 5. Redis In-Memory Caching for Reference Endpoints

Cache static/semi-static lookup options (`/classes/`, `/subjects/`, `/teachers/`) in Redis for 5–15 minutes. Automatically invalidate cache entries when a model instance is saved or deleted via Django signals:

```python
from django.views.decorators.cache import cache_page
from django.utils.decorators import method_decorator

class ClassViewSet(viewsets.ModelViewSet):
    @method_decorator(cache_page(60 * 15))
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
```

---

## 6. Dedicated Aggregated Attendance Matrix Endpoint

Create a dedicated summary endpoint `GET /api/v1/attendance/matrix/` that returns the combined student list, sessions, and attendance statuses for a given class/month in a single HTTP response:

### Request
`GET /api/v1/attendance/matrix/?class_id=1&month=7&year=2026`

### Response Shape (200 OK)
```json
{
  "class_id": 1,
  "sessions": [
    { "id": 101, "start_time": "2026-07-02T09:00:00Z", "subject": "Mathematics" }
  ],
  "students": [
    {
      "id": 5,
      "name": "Alex Smith",
      "records": {
        "101": "present"
      }
    }
  ]
}
```

* **Impact**: Replaces **4 sequential frontend HTTP requests** with **1 optimized aggregated payload**.

---

## Summary of Expected Performance Impact

| Optimization | Target Endpoint | Performance Benefit |
|---|---|---|
| **Composite Database Indexes** | All list endpoints | Eliminates sequential table scans on multi-column queries |
| **`select_related` Eager Loading** | `/sessions/`, `/session-attendances/` | Reduces SQL queries per page from ~100 to 2 queries |
| **Server-Side Range Filters** | `/sessions/` | Prevents unnecessary DRF pagination loops |
| **Redis Reference Caching** | `/classes/`, `/subjects/`, `/teachers/` | Instant sub-10ms response times for comboboxes |
| **Attendance Matrix Endpoint** | `/attendance/matrix/` | 3x faster grid load times by avoiding waterfall fetches |
