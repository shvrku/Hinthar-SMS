# Hinthar SMS — Backend Data Models & Database Schema Reference

**Repository:** `Hinthar-SMS/Hinthar-SMS`  
**Stack:** Django 5 · Django REST Framework · PostgreSQL  
**Source of Truth Model Files:**
- Identity & Directory: [`people/models.py`](../people/models.py)
- Cohorts, Courses & Weekly Timetable: [`timetable/models.py`](../timetable/models.py)
- Dated Sessions, Roll Attendance & Campus Check-In: [`class_sessions/models.py`](../class_sessions/models.py)
- Announcements, Events & Registrations: [`communications/models.py`](../communications/models.py)
- Next-Pass Modules (Backend Scaffolded, UI Pending Next Pass):
  - Exam Tracking & Report Cards: [`academics/models.py`](../academics/models.py)
  - Payroll & Student Fees: [`payroll/models.py`](../payroll/models.py)

---

## 1. Cross-App Entity Relationship Informatics (ASCII)

```text
===================================================================================================
                           IDENTITY & DIRECTORY LAYER (people app)
===================================================================================================

                       +-----------------------------------------+
                       |              people.User                |
                       |-----------------------------------------|
                       | PK  id                                  |
                       | UQ  clerk_id (Clerk OIDC sub)           |
                       |     role (admin|staff|terminal|         |
                       |           teacher|student|pending)      |
                       |     is_active (bool)                    |
                       +----+---------------+---------------+----+
                            |               |               |
          1:1 (SET_NULL)    |               | 1:1           | 1:1 (SET_NULL)
     +----------------------+               | (SET_NULL)    +----------------------+
     v                                      v                                      v
+----------------------------+     +----------------------------+     +----------------------------+
|      people.Student        |     |      people.Teacher        |     |       people.Staff         |
|----------------------------|     |----------------------------|     |----------------------------|
| PK id                      |     | PK id                      |     | PK id                      |
| UQ unique_code (HIS24-...) |     | UQ unique_code (HIST22-..) |     | UQ unique_code (HISS24-..) |
| UQ check_in_token (64ch)   |     |    employment_type         |     |    school_code             |
|    check_in_token_active   |     |    school_code             |     | FK user_id (nullable)      |
| UQ exam_candidate_number   |     | FK user_id (nullable)      |     +----------------------------+
| FK user_id (nullable)      |     +-------------+--------------+
+------+--------------+------+                   |
       |              |                          |
       |              |        +-----------------+-----------------+
       |              |        |                                   |
       |              |        |          +------------------------+
       |              |        |          |     people.Subject     |
       |              |        |          |------------------------|
       |              |        |          | PK id                  |
       |              |        |          | UQ name                |
       |              |        |          +-----------+------------+
       |              |        |                      |
=======|==============|========|======================|============================================
       |              |        |  COHORTS & TIMETABLE LAYER (timetable app)
=======|==============|========|======================|============================================
       |              |        |                      |
       |              v        |                      v
       |   +-------------------+--------+    +--------+-------------------+
       |   |   timetable.ClassStudent   |    |      timetable.Course      |
       |   |----------------------------|    |----------------------------|
       |   | PK id                      |    | PK id                      |
       |   | UQ student_id (Max 1 Cohort|    | FK class_obj_id  (CASCADE) |<--+
       |   | FK class_obj_id  (CASCADE) |    | FK subject_id    (CASCADE) |   |
       |   | FK student_id    (CASCADE) |    | FK default_teacher_id      |   |
       |   +--------------+-------------+    +--------+-------------------+   |
       |                  |                           |                       |
       |                  |      +--------------------+                       |
       |                  v      v                                            |
       |   +--------------+------+------+                                     |
       |   |      timetable.Class       | (Domain Alias: Cohort)              |
       |   |----------------------------|                                     |
       |   | PK id                      |                                     |
       |   |    education_level (IG/IAL)|                                     |
       |   |    cohort_identifier (K/A) |                                     |
       |   |    cohort_sub_category (1) |                                     |
       |   +--------------+-------------+                                     |
       |                  |                                                   |
       |                  v                                                   |
       |   +--------------+--------------------+                              |
       |   |     timetable.TimetableSlot       |                              |
       |   |-----------------------------------|                              |
       |   | PK id                             |                              |
       |   | FK class_obj_id  (CASCADE)        |                              |
       |   | FK subject_id    (CASCADE)        |                              |
       |   | FK course_id     (CASCADE, auto)  |------------------------------+
       |   | FK teacher_id    (CASCADE)        |<--(Assigned Teacher)
       |   |    day_of_week (0=Mon .. 6=Sun)   |
       |   |    start_time, end_time, room     |
       |   +--------------+--------------------+
       |                  |
=======|==================|========================================================================
       |                  |   OPERATIONS, SESSIONS & CHECK-IN LAYER (class_sessions app)
=======|==================|========================================================================
       |                  |
       |                  v 1:N (PROTECT)
       |   +--------------+--------------------+     +------------------------------------+
       |   |      class_sessions.Session       |     |    class_sessions.AdHocSession     |
       |   |-----------------------------------|     |------------------------------------|
       |   | PK id                             |     | PK id                              |
       |   | FK timetable_slot_id (PROTECT)    |     | FK teacher_id        (PROTECT)     |
       |   | FK class_obj_id      (PROTECT)    |     | FK actual_teacher_id (PROTECT,null)|
       |   | FK teacher_id        (PROTECT)    |     | FK subject_id        (PROTECT)     |
       |   | FK actual_teacher_id (PROTECT,Sub)|     |    date, start_time, end_time      |
       |   |    start_time, end_time (ISO)     |     |    status                          |
       |   |    status (scheduled|completed|..)|     +-----------------+------------------+
       |   +--------------+--------------------+                       |
       |                  | 1:N (CASCADE)                              | 1:N (CASCADE)
       |                  v                                            v
       |   +--------------+--------------------+     +-----------------+------------------+
       +-->| class_sessions.SessionAttendance  |     |class_sessions.AdHocSessionAttendance|
       |   |-----------------------------------|     |------------------------------------|
       |   | PK id                             |     | PK id                              |
       |   | UQ (session_id, student_id)       |     | UQ (ad_hoc_session_id, student_id) |
       |   |    status (present|late|absent|   |     |    status (present|late|absent|    |
       |   |            excused)               |     |            excused)                |
       |   | FK auto_marked_by_checkin_id      |     | FK auto_marked_by_checkin_id       |
       |   +-----------------------------------+     +------------------------------------+
       |
       +-->+-----------------------------------+
           |      class_sessions.CheckIn       |
           |-----------------------------------|
           | PK id                             |
           | UQ (student_id, date)             |
           |    timestamp (auto_now_add)       |
           |    check_in_type (qr | manual)    |
           | FK checked_by_id -> people.User   |
           +-----------------------------------+
```

---

## 2. `people` App Models ([`people/models.py`](../people/models.py))

### 2.1 `people.User`
Custom user model (`AUTH_USER_MODEL = 'people.User'`) extending `AbstractUser`. Authenticates via Clerk OIDC JWTs (`clerk_id`) while storing authorization role and active state locally in PostgreSQL.

| Field | Type | Constraints / Defaults | Description |
| :--- | :--- | :--- | :--- |
| `id` | `BigAutoField` | PK | Internal database ID |
| `username` | `CharField(150)` | `unique=True` | Auto-derived username or Clerk handle |
| `email` | `EmailField` | `blank=True` | Primary email synced from Clerk |
| `first_name` / `last_name` | `CharField(150)` | `blank=True` | Name fields synced from Clerk |
| `clerk_id` | `CharField(255)` | `unique=True, db_index=True` | Immutable Clerk subject (`sub`) identifier (`user_...`) |
| `role` | `CharField(20)` | `default='pending'` | One of: `'admin'`, `'staff'`, `'terminal'`, `'teacher'`, `'student'`, `'pending'` |
| `is_active` | `BooleanField` | `default=True` | When `False`, blocks all API routes except `GET /api/v1/me/` |
| `date_joined` / `last_login` | `DateTimeField` | Standard Django | Account creation & login timestamps |

- **Reverse 1:1 Profiles:** `student_profile` (`people.Student`), `teacher_profile` (`people.Teacher`), `staff_profile` (`people.Staff`).

### 2.2 `people.Student`
Student demographic record, campus QR pass token, and optional `1:1` link to `people.User`.

| Field | Type | Constraints / Defaults | Description |
| :--- | :--- | :--- | :--- |
| `id` | `BigAutoField` | PK | Student ID |
| `name` | `CharField(255)` | Required | Full student name |
| `dob` | `DateField` | `null=True, blank=True` | Date of birth (`YYYY-MM-DD`) |
| `enrollment_date` | `DateField` | `auto_now_add=True` | Date enrolled |
| `contact` | `CharField(500)` | `null=True, blank=True` | Phone / guardian contact info |
| `school_code` | `CharField(10)` | `default='HIS'`, choices: `HIS`, `SPD`, `SPN`, `YWM` | Campus/branch prefix |
| `unique_code` | `CharField(50)` | `unique=True, db_index=True, editable=False` | Auto-generated on first save: `{SchoolCode}{Year}-{Seq:05d}` (e.g. `HIS24-00143`) |
| `exam_candidate_number` | `CharField(50)` | `unique=True, null=True, blank=True, db_index=True` | Optional external examination candidate ID |
| `check_in_token` | `CharField(64)` | `unique=True, editable=False` | Secret 32-byte URL-safe QR token (`secrets.token_urlsafe(32)`) |
| `check_in_token_active` | `BooleanField` | `default=True` | When `False`, gate QR scans are rejected with `403` |
| `user` | `OneToOneField(User)` | `on_delete=SET_NULL, null=True, related_name='student_profile'` | Linked Clerk-backed `User` account |

- **Model Methods & Hooks:**
  - `save()`: Auto-populates `check_in_token` via `secrets.token_urlsafe(32)` and `unique_code` via `people.utils.generate_unique_code(self)` if blank.
  - `regenerate_check_in_token()`: Generates a new `secrets.token_urlsafe(32)`, sets `check_in_token_active = True`, and persists `update_fields=['check_in_token', 'check_in_token_active']`.

### 2.3 `people.Teacher`
Faculty / tutor record and optional `1:1` link to `people.User`.

| Field | Type | Constraints / Defaults | Description |
| :--- | :--- | :--- | :--- |
| `id` | `BigAutoField` | PK | Teacher ID |
| `name` | `CharField(255)` | Required | Full teacher name |
| `employment_type` | `CharField(20)` | `default='tutor'`, choices: `full_time`, `tutor` | Employment classification |
| `contact` | `CharField(500)` | `null=True, blank=True` | Phone / email contact |
| `join_date` | `DateField` | `default=timezone.now` | Date joined |
| `school_code` | `CharField(10)` | `default='HIS'`, choices: `HIS`, `SPD`, `SPN`, `YWM` | Campus/branch code |
| `unique_code` | `CharField(50)` | `unique=True, db_index=True, editable=False` | Auto-generated: `{SchoolCode}T{JoinYear}-{Seq:05d}` (e.g. `HIST22-00007`) |
| `user` | `OneToOneField(User)` | `on_delete=SET_NULL, null=True, related_name='teacher_profile'` | Linked Clerk-backed `User` account |

### 2.4 `people.Staff`
Non-teaching operations staff record.

| Field | Type | Constraints / Defaults | Description |
| :--- | :--- | :--- | :--- |
| `id` | `BigAutoField` | PK | Staff ID |
| `name` | `CharField(255)` | Required | Full name |
| `contact` | `CharField(500)` | `null=True, blank=True` | Contact details |
| `join_date` | `DateField` | `default=timezone.now` | Date joined |
| `school_code` | `CharField(10)` | `default='HIS'` | Campus/branch code |
| `unique_code` | `CharField(50)` | `unique=True, db_index=True, editable=False` | Auto-generated: `{SchoolCode}S{JoinYear}-{Seq:05d}` (e.g. `HISS24-00001`) |
| `user` | `OneToOneField(User)` | `on_delete=SET_NULL, null=True, related_name='staff_profile'` | Linked Clerk-backed `User` account |

### 2.5 `people.Subject`
Global subject catalog shared across cohorts, courses, timetable slots, and ad-hoc tutoring sessions.

| Field | Type | Constraints / Defaults | Description |
| :--- | :--- | :--- | :--- |
| `id` | `BigAutoField` | PK | Subject ID |
| `name` | `CharField(255)` | `unique=True` | Subject title (e.g., `"Mathematics"`, `"Physics"`) |

### 2.6 `people.AuditLog`
Immutable append-only activity log powering `/api/v1/audit-logs/` and the `/overview` Recent Activity feed.

| Field | Type | Constraints / Defaults | Description |
| :--- | :--- | :--- | :--- |
| `id` | `BigAutoField` | PK | Log ID |
| `user` | `ForeignKey(User)` | `on_delete=SET_NULL, null=True, related_name='audit_logs'` | Actor who performed the operation |
| `user_email` | `CharField(255)` | `blank=True, default=''` | Snapshot of actor's email |
| `category` | `CharField(20)` | `db_index=True, default='other'` | `student`, `teacher`, `staff`, `class`, `session`, `check_in`, `user`, `other` |
| `summary` | `CharField(255)` | `blank=True` | Human-readable event summary for UI feeds |
| `model_name` | `CharField(255)` | `db_index=True` | Target model name |
| `record_id` | `CharField(255)` | `db_index=True` | Target primary key |
| `action` | `CharField(20)` | Choices: `create`, `update`, `delete` | Mutation verb |
| `field_name` | `CharField(255)` | `null=True, blank=True` | Specific changed field (when applicable) |
| `old_value` / `new_value` | `TextField` | `null=True, blank=True` | Before/after values |
| `timestamp` | `DateTimeField` | `auto_now_add=True, db_index=True` | Event timestamp |

- **Indexes:** `auditlog_model_record` (`['model_name', 'record_id']`), `auditlog_category_ts` (`['category', '-timestamp']`).

---

## 3. `timetable` App Models ([`timetable/models.py`](../timetable/models.py))

### 3.1 `timetable.Class` (Domain Alias: `Cohort`)
Represents an academic student cohort (e.g., `"IG K1"`, `"IAL A2"`, `"Year8 A"`).

| Field | Type | Constraints / Defaults | Description |
| :--- | :--- | :--- | :--- |
| `id` | `BigAutoField` | PK | Class / Cohort ID |
| `education_level` | `CharField(20)` | Choices: `IAL`, `IG`, `Year1` … `Year9` | Education tier |
| `cohort_identifier` | `CharField(1)` | Required (e.g. `'K'`, `'A'`) | Single-character cohort group |
| `cohort_sub_category` | `CharField(10)` | `null=True, blank=True` (e.g. `'1'`, `'2'`) | Sub-group identifier |

- **Constraints:** `UniqueConstraint(fields=['education_level', 'cohort_identifier', 'cohort_sub_category'], name='unique_class_per_level_cohort')`.
- **Computed Properties:** `full_cohort_identifier` returns `"{education_level} {cohort_identifier}{cohort_sub_category or ''}"` (e.g. `"IG K1"`).

### 3.2 `timetable.Course`
Links a `Subject` to a `Class` (Cohort) with an optional `default_teacher`.

| Field | Type | Constraints / Defaults | Description |
| :--- | :--- | :--- | :--- |
| `id` | `BigAutoField` | PK | Course ID |
| `class_obj` | `ForeignKey(Class)` | `on_delete=CASCADE, related_name='courses'` | Parent Cohort |
| `subject` | `ForeignKey(Subject)` | `on_delete=CASCADE, related_name='courses'` | Offered Subject |
| `default_teacher` | `ForeignKey(Teacher)` | `on_delete=SET_NULL, null=True, blank=True, related_name='courses'` | Default lead teacher |

- **Constraints & Indexes:** `UniqueConstraint(fields=['class_obj', 'subject'], name='unique_course_per_cohort_subject')`; index `idx_course_cohort_subj`.

### 3.3 `timetable.ClassStudent`
Primary cohort membership table. Enforces at the PostgreSQL constraint level that a student can belong to **at most one primary cohort**.

| Field | Type | Constraints / Defaults | Description |
| :--- | :--- | :--- | :--- |
| `id` | `BigAutoField` | PK | Enrollment row ID |
| `class_obj` | `ForeignKey(Class)` | `on_delete=CASCADE, related_name='class_students'` | Enrolled Cohort |
| `student` | `ForeignKey(Student)` | `on_delete=CASCADE, related_name='enrolled_classes'` | Enrolled Student |

- **Constraints:**
  - `unique_student_per_class` on `['class_obj', 'student']`
  - `unique_primary_cohort_per_student` on `['student']` (guarantees single primary cohort per student)

### 3.4 `timetable.StudentSubjectEnrollment` (Alias: `CourseEnrollment`)
Per-subject enrollment override supporting cross-cohort electives (`status='enrolled'`) or dropped cohort subjects (`status='dropped'`).

| Field | Type | Constraints / Defaults | Description |
| :--- | :--- | :--- | :--- |
| `id` | `BigAutoField` | PK | Enrollment ID |
| `student` | `ForeignKey(Student)` | `on_delete=CASCADE, related_name='cross_subject_enrollments'` | Student |
| `class_obj` | `ForeignKey(Class)` | `on_delete=CASCADE, related_name='cross_subject_enrollments'` | Target Cohort |
| `subject` | `ForeignKey(Subject)` | `on_delete=CASCADE, related_name='cross_student_enrollments'` | Target Subject |
| `course` | `ForeignKey(Course)` | `on_delete=CASCADE, null=True, blank=True, related_name='enrollments'` | Auto-synced `Course` link |
| `status` | `CharField(20)` | `default='enrolled'`, choices: `enrolled`, `dropped` | Enrollment state |

- **Constraints:** `UniqueConstraint(fields=['student', 'class_obj', 'subject'], name='unique_student_class_subject_enrollment')`.

### 3.5 `timetable.TimetableSlot`
Recurring weekly schedule template (Monday `0` through Sunday `6`) with flexible start/end times.

| Field | Type | Constraints / Defaults | Description |
| :--- | :--- | :--- | :--- |
| `id` | `BigAutoField` | PK | Slot ID |
| `class_obj` | `ForeignKey(Class)` | `on_delete=CASCADE, related_name='timetable_slots'` | Cohort |
| `subject` | `ForeignKey(Subject)` | `on_delete=CASCADE, related_name='timetable_slots'` | Subject |
| `course` | `ForeignKey(Course)` | `on_delete=CASCADE, null=True, blank=True, related_name='timetable_slots'` | Auto-created/linked `Course` |
| `teacher` | `ForeignKey(Teacher)` | `on_delete=CASCADE, related_name='timetable_slots'` | Assigned Teacher |
| `day_of_week` | `IntegerField` | Choices: `0` (Monday) … `6` (Sunday) | Day of week |
| `start_time` | `TimeField` | Required (`HH:MM:SS`) | Lesson start time |
| `end_time` | `TimeField` | Required (`end_time > start_time`) | Lesson end time |
| `room` | `CharField(100)` | `null=True, blank=True` | Optional classroom label |

- **Hooks:** `clean()` enforces `end_time > start_time`. `save()` automatically links or creates the matching `Course(class_obj, subject)`.

---

## 4. `class_sessions` App Models ([`class_sessions/models.py`](../class_sessions/models.py))

### 4.1 `class_sessions.Session`
Concrete dated lesson generated from a `TimetableSlot` (or created directly).

| Field | Type | Constraints / Defaults | Description |
| :--- | :--- | :--- | :--- |
| `id` | `BigAutoField` | PK | Session ID |
| `timetable_slot` | `ForeignKey(TimetableSlot)` | `on_delete=PROTECT, related_name='sessions'` | Source weekly slot |
| `class_obj` | `ForeignKey(Class)` | `on_delete=PROTECT, related_name='sessions'` | Cohort |
| `teacher` | `ForeignKey(Teacher)` | `on_delete=PROTECT, related_name='sessions'` | Assigned slot teacher |
| `actual_teacher` | `ForeignKey(Teacher)` | `on_delete=PROTECT, null=True, blank=True, related_name='sessions_taught'` | Substitute teacher (normalized to `None` if equal to `teacher`) |
| `start_time` | `DateTimeField` | Required (ISO-8601) | Concrete start datetime |
| `end_time` | `DateTimeField` | Required (`end_time > start_time`) | Concrete end datetime |
| `status` | `CharField(20)` | `default='scheduled'`, choices: `scheduled`, `completed`, `cancelled`, `no_show` | Session lifecycle status |

- **Constraints & Indexes:**
  - `UniqueConstraint(fields=['timetable_slot', 'start_time'], name='unique_session_per_slot_start')` (prevents duplicate session generation).
  - Indexes on `['class_obj', 'start_time']`, `['teacher', 'start_time']`, `['start_time']`, `['status']`.

### 4.2 `class_sessions.SessionAttendance`
Per-student lesson attendance row for a `Session`. Absence of a row represents **unmarked (`null`)**, not absent.

| Field | Type | Constraints / Defaults | Description |
| :--- | :--- | :--- | :--- |
| `id` | `BigAutoField` | PK | Attendance record ID |
| `session` | `ForeignKey(Session)` | `on_delete=CASCADE, related_name='attendances'` | Target Session |
| `student` | `ForeignKey(Student)` | `on_delete=CASCADE, related_name='attendances'` | Student |
| `status` | `CharField(20)` | `default='absent'`, choices: `present`, `absent`, `late`, `excused` | Roll status |
| `auto_marked_by_checkin` | `ForeignKey(CheckIn)` | `on_delete=SET_NULL, null=True, blank=True, editable=False` | Tracks if auto-marked by gate check-in |

- **Constraints:** `UniqueConstraint(fields=['session', 'student'], name='unique_attendance_per_session_student')`.

### 4.3 `class_sessions.AdHocSession` & `AdHocSessionAttendance`
Extra tutoring / non-timetable sessions and their student roll entries.

- **`AdHocSession` Fields:** `id`, `teacher` (`PROTECT`), `actual_teacher` (`PROTECT, null=True`), `subject` (`PROTECT`), `date` (`DateField, db_index=True`), `start_time` (`TimeField`), `end_time` (`TimeField`), `status` (`scheduled | completed | cancelled | no_show`).
  - Constraint: `UniqueConstraint(fields=['teacher', 'subject', 'date', 'start_time'], name='unique_adhoc_session_per_start')`.
- **`AdHocSessionAttendance` Fields:** `id`, `ad_hoc_session` (`CASCADE`), `student` (`CASCADE`), `status` (`present | absent | late | excused`), `auto_marked_by_checkin` (`SET_NULL, null=True`).
  - Constraint: `UniqueConstraint(fields=['ad_hoc_session', 'student'], name='unique_attendance_per_adhoc_session_student')`.

### 4.4 `class_sessions.CheckIn`
Daily campus arrival log recorded via QR terminal scan or staff manual roll.

| Field | Type | Constraints / Defaults | Description |
| :--- | :--- | :--- | :--- |
| `id` | `BigAutoField` | PK | Check-in ID |
| `student` | `ForeignKey(Student)` | `on_delete=CASCADE, related_name='check_ins'` | Arriving Student |
| `date` | `DateField` | `db_index=True` | Local calendar date of arrival |
| `timestamp` | `DateTimeField` | `auto_now_add=True` | Exact scan/manual commit timestamp |
| `check_in_type` | `CharField(10)` | `default='qr'`, choices: `qr`, `manual` | Arrival capture method |
| `checked_by` | `ForeignKey(User)` | `on_delete=SET_NULL, null=True, related_name='check_ins_performed'` | Terminal / staff operator |

- **Constraints:** `UniqueConstraint(fields=['student', 'date'], name='unique_student_daily_checkin')` (at most 1 campus check-in per student per calendar day).

---

## 5. `communications` App Models ([`communications/models.py`](../communications/models.py))

### 5.1 `communications.Tag`
Topic tags scoped to either `'announcement'` or `'event'`.
- **Fields:** `id`, `name` (`CharField(80)`), `slug` (`SlugField(100)`), `scope` (`'announcement' | 'event'`).
- **Constraints:** `unique_tag_name_per_scope` (`['name', 'scope']`), `unique_tag_slug_per_scope` (`['slug', 'scope']`).

### 5.2 `communications.Announcement`
Press-style markdown announcement posts.
- **Fields:** `id`, `title` (`CharField(255)`), `slug` (`SlugField(280), unique=True`), `body` (`TextField`), `status` (`'published' | 'archived'`), `is_featured` (`BooleanField`), `is_pinned` (`BooleanField`), `published_at` (`DateTimeField, null=True`), `author` (`FK User, SET_NULL`), `tags` (`M2M Tag`), `created_at`, `updated_at`.
- **Ordering:** `['-is_featured', '-is_pinned', '-published_at', '-created_at']`.

### 5.3 `communications.Event` & `EventRegistration`
School events with capacity/waitlist management and user registrations.
- **`Event` Fields:** `id`, `title`, `slug` (`unique=True`, auto-8-char alphanumeric suffix), `summary` (`CharField(500)`), `body` (`TextField`), `audience` (`'internal' | 'external'`), `registration_mode` (`'instant_waitlist' | 'approval_required'`), `status` (`'published' | 'closed' | 'cancelled'`), `starts_at` (`DateTimeField`), `ends_at` (`DateTimeField, null=True`), `location` (`CharField(255)`), `registration_opens_at`, `registration_closes_at`, `capacity` (`PositiveIntegerField, null=True`), `cover_image_url` (`URLField`), `created_by` (`FK User`), `tags` (`M2M Tag`), `created_at`, `updated_at`.
- **`EventRegistration` Fields:** `id`, `event` (`FK Event, CASCADE`), `user` (`FK User, CASCADE`), `status` (`'confirmed' | 'waitlisted' | 'pending' | 'cancelled'`), `staff_note` (`TextField`), `registered_at` (`auto_now_add`), `reviewed_at` (`DateTimeField, null=True`), `reviewed_by` (`FK User, SET_NULL`).
  - Constraint: `UniqueConstraint(fields=['event', 'user'], name='unique_event_registration_per_user')`.

---

## 6. Upcoming Next-Pass Models (`academics` & `payroll`)

> [!NOTE]
> **Roadmap Status:** All core operations above (`people`, `timetable`, `class_sessions`, `communications`) are **100% live in both backend and frontend**. The two domains below (`academics` Exam Tracking and `payroll` Teacher/Staff Payroll & Student Fee Payments) have backend models scaffolded and are scheduled for the next frontend/product pass.

### 6.1 Exam Tracking & Report Cards (`academics` App — [`academics/models.py`](../academics/models.py))
- **`academics.AcademicYear`:** `name` (`unique`), `start_date`, `end_date` (`end_date > start_date`). Auto-provisions Semesters 1 and 2 (`Term`) inside an atomic transaction on `save()`.
- **`academics.Term`:** `academic_year` (`PROTECT`), `number` (`1 = Semester 1`, `2 = Semester 2`).
- **`academics.SubjectOffering`:** `class_obj` (`PROTECT`), `subject` (`PROTECT`), `term` (`PROTECT`), `exam_weight`, `quiz_weight`, `assignment_weight` (PostgreSQL `CheckConstraint` enforces weights sum to `100.00`).
- **`academics.Assessment`:** `offering` (`PROTECT`), `title`, `kind` (`'exam' | 'quiz' | 'assignment'`), `max_marks` (`> 0`). Immutable `kind` and `max_marks` once results exist.
- **`academics.AssessmentResult`:** `assessment` (`PROTECT`), `student` (`PROTECT`), `marks` (`0 <= marks <= max_marks`), `remarks`, `recorded_by` (`FK User`), `updated_at`. Validates student cohort enrollment on `clean()`.
- **`academics.ReportCard`:** `student` (`PROTECT`), `class_obj` (`PROTECT`), `term` (`PROTECT`), `revision` (`>= 1`), `comments`, `snapshot` (`JSONField`), `created_by`, `created_at`, `published_at`, `published_by`. Immutable once `published_at` is set.

### 6.2 Payroll & Student Fee Payments (`payroll` App — [`payroll/models.py`](../payroll/models.py))
- **`payroll.StudentFee`:** `student` (`FK Student`), `academic_year` (`FK AcademicYear`), `fee_type` (`'tuition' | 'library' | 'transport' | 'exam' | 'other'`), `amount_due`, `due_date`, `status` (`'pending' | 'partial' | 'paid' | 'overdue'`).
- **`payroll.FeePayment`:** `student_fee` (`FK StudentFee`), `amount_paid` (`> 0`, cannot exceed remaining balance), `payment_date`, `payment_method` (`'cash' | 'bank_transfer' | 'mobile_money'`), `reference_number`.
- **`payroll.StaffSalary`:** `staff` (`FK Staff`), `month` (normalized to 1st of month; unique per staff+month), `base_salary`, `allowances`, `deductions`, `net_salary` (`base + allowances - deductions >= 0`), `status` (`'pending' | 'paid'`), `payment_date`.
