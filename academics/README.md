# Phase 1: academics for Hinthar SMS

## Seed dummy students for IG K3

Run `python manage.py seed_ig_k3_students` to create 30 dummy student profiles
and enroll them in IG K3, creating the class if necessary. The command uses the
configured Django database (`DATABASE_URL` for PostgreSQL). It creates no login
accounts and makes no authentication service calls.

Students have realistic names, teenage birth dates, reserved `example.com`
contact addresses, school code `HIS`, dummy candidate numbers, and unique
check-in tokens. Codes `DUMMY-IGK3-001` through `DUMMY-IGK3-030` identify this
seed set. Repeated runs preserve existing profiles and restore any missing
enrollments without adding duplicates. All inserts share one transaction.

## Source and verification

The GitHub integration returned 404 for `HintharProject/school-management-system-api-prod`
and its `people/models.py`; the repository was absent from accessible-repository search.
This package is therefore based on the uploaded backend, NOT a verified current GitHub
commit. The newly attached `class_sessions(1).zip` and `components(1).zip` are identical
to the archives previously inspected. Grant the GitHub connection access to the exact
repository (or correct the repository name) for a current-revision comparison.

No remote repository, branch, or user database was changed. The supplied implementation
was checked in an isolated copy of the uploaded backend with Django 5.1.15, DRF 3.17.2,
and SQLite. Django system checks and all 18 included tests passed. Test database creation
applied the migration graph. Live Clerk sign-in and PostgreSQL concurrency were not tested.

## Existing architecture and authentication

- `people.models.Student` is the existing student entity. Its optional `user` OneToOne
  links to the custom `people.User`, whose `student_profile` reverse relation is used for
  ownership checks. Students do not need accounts for staff to enter grades.
- `people.models.Subject` is reused.
- `Class` and `ClassStudent` live in **timetable**, not people. The new app references
  them without adding fields or changing their existing relationships.
- `people.authentication.ClerkJWTAuthentication` authenticates Bearer tokens using Clerk
  JWKS, RS256, issuer and configured audience. Django owns roles; Clerk claims do not
  grant academic permissions. Newly provisioned users begin as pending.
- Inactive accounts can authenticate for the existing `/me/` lock-screen flow; academic
  permissions nevertheless reject them. Do not change that authentication behavior.
- `people.clerk_backend` is the server-side Clerk management client; academic requests
  do not need to call it or use the Clerk secret key from the frontend.
- Existing global authentication and pagination are inherited. Do not add JWT packages,
  new login endpoints, session authentication, or `AllowAny` permissions for this app.
- Reuse `AuditedViewSetMixin` and the existing audit table for changes. The `other`
  category avoids modifying `people` model choices in this phase.

## 1. Initialize the app locally

In your activated backend virtual environment, from the folder containing `manage.py`:

```bash
git switch feature/academic-and-payroll
python manage.py startapp academics
```

If that branch exists only locally, that is fine; nothing needs to be pushed. If the app
already exists, skip `startapp` and compare its files before replacing them.

Copy the complete contents of these files from this package:

- `academics/models.py`
- `academics/serializers.py`
- `academics/views.py`
- `academics/urls.py`

Keep the generated `academics/apps.py`, `__init__.py`, and `migrations/__init__.py`.
Equivalent copies are included. Copy the supplied `academics/tests.py` to run the tests.
No additional application file, service module, signal handler, or third-party dependency
is required by the four implementation files.

## 2. Register the app

Inside the existing `INSTALLED_APPS` list in `config/settings.py`, add:

```python
    'academics.apps.AcademicsConfig',
```

Leave `AUTH_USER_MODEL`, `REST_FRAMEWORK`, Clerk settings, and database configuration
unchanged. Confirm your existing `.env` points at your local database; settings use
`DATABASE_URL` or fall back to `BASE_DIR / 'db.sqlite3'`.

## 3. Register the URLs

In `config/urls.py`, inside the existing `path('api/v1/', include([...]))` list, add:

```python
        path('', include('academics.urls')),
```

The relevant block becomes:

```python
    path('api/v1/', include([
        path('', include('people.urls')),
        path('', include('timetable.urls')),
        path('', include('class_sessions.urls')),
        path('', include('communications.urls')),
        path('', include('academics.urls')),
        # path('', include('payroll.urls')),  # remains archived
    ])),
```

`path` and `include` are already imported. Do not add another `api/v1/` prefix to
`academics/urls.py` or replace your existing project routes.

## 4. Create and apply LOCAL migrations

First check the configured connection without printing credentials:

```bash
python manage.py shell -c "from django.conf import settings; d=settings.DATABASES['default']; print({k:d.get(k) for k in ('ENGINE','NAME','HOST','PORT')})"
python manage.py check
python manage.py makemigrations academics --dry-run --verbosity 3
```

After reviewing the preview, generate the migration and inspect its plan:

```bash
python manage.py makemigrations academics
python manage.py migrate --plan
```

Then apply to your confirmed local database and run the tests:

```bash
python manage.py migrate
python manage.py test academics
python manage.py runserver
```

This package intentionally does not include a generated `0001_initial.py`: your local
checkout must generate dependencies against its own current migration graph.

**Existing migration drift in the uploaded backend:** the historical migration state
includes `people_audi_model_n_95b171_idx`, but current `AuditLog.Meta.indexes` omits it.
During verification, Django also proposed
`people/0016_remove_auditlog_people_audi_model_n_95b171_idx.py`, and the new academic
migration depended on it. That index cleanup is unrelated to academics. Check whether
your local checkout already resolves this difference; review any proposed `people`
migration separately before applying. Do not delete, fake, or rewrite applied migrations.

## Business rules implemented

### Calendar and relationships

An AcademicYear stores its name and date range. Creating it through the API or ordinary
model `save()` creates Semester 1 and Semester 2 in the same transaction. The term API
is read-only, and database constraints reject duplicates and semester numbers other
than 1 or 2. Semester-specific date boundaries are not assumed.

SubjectOffering connects an existing Class, Subject, and Term and stores the three
category weights. There is one offering per class/subject/term.

### Weights and calculation

All three weights must be explicitly supplied. They are percentages, between 0 and 100,
with up to two decimal places, and must sum to 100. There is no assumed institutional
split. For example, exams 60%, quizzes 20%, assignments 20% is valid.

Within a category, use total earned points / total possible points. Thus a 100-point
exam contributes more within its category than a 10-point exam. The subject result is:

`sum(category_percentage * category_weight / 100)`.

A category with positive weight needs at least one assessment and a result for every
assessment before a report can be generated. A zero-weight category does not contribute
and does not require marks. Missing marks are not silently zero; an explicitly entered
zero is valid. Absence/exemption and resit policies are not invented in this release.

Round the final subject percentage HALF_UP to two decimals, then assign the grade:

| Grade | Percentage |
|---|---|
| A | 80.00 through 100.00 |
| B | 70.00 up to, but not including, 80.00 |
| C | 60.00 up to, but not including, 70.00 |
| D | 50.00 up to, but not including, 60.00 |
| F | Below 50.00 |

Consequently a raw 79.995 rounds to 80.00 and becomes A. This explicitly closes the
decimal gaps in shorthand bands such as "70-79". No GPA or cross-subject aggregate is
assumed without a credit/weight policy.

### Reports and history

Reports are JSON snapshots, with a subject list, source marks/maxima, category weights,
percentages, grades, names, and calculation rules. PDF rendering and frontend pages are
not included in this phase.

POST a report to generate a staff-only draft. POST its `publish/` action to recalculate
from the latest marks and publish it. Publishing an already published report is
idempotent: it returns the saved snapshot. A newer published revision blocks publication
of an older draft. Each subsequent POST for the same student/class/term creates the
next draft revision; all previously published revisions remain available.

Published reports cannot be modified through model `save()` or the API. Later changes
to marks, weights, or names do not alter them. The API provides no DELETE endpoints.
Database administrators and direct `QuerySet.update()`/bulk SQL can bypass model
validation: use the academic API for normal writes. Foreign keys use PROTECT for
retained people/class/subject relationships.

New marks require current ClassStudent membership. Report corrections can be generated
for a previously reported class/term after a transfer. Existing marks can be corrected
after a transfer, but new historical assessment results require a future enrollment
history policy. This phase does not invent historical enrollment dates or edit the
existing ClassStudent schema.

### Access

| Account | Access |
|---|---|
| Active staff/admin | Academic setup, grades, report creation and publication |
| Active linked student | Only own published report list/detail |
| Teacher | No new academic access in this Phase 1 |
| Terminal/pending/inactive/anonymous | No academic access |

Teacher grade entry needs an explicit class/subject assignment policy and can be added
later. Students cannot read school-wide marks, drafts, or another student's report by
changing an ID or filter. Clients cannot set recorded_by, published_by, snapshot, revision,
or publication timestamps. Authentication still uses the existing Clerk Bearer token.

Academic API writes and report publication take a term lock on PostgreSQL. SQLite has
no equivalent `select_for_update` row locking; the verification here is single-process
functional testing, not proof of PostgreSQL concurrency behavior.

## API quick start

All paths below are relative to `/api/v1/`; send your existing Clerk token as
`Authorization: Bearer <token>` and `Content-Type: application/json`.

IDs below are illustrative. Substitute the IDs returned by your local API.

1. POST `/academic-years/`:

```json
{"name":"2026-2027","start_date":"2026-06-01","end_date":"2027-05-31"}
```

The response contains the two terms and their IDs. You can also GET `/terms/?academic_year_id=1`.

2. POST `/subject-offerings/` using existing Class and Subject IDs:

```json
{"class_obj":1,"subject":1,"term":1,"exam_weight":"60.00","quiz_weight":"20.00","assignment_weight":"20.00"}
```

3. POST `/assessments/` for each needed exam, quiz, and assignment:

```json
{"offering":1,"title":"Midterm exam","kind":"exam","max_marks":"100.00"}
```

Valid kinds: `exam`, `quiz`, `assignment`.

4. POST `/assessment-results/` for each student/assessment:

```json
{"assessment":1,"student":1,"marks":"82.50","remarks":"Good progress"}
```

PATCH `/assessment-results/{id}/` to correct marks. Marks must be 0 through max_marks;
student + assessment must be unique. Assessment kind and max_marks are fixed once
results exist. Student/assessment identity on a result cannot be reassigned.

5. Once all positive-weight categories have assessments and complete marks, POST `/report-cards/`:

```json
{"student":1,"class_obj":1,"term":1,"comments":"Steady progress this semester."}
```

6. POST `/report-cards/{returned_id}/publish/` with `{}`.

7. GET `/report-cards/{id}/` or `/report-cards/?student_id=1&term_id=1`.

All list routes use existing pagination (`count`, `next`, `previous`, `results`), default
50 rows and maximum 200 per page. Foreign key filters must be positive integers.

| Resource | Methods | Filters |
|---|---|---|
| academic-years | GET/POST; detail GET | none |
| terms | GET only | academic_year_id |
| subject-offerings | GET/POST; detail GET/PUT/PATCH | class_id, subject_id, term_id |
| assessments | GET/POST; detail GET/PUT/PATCH | offering_id, term_id, class_id |
| assessment-results | GET/POST; detail GET/PUT/PATCH | student_id, assessment_id, term_id, class_id |
| report-cards | GET/POST; detail GET; publish POST | student_id, class_id, term_id |

Validation failures use HTTP 400; a database uniqueness/concurrent-write conflict uses
HTTP 409. Unauthorized student detail requests return 404 through the scoped queryset.

## Complete implementation files

The four requested Python files are included in `academics/` without placeholders.
The tests are optional to install but recommended to run before committing your local work.

Technical references checked while preparing the implementation:
- https://docs.djangoproject.com/en/5.1/ref/models/constraints/
- https://www.django-rest-framework.org/api-guide/serializers/
- https://www.django-rest-framework.org/api-guide/permissions/
