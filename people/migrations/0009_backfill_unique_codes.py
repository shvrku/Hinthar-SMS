from django.db import migrations
from django.utils import timezone


def backfill_unique_codes(apps, schema_editor):
    Student = apps.get_model('people', 'Student')
    Teacher = apps.get_model('people', 'Teacher')
    Staff = apps.get_model('people', 'Staff')

    # 1. Backfill Students
    student_cohorts = {}
    for student in Student.objects.filter(unique_code__isnull=True).order_by('enrollment_date', 'id'):
        school_code = (student.school_code or 'HIS').upper()
        if student.enrollment_date:
            year = student.enrollment_date.year
        elif student.user and student.user.date_joined:
            year = student.user.date_joined.year
        else:
            year = timezone.now().year

        year_str = f"{year % 100:02d}"
        prefix = f"{school_code}{year_str}-"

        if prefix not in student_cohorts:
            # Find max existing sequence if any
            existing = Student.objects.filter(unique_code__startswith=prefix).values_list('unique_code', flat=True)
            max_seq = 0
            for code in existing:
                if code and '-' in code:
                    suffix = code.rsplit('-', 1)[-1]
                    if suffix.isdigit():
                        max_seq = max(max_seq, int(suffix))
            student_cohorts[prefix] = max_seq

        student_cohorts[prefix] += 1
        seq_num = student_cohorts[prefix]
        student.unique_code = f"{prefix}{seq_num:05d}"
        student.save(update_fields=['unique_code'])

    # 2. Backfill Teachers
    teacher_cohorts = {}
    for teacher in Teacher.objects.filter(unique_code__isnull=True).order_by('id'):
        school_code = (teacher.school_code or 'HIS').upper()
        if teacher.user and teacher.user.date_joined:
            year = teacher.user.date_joined.year
        elif teacher.join_date:
            year = teacher.join_date.year
        else:
            year = timezone.now().year

        year_str = f"{year % 100:02d}"
        prefix = f"{school_code}T{year_str}-"

        if prefix not in teacher_cohorts:
            existing = Teacher.objects.filter(unique_code__startswith=prefix).values_list('unique_code', flat=True)
            max_seq = 0
            for code in existing:
                if code and '-' in code:
                    suffix = code.rsplit('-', 1)[-1]
                    if suffix.isdigit():
                        max_seq = max(max_seq, int(suffix))
            teacher_cohorts[prefix] = max_seq

        teacher_cohorts[prefix] += 1
        seq_num = teacher_cohorts[prefix]
        teacher.unique_code = f"{prefix}{seq_num:05d}"
        teacher.save(update_fields=['unique_code'])

    # 3. Backfill Staff
    staff_cohorts = {}
    for staff in Staff.objects.filter(unique_code__isnull=True).order_by('id'):
        school_code = (staff.school_code or 'HIS').upper()
        if staff.user and staff.user.date_joined:
            year = staff.user.date_joined.year
        elif staff.join_date:
            year = staff.join_date.year
        else:
            year = timezone.now().year

        year_str = f"{year % 100:02d}"
        prefix = f"{school_code}S{year_str}-"

        if prefix not in staff_cohorts:
            existing = Staff.objects.filter(unique_code__startswith=prefix).values_list('unique_code', flat=True)
            max_seq = 0
            for code in existing:
                if code and '-' in code:
                    suffix = code.rsplit('-', 1)[-1]
                    if suffix.isdigit():
                        max_seq = max(max_seq, int(suffix))
            staff_cohorts[prefix] = max_seq

        staff_cohorts[prefix] += 1
        seq_num = staff_cohorts[prefix]
        staff.unique_code = f"{prefix}{seq_num:05d}"
        staff.save(update_fields=['unique_code'])

    # 4. Verify backfill complete
    unfilled_students = Student.objects.filter(unique_code__isnull=True).count()
    unfilled_teachers = Teacher.objects.filter(unique_code__isnull=True).count()
    unfilled_staff = Staff.objects.filter(unique_code__isnull=True).count()

    if unfilled_students > 0 or unfilled_teachers > 0 or unfilled_staff > 0:
        raise RuntimeError(
            f"Backfill incomplete! Students: {unfilled_students}, Teachers: {unfilled_teachers}, Staff: {unfilled_staff}"
        )


def reverse_backfill(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('people', '0008_add_unique_code_fields'),
    ]

    operations = [
        migrations.RunPython(backfill_unique_codes, reverse_code=reverse_backfill),
    ]
