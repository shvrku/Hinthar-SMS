"""Seed a repeatable set of dummy students without creating login accounts."""

import secrets
from datetime import date

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from people.models import Student
from timetable.models import Class, ClassStudent


STUDENT_NAMES = (
    "Aung Min Khant", "Thiri Htet", "Kaung Myat Thu", "May Thazin",
    "Hein Htet Aung", "Su Myat Noe", "Min Khant Kyaw", "Ei Shwe Sin",
    "Zaw Htet Paing", "Phyu Sin Thant", "Nay Lin Htet", "Khin Yadanar",
    "Thet Paing Soe", "Wint Yati", "Ye Min Oo", "Hnin Pwint Phyu",
    "Sithu Aung", "May Myat Mon", "Htet Wai Yan", "Shwe Yee Win",
    "Pyae Phyo Aung", "Yoon Wadi", "Kyaw Zin Thant", "Thazin Nwe",
    "Phone Myat Min", "Nan Su Yati", "Arkar Hein", "Mya Thiri",
    "Thu Rain Aung", "Ei Mon Kyaw",
)


class Command(BaseCommand):
    help = "Bulk create 30 dummy students and enroll them in IG K3 (safe to rerun)."

    def handle(self, *args, **options):
        today = timezone.localdate()
        codes = [f"DUMMY-IGK3-{index:03d}" for index in range(1, 31)]

        with transaction.atomic():
            class_obj, _ = Class.objects.get_or_create(
                education_level="IG",
                cohort_identifier="K",
                cohort_sub_category="3",
            )
            # Serialize concurrent runs of this seed command for the same class.
            class_obj = Class.objects.select_for_update().get(pk=class_obj.pk)
            existing = Student.objects.in_bulk(codes, field_name="unique_code")
            students = []
            for index, (name, code) in enumerate(zip(STUDENT_NAMES, codes), start=1):
                if code in existing:
                    continue
                student = Student(
                    name=name,
                    dob=date(today.year - 15 - index % 2, (index - 1) % 12 + 1,
                             (index * 7 - 1) % 28 + 1),
                    contact=f"{name.lower().replace(' ', '.')}@example.com",
                    school_code="HIS",
                    unique_code=code,
                    exam_candidate_number=f"DUMMY-IGK3-C{index:03d}",
                    # bulk_create bypasses Student.save(), so supply both codes
                    # and tokens explicitly. enrollment_date is auto-populated.
                    check_in_token=secrets.token_urlsafe(32),
                    check_in_token_active=True,
                    user=None,
                )
                student.full_clean(exclude=["enrollment_date"])
                students.append(student)

            Student.objects.bulk_create(students)
            seeded_students = Student.objects.filter(unique_code__in=codes)
            enrolled_ids = set(ClassStudent.objects.filter(
                class_obj=class_obj, student__in=seeded_students,
            ).values_list("student_id", flat=True))
            enrollments = [
                ClassStudent(class_obj=class_obj, student=student)
                for student in seeded_students if student.pk not in enrolled_ids
            ]
            ClassStudent.objects.bulk_create(enrollments)

        self.stdout.write(self.style.SUCCESS(
            f"Created {len(students)} dummy students and {len(enrollments)} "
            f"enrollments. All 30 dummy students are assigned to {class_obj}."
        ))
