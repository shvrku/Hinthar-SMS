from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase, APIClient

from class_sessions.models import Session, SessionAttendance
from people.models import Student, Subject, Teacher
from timetable.models import Class, ClassStudent, StudentSubjectEnrollment, TimetableSlot

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

    def test_all_range_keeps_full_daily_campus_series(self):
        self.client.force_authenticate(user=self.admin)
        today = timezone.localdate()
        past = today - timedelta(days=5)
        Session.objects.create(
            timetable_slot=self.slot,
            teacher=self.teacher,
            class_obj=self.class_obj,
            start_time=timezone.make_aware(datetime.combine(past, time(9, 0))),
            end_time=timezone.make_aware(datetime.combine(past, time(10, 0))),
            status="completed",
        )
        res = self.client.get(
            f"/api/v1/classes/{self.class_obj.id}/attendance-summary/?range=all"
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        expected_days = (today - past).days + 1
        self.assertEqual(res.data["campus"]["days_in_range"], expected_days)
        self.assertEqual(len(res.data["campus"]["daily"]), expected_days)
        self.assertEqual(res.data["campus"]["daily"][0]["date"], past.isoformat())
        self.assertEqual(res.data["campus"]["daily"][-1]["date"], today.isoformat())


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

    def test_list_requires_class_id(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.get("/api/v1/timetable-slots/")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)


class HubTimetableAccessTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username="hub_tt_admin", role="admin", clerk_id="clerk_hub_tt_admin"
        )
        self.class_obj = Class.objects.create(education_level="IG", cohort_identifier="H")
        self.other_class = Class.objects.create(education_level="IG", cohort_identifier="Z")
        self.teacher_user = User.objects.create_user(
            username="hub_tt_teacher", role="teacher", clerk_id="clerk_hub_tt_teacher"
        )
        self.other_teacher_user = User.objects.create_user(
            username="hub_tt_other_teacher", role="teacher", clerk_id="clerk_hub_tt_other_t"
        )
        self.student_user = User.objects.create_user(
            username="hub_tt_student", role="student", clerk_id="clerk_hub_tt_student"
        )
        self.other_student_user = User.objects.create_user(
            username="hub_tt_other_student", role="student", clerk_id="clerk_hub_tt_other_s"
        )
        self.teacher = Teacher.objects.create(name="Hub TT Teacher", user=self.teacher_user)
        self.other_teacher = Teacher.objects.create(
            name="Hub TT Other Teacher", user=self.other_teacher_user
        )
        self.student = Student.objects.create(name="Hub TT Student", user=self.student_user)
        Student.objects.create(name="Hub TT Other Student", user=self.other_student_user)
        ClassStudent.objects.create(class_obj=self.class_obj, student=self.student)
        self.subject = Subject.objects.create(name="Hub TT Subject")
        self.slot = TimetableSlot.objects.create(
            class_obj=self.class_obj,
            subject=self.subject,
            teacher=self.teacher,
            day_of_week=1,
            start_time="09:00",
            end_time="10:00",
        )

    def test_staff_can_read_class_and_teacher_timetable(self):
        self.client.force_authenticate(user=self.admin)
        class_res = self.client.get(f"/api/v1/timetable/class/{self.class_obj.id}/")
        teacher_res = self.client.get(f"/api/v1/timetable/teacher/{self.teacher.id}/")
        self.assertEqual(class_res.status_code, status.HTTP_200_OK)
        self.assertEqual(teacher_res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(class_res.data), 1)
        self.assertEqual(teacher_res.data[0]["id"], self.slot.id)

    def test_enrolled_student_can_read_own_class_timetable(self):
        self.client.force_authenticate(user=self.student_user)
        res = self.client.get(f"/api/v1/timetable/class/{self.class_obj.id}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data[0]["id"], self.slot.id)

    def test_student_denied_other_class_timetable(self):
        self.client.force_authenticate(user=self.student_user)
        res = self.client.get(f"/api/v1/timetable/class/{self.other_class.id}/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_unenrolled_student_denied_class_timetable(self):
        self.client.force_authenticate(user=self.other_student_user)
        res = self.client.get(f"/api/v1/timetable/class/{self.class_obj.id}/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_student_denied_teacher_timetable(self):
        self.client.force_authenticate(user=self.student_user)
        res = self.client.get(f"/api/v1/timetable/teacher/{self.teacher.id}/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_teacher_can_read_own_timetable(self):
        self.client.force_authenticate(user=self.teacher_user)
        res = self.client.get(f"/api/v1/timetable/teacher/{self.teacher.id}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data[0]["id"], self.slot.id)

    def test_teacher_denied_other_teacher_timetable(self):
        self.client.force_authenticate(user=self.teacher_user)
        res = self.client.get(f"/api/v1/timetable/teacher/{self.other_teacher.id}/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_teacher_denied_class_timetable(self):
        self.client.force_authenticate(user=self.teacher_user)
        res = self.client.get(f"/api/v1/timetable/class/{self.class_obj.id}/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)


class ClassCascadeDeletionTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username="class_del_admin", role="admin", clerk_id="clerk_class_del_1"
        )
        self.class_obj = Class.objects.create(education_level="IG", cohort_identifier="Z")
        self.teacher = Teacher.objects.create(name="Delete Test Teacher")
        self.subject = Subject.objects.create(name="Delete Test Math")
        self.student = Student.objects.create(name="Delete Test Student")
        self.class_student = ClassStudent.objects.create(class_obj=self.class_obj, student=self.student)
        self.slot = TimetableSlot.objects.create(
            class_obj=self.class_obj,
            subject=self.subject,
            teacher=self.teacher,
            day_of_week=1,
            start_time="10:00",
            end_time="11:00",
        )
        today = timezone.localdate()
        self.session = Session.objects.create(
            timetable_slot=self.slot,
            teacher=self.teacher,
            class_obj=self.class_obj,
            start_time=timezone.make_aware(datetime.combine(today, time(10, 0))),
            end_time=timezone.make_aware(datetime.combine(today, time(11, 0))),
            status="scheduled",
        )
        self.attendance = SessionAttendance.objects.create(
            session=self.session, student=self.student, status="present"
        )

    def test_delete_class_deletes_everything_cleanly(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.delete(f"/api/v1/classes/{self.class_obj.id}/")
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Class.objects.filter(id=self.class_obj.id).exists())
        self.assertFalse(Session.objects.filter(id=self.session.id).exists())
        self.assertFalse(SessionAttendance.objects.filter(id=self.attendance.id).exists())
        self.assertFalse(TimetableSlot.objects.filter(id=self.slot.id).exists())
        self.assertFalse(ClassStudent.objects.filter(id=self.class_student.id).exists())

    def test_bulk_delete_classes_deletes_everything_cleanly(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.delete(
            "/api/v1/classes/bulk_delete/",
            {"ids": [self.class_obj.id]},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["deleted_count"], 1)
        self.assertFalse(Class.objects.filter(id=self.class_obj.id).exists())
        self.assertFalse(Session.objects.filter(id=self.session.id).exists())
        self.assertFalse(SessionAttendance.objects.filter(id=self.attendance.id).exists())
        self.assertFalse(TimetableSlot.objects.filter(id=self.slot.id).exists())
        self.assertFalse(ClassStudent.objects.filter(id=self.class_student.id).exists())

    def test_delete_timetable_slot_cascades_sessions(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.delete(f"/api/v1/timetable-slots/{self.slot.id}/")
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(TimetableSlot.objects.filter(id=self.slot.id).exists())
        self.assertFalse(Session.objects.filter(id=self.session.id).exists())
        self.assertFalse(SessionAttendance.objects.filter(id=self.attendance.id).exists())
        self.assertTrue(Class.objects.filter(id=self.class_obj.id).exists())

    def test_bulk_delete_timetable_slots_cascades_sessions(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.delete(
            "/api/v1/timetable-slots/bulk_delete/",
            {"ids": [self.slot.id]},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["deleted_count"], 1)
        self.assertFalse(TimetableSlot.objects.filter(id=self.slot.id).exists())
        self.assertFalse(Session.objects.filter(id=self.session.id).exists())
        self.assertFalse(SessionAttendance.objects.filter(id=self.attendance.id).exists())
        self.assertTrue(Class.objects.filter(id=self.class_obj.id).exists())


class StudentSubjectEnrollmentTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username="cross_admin", role="admin", clerk_id="clerk_cross_1"
        )
        self.class_a = Class.objects.create(education_level="Year1", cohort_identifier="A")
        self.class_b = Class.objects.create(education_level="Year2", cohort_identifier="B")
        self.teacher = Teacher.objects.create(name="Cross Teacher")
        self.subject = Subject.objects.create(name="Cross Physics")
        self.student = Student.objects.create(name="Cross Student")
        # Student primarily enrolled in Class A
        ClassStudent.objects.create(class_obj=self.class_a, student=self.student)

        # Class B has a timetable slot for Physics
        self.slot = TimetableSlot.objects.create(
            class_obj=self.class_b,
            subject=self.subject,
            teacher=self.teacher,
            day_of_week=0,
            start_time=time(9, 0),
            end_time=time(10, 0),
        )

    def test_cross_enroll_creates_record(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            "/api/v1/student-subject-enrollments/",
            {
                "class_obj_id": self.class_b.id,
                "student_id": self.student.id,
                "subject_id": self.subject.id,
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            StudentSubjectEnrollment.objects.filter(
                class_obj=self.class_b,
                student=self.student,
                subject=self.subject,
            ).exists()
        )

    def test_cross_enroll_list_filter(self):
        self.client.force_authenticate(user=self.admin)
        StudentSubjectEnrollment.objects.create(
            class_obj=self.class_b,
            student=self.student,
            subject=self.subject,
        )
        res = self.client.get(f"/api/v1/student-subject-enrollments/?student_id={self.student.id}")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data.get("results", res.data)
        self.assertEqual(len(results), 1)

    def test_cross_enroll_delete(self):
        self.client.force_authenticate(user=self.admin)
        sse = StudentSubjectEnrollment.objects.create(
            class_obj=self.class_b,
            student=self.student,
            subject=self.subject,
        )
        res = self.client.delete(f"/api/v1/student-subject-enrollments/{sse.id}/")
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(StudentSubjectEnrollment.objects.filter(id=sse.id).exists())



class CohortCourseAndConflictTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username="cohort_course_admin", role="admin", clerk_id="clerk_cohort_course_1"
        )
        # Create cohorts using the new explicit terminology fields
        self.cohort_ig_k1 = Class.objects.create(
            education_level="IG", cohort="K", sub_cohort_category="1"
        )
        self.cohort_ig_k2 = Class.objects.create(
            education_level="IG", cohort="K", sub_cohort_category="2"
        )
        self.teacher_1 = Teacher.objects.create(name="Teacher One")
        self.teacher_2 = Teacher.objects.create(name="Teacher Two")
        self.math = Subject.objects.create(name="Course Math")
        self.physics = Subject.objects.create(name="Course Physics")
        self.econ = Subject.objects.create(name="Course Economics")
        self.student = Student.objects.create(name="Course Student")

        # Assign Primary Cohort IG K1
        ClassStudent.objects.create(class_obj=self.cohort_ig_k1, student=self.student)

        # IG K1 has Math (Mon 09:00-10:00) and Physics (Mon 10:00-11:00)
        self.slot_k1_math = TimetableSlot.objects.create(
            class_obj=self.cohort_ig_k1,
            subject=self.math,
            teacher=self.teacher_1,
            day_of_week=0,
            start_time=time(9, 0),
            end_time=time(10, 0),
        )
        self.slot_k1_phys = TimetableSlot.objects.create(
            class_obj=self.cohort_ig_k1,
            subject=self.physics,
            teacher=self.teacher_1,
            day_of_week=0,
            start_time=time(10, 0),
            end_time=time(11, 0),
        )

        # IG K2 has Economics (Mon 09:30-10:30) -> overlaps with IG K1 Math AND IG K1 Physics!
        self.slot_k2_econ = TimetableSlot.objects.create(
            class_obj=self.cohort_ig_k2,
            subject=self.econ,
            teacher=self.teacher_2,
            day_of_week=0,
            start_time=time(9, 30),
            end_time=time(10, 30),
        )

    def test_cohort_explicit_terminology_fields(self):
        self.assertEqual(self.cohort_ig_k1.cohort, "K")
        self.assertEqual(self.cohort_ig_k1.sub_cohort_category, "1")
        self.assertEqual(self.cohort_ig_k1.full_cohort_identifier, "IG K1")

        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            "/api/v1/classes/",
            {
                "education_level": "IAL",
                "cohort": "K",
                "sub_cohort_category": "2",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["cohort"], "K")
        self.assertEqual(res.data["sub_cohort_category"], "2")
        self.assertEqual(res.data["full_cohort_identifier"], "IAL K2")

    def test_courses_auto_created_and_listable(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.get(f"/api/v1/courses/?cohort_id={self.cohort_ig_k1.id}")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 2)
        labels = {c["course_label"] for c in res.data}
        self.assertEqual(labels, {"IG K1 — Course Math", "IG K1 — Course Physics"})

    def test_conflict_detected_but_enrollment_allowed(self):
        self.client.force_authenticate(user=self.admin)
        # Preview conflict before enrolling
        preview = self.client.get(
            f"/api/v1/timetable/student/{self.student.id}/"
            f"?candidate_class_id={self.cohort_ig_k2.id}&candidate_subject_id={self.econ.id}"
        )
        self.assertEqual(preview.status_code, status.HTTP_200_OK)
        self.assertTrue(preview.data["has_conflicts"])
        self.assertEqual(preview.data["conflict_count"], 2)

        # Enroll anyway — must NOT block!
        res = self.client.post(
            "/api/v1/course-enrollments/",
            {
                "class_obj_id": self.cohort_ig_k2.id,
                "student_id": self.student.id,
                "subject_id": self.econ.id,
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(res.data["has_conflicts"])
        self.assertEqual(res.data["conflict_count"], 2)

        # Dropping IG K1 Physics reduces conflict count from 2 to 1
        drop_res = self.client.post(
            "/api/v1/course-enrollments/",
            {
                "class_obj_id": self.cohort_ig_k1.id,
                "student_id": self.student.id,
                "subject_id": self.physics.id,
                "status": "dropped",
            },
            format="json",
        )
        self.assertEqual(drop_res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(drop_res.data["has_conflicts"])
        self.assertEqual(drop_res.data["conflict_count"], 1)

    def test_student_can_only_have_one_primary_cohort(self):
        self.client.force_authenticate(user=self.admin)
        # Student is already in IG K1 as Primary Cohort; attempting to add IG K2 as a second Primary Cohort must fail
        res = self.client.post(
            "/api/v1/class-students/",
            {
                "class_obj_id": self.cohort_ig_k2.id,
                "student_id": self.student.id,
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("student_id", res.data)

        # Updating their single Primary Cohort to IG K2 via PATCH works
        cs = ClassStudent.objects.get(student=self.student)
        patch_res = self.client.patch(
            f"/api/v1/class-students/{cs.id}/",
            {"class_obj_id": self.cohort_ig_k2.id},
            format="json",
        )
        self.assertEqual(patch_res.status_code, status.HTTP_200_OK)
        self.assertEqual(ClassStudent.objects.filter(student=self.student).count(), 1)
        self.assertEqual(ClassStudent.objects.get(student=self.student).class_obj_id, self.cohort_ig_k2.id)

