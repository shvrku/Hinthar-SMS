# School Management System — Full Project Summary
 
**Scope:** Core system covering people, class structure, timetabling, session/attendance tracking, and teacher payroll.
*(Academic records / exams / report cards intentionally excluded from this build — future module.)*
 
---
 
## 1. Database Structure (Full Model)
 
### People
```
TEACHERS
- teacher_id PK
- name
- employment_type      -- full_time / tutor
- default_rate
- contact
- bank_details
 
STUDENTS
- student_id PK
- name
- dob
- enrollment_date
- contact
 
SUBJECTS
- subject_id PK
- name
```
 
### Class Structure
```
CLASSES
- class_id PK
- education_level        -- enum: IAL, IG, Year1, Year2, ... Year9
- cohort_identifier       -- single letter, e.g. E / F / G / H / K
- cohort_sub_category     -- nullable, e.g. 1 / 2 / 3 (stream split due to timetable clashes)
  -- unique constraint on (education_level, cohort_identifier, cohort_sub_category)
  -- display name (e.g. "IAL E", "IG K3") is computed, not stored
 
CLASS_STUDENTS   -- join table
- class_id FK
- student_id FK
```
 
### Timetable (recurring template)
```
TIMETABLE_SLOTS
- timetable_id PK
- class_id FK
- subject_id FK
- teacher_id FK
- day_of_week
- start_time
- end_time
- room
 
TIMETABLE_STUDENTS   -- used only for 1-on-1 tutor slots with no full class
- timetable_id FK
- student_id FK
```
 
### Sessions (actual dated occurrences)
```
SESSIONS
- session_id PK
- timetable_id FK   -- nullable, allows ad-hoc/makeup sessions
- teacher_id FK
- class_id FK        -- nullable, null for tutor sessions
- session_date
- status              -- scheduled / completed / cancelled / no_show
- paid                -- boolean lock flag, prevents payroll double-counting
- payslip_id FK       -- nullable, soft reference for traceability only
 
SESSION_ATTENDANCE
- session_id FK
- student_id FK
- status              -- present / absent / late
```
 
### Payroll
```
PAY_PERIODS
- pay_period_id PK
- start_date
- end_date
 
PAYSLIPS   -- frozen snapshot, values copied in at generation, never recalculated
- payslip_id PK
- teacher_id FK
- pay_period_id FK
- session_count
- rate_applied
- gross_pay
- tax_deduction
- other_deductions
- adjustments_total
- net_pay
- status               -- draft / approved / paid
- issued_date
 
ADJUSTMENTS   -- corrections, never edit locked payslips/sessions directly
- adjustment_id PK
- teacher_id FK
- session_id FK        -- nullable
- reason
- amount               -- signed +/-
- status               -- pending / applied
- created_date
- applied_payslip_id FK -- nullable, set once absorbed into a payslip
```
 
**Key design decisions:**
- Timetable (template) and Sessions (actual dated occurrences) are separate — allows cancellations/substitutions without corrupting the recurring schedule.
- One unified `SESSIONS` table for both class sessions and 1-on-1 tutoring (nullable `class_id`); tutor rosters come from `SESSION_ATTENDANCE`.
- Payroll is decoupled from sessions structurally — a `paid` lock flag prevents double-counting instead of a rigid FK.
- Payslips are frozen snapshots; corrections happen via `ADJUSTMENTS`, never by editing locked records.
- Payroll generation always follows preview (read-only) → confirm (atomic lock) to catch counting errors before they're permanent.
---
 
## 2. Data Flow Diagrams
 
**Level 0 (Context):** One process (Django API system), three external entities (Admin, Teacher, Student), one external Auth Provider, one consolidated data store.
 
**Level 1 (Exploded):**
 
| Process | Data Store | Responsibility |
|---|---|---|
| 1.0 Manage Timetable | D2 Timetable | Recurring slot definitions, pivoted views |
| 2.0 Record Sessions & Attendance | D3 Sessions & Attendance | Generate dated sessions, mark status, record attendance |
| 4.0 Process Payroll | D5 Payroll | Preview, confirm, lock, adjustments |
| 5.0 Authenticate & Authorize | D1 People | Token validation, role mapping |
 
*(3.0 reserved for future academic records module.)*
 
---
 
## 3. Tech Stack
 
| Layer | Choice | Reason |
|---|---|---|
| Backend/API | Django + Django REST Framework | Free admin panel, mature built-in permissions, strong fit for CRUD+permission-heavy internal tools |
| Database | PostgreSQL, hosted on Neon | Managed but portable (standard Postgres, `pg_dump` anywhere); supports Row-Level Security |
| Auth | Clerk (OIDC-based) | Handles login, MFA, session management outside app code |
| Frontend | Any framework, consumes the API only | Decoupled — teammates build/rebuild UI without touching backend, no merge-conflict risk |
| Frontend hosting | Vercel | Good fit for the frontend specifically |
| Backend hosting | Docker container on self-managed host | Django needs a long-running process — not a fit for Vercel serverless (timeouts, no background workers) |
 
---
 
## 4. Auth Flow Summary
 
1. Frontend redirects to Clerk for login — Django is not involved in login itself.
2. Frontend receives a short-lived access token (JWT) + refresh token.
3. Every API call sends `Authorization: Bearer <token>`.
4. Django verifies the JWT signature locally against Clerk's public JWKS endpoint.
5. Role claims map to Django groups/permissions on first login (JIT provisioning via `GET /api/v1/me`).
6. Refresh happens silently in the background; revoking a user in Clerk kills their access immediately.
---
 
## 5. Implementation Plan (Phased)
 
### Phase 1 — Project Structuring & Foundation
- Initialize Django project with separate apps: `people`, `timetable`, `sessions`, `payroll`
- Set up DRF, `.env` config, API versioning (`/api/v1/`), `drf-spectacular` docs
- Connect to Neon Postgres, confirm via initial migration
- Build Clerk JWT verification (`authentication.py`), `GET /api/v1/me`, core permission classes (`IsAdmin`, `IsOwnerTeacher`, `IsOwnerStudent`)
- **Build this phase directly — it's the security foundation everything else depends on**
### Phase 2 — Core Models & Class Structure
- Implement all models above
- CRUD for `TEACHERS`, `STUDENTS`, `SUBJECTS`, `CLASSES`, `CLASS_STUDENTS` — admin-only writes
### Phase 3 — Timetable
- `POST /api/v1/timetable-slots/` — admin defines recurring slots
- `GET /api/v1/timetable/teacher/{id}` and `/timetable/class/{id}` — pivoted grid views
- Overlap validation: reject double-booked teacher/room at write time
### Phase 4 — Sessions & Attendance
- `POST /api/v1/sessions/generate` — idempotent batch generation from timetable slots (unique constraint on `timetable_id` + `session_date`)
- `GET /api/v1/sessions/?teacher_id=&date_from=&date_to=`
- `PATCH /api/v1/sessions/{id}/status` — teacher-owned only
- `POST /api/v1/sessions/{id}/attendance` — bulk, pre-populated roster
- Highest write-volume module — index `session_id`, `teacher_id`
### Phase 5 — Payroll
- `GET /api/v1/payslips/preview?teacher_id=&pay_period_id=`
- `POST /api/v1/payslips/confirm` — atomic transaction, `select_for_update()` lock
- `POST /api/v1/adjustments/`
- `GET /api/v1/payslips/{id}`
- **Test priority:** concurrent `confirm` calls for same teacher/period — verify lock prevents double-payment
### Phase 6 — Audit Layer *(build alongside Phase 5, not after)*
- `post_save` signal on `Payslip` and `Session.status`/`paid` changes → `AuditLog` table
---
 
## 6. Deferred / Future Module
 
**Academic records (exams, results, report cards)** — excluded from this build. Slots in later as Process 3.0 and a `D4 Academic Records` store without disrupting current structure.