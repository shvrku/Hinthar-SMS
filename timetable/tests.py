from datetime import datetime, time

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase, APIClient

from class_sessions.models import Session, SessionAttendance
from people.models import Student, Subject, Teacher
from timetable.models import Class, ClassStudent, TimetableSlot

User = get_user_model()


class ClassAttendanceSummaryTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username="class_summary_admin", role="admin", clerk_id="clerk_class_sum_1"
        )
        self.class_obj = Class.objects.create(education_level="IG", cohort_identifier="A")
        self.teacher = Teacher.objects.create(name="Class Summary Teacher")
        self.subject = Subject.objects.create(name="Class Summary Math")
        self.student = Student.objects.create(name="Class Summary Student")
        ClassStudent.objects.create(class_obj=self.class_obj, student=self.student)
        self.slot = TimetableSlot.objects.create(
            class_obj=self.class_obj,
            subject=self.subject,
            teacher=self.teacher,
            day_of_week=0,
            start_time="09:00",
            end_time="10:00",
        )
        today = timezone.localdate()
        self.session = Session.objects.create(
            timetable_slot=self.slot,
            teacher=self.teacher,
            class_obj=self.class_obj,
            start_time=timezone.make_aware(datetime.combine(today, time(9, 0))),
            end_time=timezone.make_aware(datetime.combine(today, time(10, 0))),
            status="completed",
        )
        SessionAttendance.objects.create(
            session=self.session, student=self.student, status="present"
        )

    def test_requires_valid_range(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.get(f"/api/v1/classes/{self.class_obj.id}/attendance-summary/")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        res = self.client.get(
            f"/api/v1/classes/{self.class_obj.id}/attendance-summary/?range=decade"
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_summary_separates_campus_and_lesson(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.get(
            f"/api/v1/classes/{self.class_obj.id}/attendance-summary/?range=month"
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("campus", res.data)
        self.assertIn("lesson", res.data)
        self.assertEqual(res.data["lesson"]["present"], 1)
        self.assertEqual(res.data["campus"]["enrolled_students"], 1)


class TeacherAttendanceSummaryTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username="teacher_summary_admin", role="admin", clerk_id="clerk_teacher_sum_1"
        )
        self.class_obj = Class.objects.create(education_level="IG", cohort_identifier="B")
        self.assigned = Teacher.objects.create(name="Assigned Teacher")
        self.cover = Teacher.objects.create(name="Cover Teacher")
        self.subject = Subject.objects.create(name="Teacher Summary Science")
        self.student = Student.objects.create(name="Teacher Summary Student")
        ClassStudent.objects.create(class_obj=self.class_obj, student=self.student)
        self.slot = TimetableSlot.objects.create(
            class_obj=self.class_obj,
            subject=self.subject,
            teacher=self.assigned,
            day_of_week=1,
            start_time="11:00",
            end_time="12:00",
        )
        today = timezone.localdate()
        self.session = Session.objects.create(
            timetable_slot=self.slot,
            teacher=self.assigned,
            actual_teacher=self.cover,
            class_obj=self.class_obj,
            start_time=timezone.make_aware(datetime.combine(today, time(11, 0))),
            end_time=timezone.make_aware(datetime.combine(today, time(12, 0))),
            status="completed",
        )
        SessionAttendance.objects.create(
            session=self.session, student=self.student, status="late"
        )

    def test_same_teacher_actual_normalized_to_null(self):
        self.session.actual_teacher = self.assigned
        self.session.save()
        self.session.refresh_from_db()
        self.assertIsNone(self.session.actual_teacher_id)

    def test_assigned_personal_covered_and_cover_accountability(self):
        self.client.force_authenticate(user=self.admin)
        assigned_res = self.client.get(
            f"/api/v1/teachers/{self.assigned.id}/attendance-summary/?range=month"
        )
        self.assertEqual(assigned_res.status_code, status.HTTP_200_OK)
        self.assertEqual(assigned_res.data["personal"]["covered"], 1)
        # Assigned did not teach — accountability for student rolls goes to cover
        self.assertEqual(assigned_res.data["accountability"]["total_marks"], 0)

        cover_res = self.client.get(
            f"/api/v1/teachers/{self.cover.id}/attendance-summary/?range=month"
        )
        self.assertEqual(cover_res.status_code, status.HTTP_200_OK)
        self.assertEqual(cover_res.data["personal"]["cover_taught"], 1)
        self.assertEqual(cover_res.data["accountability"]["late"], 1)

    def test_patch_actual_teacher(self):
        self.client.force_authenticate(user=self.admin)
        # reset to no cover
        self.session.actual_teacher = None
        self.session.save()
        res = self.client.patch(
            f"/api/v1/sessions/{self.session.id}/",
            {"actual_teacher_id": self.cover.id, "status": "completed"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.session.refresh_from_db()
        self.assertEqual(self.session.actual_teacher_id, self.cover.id)


class TimetableSlotClassFilterTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username="slot_filter_admin", role="admin", clerk_id="clerk_slot_filt_1"
        )
        self.class_a = Class.objects.create(education_level="IG", cohort_identifier="A")
        self.class_b = Class.objects.create(education_level="IG", cohort_identifier="B")
        self.teacher = Teacher.objects.create(name="Slot Filter Teacher")
        self.subject = Subject.objects.create(name="Slot Filter Subject")
        self.slot_a = TimetableSlot.objects.create(
            class_obj=self.class_a,
            subject=self.subject,
            teacher=self.teacher,
            day_of_week=0,
            start_time="08:00",
            end_time="09:00",
        )
        TimetableSlot.objects.create(
            class_obj=self.class_b,
            subject=self.subject,
            teacher=self.teacher,
            day_of_week=0,
            start_time="10:00",
            end_time="11:00",
        )

    def test_filter_timetable_slots_by_class_id(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.get(f"/api/v1/timetable-slots/?class_id={self.class_a.id}")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        rows = res.data if isinstance(res.data, list) else res.data.get("results", [])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], self.slot_a.id)
