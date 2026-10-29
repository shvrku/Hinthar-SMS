# Phase 2 payroll and fees

Copy the five files in payroll/ into your existing Django payroll app. Keep existing
apps.py, __init__.py, and migration history. If the app does not exist, first run:

    python manage.py startapp payroll

Ensure INSTALLED_APPS contains payroll.apps.PayrollConfig exactly once. Inside the
existing /api/v1/ include list in config/urls.py add:

    path('', include('payroll.urls')),

Then run locally:

    python manage.py makemigrations payroll
    python manage.py migrate --plan
    python manage.py migrate
    python manage.py test payroll

Rules: status values use lowercase API codes. Fully paid fees are paid; otherwise
past-due fees are overdue, including partially paid past-due fees. Zero-amount fees
are paid. Overpayments and nonpositive payments are rejected. Salary months are
normalized to the first day; one salary per staff/month. Paid salaries require a
payment date; pending salaries require an empty date. Net salaries cannot be negative.

Authentication is inherited. Access requires an active admin role or superuser; for
a standard Django user without a role field, is_staff grants access. This does not
allow students or all employees to browse salary records.

The API calculates current fee status during reads/filtering so overnight overdue
transitions work without writes on GET. The stored status column is synchronized by
normal fee/payment save and payment instance delete. Other code needing current
status should use current_status, with_payment_status(), or refresh_status().
Use instance save/delete, not bulk_create, bulk_update, QuerySet.update/delete, or
raw SQL for payment changes: those bypass model hooks. These CRUD endpoints record
payments; they do not initiate transfers, provide refund workflows, or deduplicate
retries using idempotency keys.

External test fixtures assume Student(name), Staff(name), and
AcademicYear(name, start_date, end_date). Adjust fixture constructors if yours differ.

Verified using Django 5.1.15, DRF 3.17.2, and isolated SQLite: 19 API tests pass.
PostgreSQL concurrency and live Clerk authentication were not tested. SQLite does
not provide select_for_update row locking.
