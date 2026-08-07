from datetime import date, datetime, timedelta
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from people.models import Student
from class_sessions.models import CheckIn, Session, SessionAttendance, AdHocSession, AdHocSessionAttendance

User = get_user_model()

class QRCheckInViewTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        # Create a terminal user for authentication
        self.terminal_user = User.objects.create_user(
            username="terminal_user",
            role="terminal",
            clerk_id="clerk_term_1"
        )
        self.student = Student.objects.create(
            name="Test Student",
            check_in_token="valid_check_in_token_123"
        )

    def test_qr_checkin_success(self):
        self.client.force_authenticate(user=self.terminal_user)
        response = self.client.post(
            "/api/v1/check-ins/qr/",
            {"check_in_token": "valid_check_in_token_123"},
            format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(CheckIn.objects.filter(student=self.student).exists())

    def test_qr_checkin_already_checked_in(self):
        self.client.force_authenticate(user=self.terminal_user)
        # First check-in
        response = self.client.post(
            "/api/v1/check-ins/qr/",
            {"check_in_token": "valid_check_in_token_123"},
            format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Second check-in on the same day
        response = self.client.post(
            "/api/v1/check-ins/qr/",
            {"check_in_token": "valid_check_in_token_123"},
            format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["error"], "Student already checked in today")

    def test_qr_checkin_invalid_token(self):
        self.client.force_authenticate(user=self.terminal_user)
        response = self.client.post(
            "/api/v1/check-ins/qr/",
            {"check_in_token": "invalid_token"},
            format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], "Invalid check-in token")


class GenerateClassSessionsViewTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        # Create an admin user for authentication
        self.admin_user = User.objects.create_user(
            username="admin_user",
            role="admin",
            clerk_id="clerk_admin_1"
        )
        from timetable.models import Class
        self.test_class = Class.objects.create(
            education_level='IG', cohort_identifier='A'
        )

    def test_generate_sessions_empty_start_and_end(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.post(
            f"/api/v1/sessions/generate/{self.test_class.id}/",
            {"start_date": "", "end_date": ""},
            format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_generate_sessions_empty_end(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.post(
            f"/api/v1/sessions/generate/{self.test_class.id}/",
            {"start_date": "2026-07-20", "end_date": ""},
            format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_generate_sessions_empty_start(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.post(
            f"/api/v1/sessions/generate/{self.test_class.id}/",
            {"start_date": "", "end_date": "2026-07-25"},
            format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_generate_sessions_invalid_start_date(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.post(
            f"/api/v1/sessions/generate/{self.test_class.id}/",
            {"start_date": "invalid-date", "end_date": ""},
            format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], "Invalid date format, use ISO 8601 (YYYY-MM-DD)")

    def test_generate_sessions_invalid_end_date(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.post(
            f"/api/v1/sessions/generate/{self.test_class.id}/",
            {"start_date": "2026-07-20", "end_date": "not-a-date"},
            format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], "Invalid date format, use ISO 8601 (YYYY-MM-DD)")

    def test_generate_sessions_class_not_found(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.post(
            "/api/v1/sessions/generate/99999/",
            {},
            format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

class AttendanceAutoGenerationTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.terminal_user = User.objects.create_user(
            username="terminal_user", role="terminal", clerk_id="clerk_term_2"
        )
        self.student = Student.objects.create(name="Auto Student", check_in_token="auto_token_123")
        
        from timetable.models import Class, TimetableSlot
        from people.models import Teacher, Subject
        self.class_obj = Class.objects.create(education_level='IG', cohort_identifier='B')
        self.teacher = Teacher.objects.create(name="Mr. Smith")
        self.subject = Subject.objects.create(name="Math")
        
        self.slot1 = TimetableSlot.objects.create(class_obj=self.class_obj, subject=self.subject, teacher=self.teacher, day_of_week=0, start_time="09:00", end_time="10:00")
        self.slot2 = TimetableSlot.objects.create(class_obj=self.class_obj, subject=self.subject, teacher=self.teacher, day_of_week=0, start_time="08:30", end_time="09:30")
        self.slot3 = TimetableSlot.objects.create(class_obj=self.class_obj, subject=self.subject, teacher=self.teacher, day_of_week=0, start_time="08:00", end_time="09:00")
        self.slot4 = TimetableSlot.objects.create(class_obj=self.class_obj, subject=self.subject, teacher=self.teacher, day_of_week=1, start_time="09:00", end_time="10:00")
        
        # Create today's session
        today = timezone.localdate()
        
        # Session 1: 09:00 - 10:00 (Student checks in at 09:10 -> present)
        # Session 2: 11:00 - 12:00 (Student checks in at 09:10 -> early/present) -> Actually logic says <= 15 mins after start -> present
        # Session 3: 08:00 - 09:00 (Student checks in at 09:10 -> after end -> absent)
        # Session 4: 08:30 - 09:30 (Student checks in at 09:10 -> > 15 mins after start, but before end -> late)
        
        self.session_present = Session.objects.create(
            timetable_slot=self.slot1, teacher=self.teacher, class_obj=self.class_obj,
            start_time=timezone.make_aware(datetime.combine(today, datetime.min.time().replace(hour=9, minute=0))),
            end_time=timezone.make_aware(datetime.combine(today, datetime.min.time().replace(hour=10, minute=0)))
        )
        self.att_present = SessionAttendance.objects.create(session=self.session_present, student=self.student, status='absent')
        
        self.session_late = Session.objects.create(
            timetable_slot=self.slot2, teacher=self.teacher, class_obj=self.class_obj,
            start_time=timezone.make_aware(datetime.combine(today, datetime.min.time().replace(hour=8, minute=30))),
            end_time=timezone.make_aware(datetime.combine(today, datetime.min.time().replace(hour=9, minute=30)))
        )
        self.att_late = SessionAttendance.objects.create(session=self.session_late, student=self.student, status='absent')
        
        self.session_absent = Session.objects.create(
            timetable_slot=self.slot3, teacher=self.teacher, class_obj=self.class_obj,
            start_time=timezone.make_aware(datetime.combine(today, datetime.min.time().replace(hour=8, minute=0))),
            end_time=timezone.make_aware(datetime.combine(today, datetime.min.time().replace(hour=9, minute=0)))
        )
        self.att_absent = SessionAttendance.objects.create(session=self.session_absent, student=self.student, status='absent')
        
        # Session with manual override
        self.session_override = Session.objects.create(
            timetable_slot=self.slot4, teacher=self.teacher, class_obj=self.class_obj,
            start_time=timezone.make_aware(datetime.combine(today, datetime.min.time().replace(hour=9, minute=0))),
            end_time=timezone.make_aware(datetime.combine(today, datetime.min.time().replace(hour=10, minute=0)))
        )
        self.att_override = SessionAttendance.objects.create(session=self.session_override, student=self.student, status='late')

    def test_attendance_generation_on_qr_checkin(self):
        # We want to simulate checking in at 09:10 AM exactly.
        # But CheckIn view uses auto_now_add=True for timestamp. 
        # So we can just create the CheckIn manually to test the utility directly, 
        # or we mock the timezone.now in the view test.
        # It's cleaner to test the view, but we have to manipulate the DB object afterward to simulate the exact time.
        
        # Actually, let's call the view to create the checkin, then override the timestamp 
        # and run the utility function manually to have precise control over the time.
        
        self.client.force_authenticate(user=self.terminal_user)
        response = self.client.post("/api/v1/check-ins/qr/", {"check_in_token": "auto_token_123"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        checkin = CheckIn.objects.get(student=self.student)
        # Override timestamp to 09:10 AM
        checkin.timestamp = timezone.make_aware(datetime.combine(checkin.date, datetime.min.time().replace(hour=9, minute=10)))
        checkin.save()
        
        # Reset statuses to absent prior to reprocessing custom time
        SessionAttendance.objects.filter(id__in=[self.att_present.id, self.att_late.id, self.att_absent.id]).update(status='absent')

        # Re-run the utility to process this exact time
        from class_sessions.utils import process_checkin_attendance
        process_checkin_attendance(checkin)
        
        # Verify statuses
        self.att_present.refresh_from_db()
        self.assertEqual(self.att_present.status, 'present') # 9:10 is <= 9:15
        
        self.att_late.refresh_from_db()
        self.assertEqual(self.att_late.status, 'late') # 9:10 is > 8:45 but <= 9:30
        
        self.att_absent.refresh_from_db()
        self.assertEqual(self.att_absent.status, 'absent') # 9:10 is > 9:00
        
        self.att_override.refresh_from_db()
        self.assertEqual(self.att_override.status, 'late') # was manually marked late, should not change


class AttendanceMatrixViewTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="test_matrix_user", role="admin", clerk_id="clerk_matrix_1")
        from timetable.models import Class, ClassStudent, TimetableSlot
        from people.models import Teacher, Subject
        
        self.class_obj = Class.objects.create(education_level='IG', cohort_identifier='M')
        self.teacher = Teacher.objects.create(name="Matrix Teacher")
        self.subject = Subject.objects.create(name="Matrix Math")
        self.student = Student.objects.create(name="Matrix Student", check_in_token="mat_tok_1")
        
        ClassStudent.objects.create(class_obj=self.class_obj, student=self.student)
        
        self.slot = TimetableSlot.objects.create(
            class_obj=self.class_obj, subject=self.subject, teacher=self.teacher,
            day_of_week=0, start_time="09:00", end_time="10:00"
        )
        
        today = timezone.localdate()
        self.session = Session.objects.create(
            timetable_slot=self.slot,
            teacher=self.teacher,
            class_obj=self.class_obj,
            start_time=timezone.make_aware(datetime.combine(today, datetime.min.time().replace(hour=9, minute=0))),
            end_time=timezone.make_aware(datetime.combine(today, datetime.min.time().replace(hour=10, minute=0)))
        )
        SessionAttendance.objects.create(session=self.session, student=self.student, status='present')

    def test_matrix_endpoint_success(self):
        self.client.force_authenticate(user=self.user)
        today = timezone.localdate()
        response = self.client.get(
            f"/api/v1/attendance/matrix/?class_id={self.class_obj.id}&month={today.month}&year={today.year}"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["class_id"], self.class_obj.id)
        self.assertEqual(len(response.data["sessions"]), 1)
        self.assertEqual(len(response.data["students"]), 1)
        self.assertEqual(response.data["students"][0]["records"][str(self.session.id)], "present")

    def test_matrix_endpoint_missing_class_id(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/v1/attendance/matrix/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_matrix_endpoint_rejects_all_and_adhoc_sentinels(self):
        self.client.force_authenticate(user=self.user)
        for sentinel in ("all", "adhoc"):
            response = self.client.get(f"/api/v1/attendance/matrix/?class_id={sentinel}")
            self.assertEqual(
                response.status_code,
                status.HTTP_400_BAD_REQUEST,
                msg=f"expected 400 for class_id={sentinel}",
            )

    def test_matrix_endpoint_class_not_found(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/v1/attendance/matrix/?class_id=9999")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class SessionFilterTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="test_filter_user", role="admin", clerk_id="clerk_filt_1")
        from timetable.models import Class, TimetableSlot
        from people.models import Teacher, Subject
        
        self.class_obj = Class.objects.create(education_level='IG', cohort_identifier='F')
        self.teacher = Teacher.objects.create(name="Filter Teacher")
        self.subject = Subject.objects.create(name="Filter Physics")
        
        self.slot = TimetableSlot.objects.create(
            class_obj=self.class_obj, subject=self.subject, teacher=self.teacher,
            day_of_week=1, start_time="10:00", end_time="11:00"
        )
        
        d1 = date(2026, 7, 10)
        self.session1 = Session.objects.create(
            timetable_slot=self.slot, teacher=self.teacher, class_obj=self.class_obj,
            start_time=timezone.make_aware(datetime.combine(d1, datetime.min.time().replace(hour=10, minute=0))),
            end_time=timezone.make_aware(datetime.combine(d1, datetime.min.time().replace(hour=11, minute=0)))
        )

    def test_session_list_extended_filters(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(
            f"/api/v1/sessions/?class_id={self.class_obj.id}&start_date=2026-07-01&end_date=2026-07-31&month=7&year=2026&subject_id={self.subject.id}"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)

    def test_session_list_filter_by_timetable_slot_id(self):
        from timetable.models import TimetableSlot

        self.client.force_authenticate(user=self.user)
        other_slot = TimetableSlot.objects.create(
            class_obj=self.class_obj,
            subject=self.subject,
            teacher=self.teacher,
            day_of_week=2,
            start_time="12:00",
            end_time="13:00",
        )
        d2 = date(2026, 7, 14)
        Session.objects.create(
            timetable_slot=other_slot,
            teacher=self.teacher,
            class_obj=self.class_obj,
            start_time=timezone.make_aware(
                datetime.combine(d2, datetime.min.time().replace(hour=12, minute=0))
            ),
            end_time=timezone.make_aware(
                datetime.combine(d2, datetime.min.time().replace(hour=13, minute=0))
            ),
        )
        response = self.client.get(
            f"/api/v1/sessions/?timetable_slot_id={self.slot.id}"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], self.session1.id)


class CheckInCorrectionTests(APITestCase):
    """Staff can delete a campus check-in to undo a mis-tap."""

    def setUp(self):
        self.client = APIClient()
        self.staff = User.objects.create_user(
            username="staff_correction",
            role="staff",
            clerk_id="clerk_staff_corr_1",
        )
        self.terminal = User.objects.create_user(
            username="terminal_correction",
            role="terminal",
            clerk_id="clerk_term_corr_1",
        )
        self.student = Student.objects.create(
            name="Correction Student",
            check_in_token="corr_token_abc",
        )
        self.checkin = CheckIn.objects.create(
            student=self.student,
            check_in_type="manual",
            checked_by=self.staff,
            date=timezone.localdate(),
        )

    def test_staff_can_delete_checkin(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.delete(f"/api/v1/check-ins/{self.checkin.id}/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(CheckIn.objects.filter(pk=self.checkin.id).exists())

    def test_terminal_cannot_delete_checkin(self):
        self.client.force_authenticate(user=self.terminal)
        response = self.client.delete(f"/api/v1/check-ins/{self.checkin.id}/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(CheckIn.objects.filter(pk=self.checkin.id).exists())

    def test_staff_bulk_delete_checkins(self):
        other = Student.objects.create(name="Other", check_in_token="corr_token_other")
        second = CheckIn.objects.create(
            student=other,
            check_in_type="qr",
            checked_by=self.staff,
            date=timezone.localdate(),
        )
        self.client.force_authenticate(user=self.staff)
        response = self.client.delete(
            "/api/v1/check-ins/bulk_delete/",
            {"ids": [self.checkin.id, second.id]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["deleted_count"], 2)

    def test_delete_reverts_auto_marked_attendance_only(self):
        from timetable.models import Class, TimetableSlot
        from people.models import Teacher, Subject

        class_obj = Class.objects.create(education_level='IG', cohort_identifier='Z')
        teacher = Teacher.objects.create(name="Corr Teacher")
        subject = Subject.objects.create(name="Corr Subject")
        slot = TimetableSlot.objects.create(
            class_obj=class_obj,
            subject=subject,
            teacher=teacher,
            day_of_week=1,
            start_time="09:00",
            end_time="10:00",
        )
        today = timezone.localdate()
        session = Session.objects.create(
            timetable_slot=slot,
            teacher=teacher,
            class_obj=class_obj,
            start_time=timezone.make_aware(datetime.combine(today, datetime.min.time().replace(hour=9))),
            end_time=timezone.make_aware(datetime.combine(today, datetime.min.time().replace(hour=10))),
        )
        auto_row = SessionAttendance.objects.create(
            session=session,
            student=self.student,
            status='present',
            auto_marked_by_checkin=self.checkin,
        )
        other_student = Student.objects.create(name="Manual Student", check_in_token="manual_student_tok")
        manual_row = SessionAttendance.objects.create(
            session=session,
            student=other_student,
            status='present',
            auto_marked_by_checkin=None,
        )
        adhoc = AdHocSession.objects.create(
            teacher=teacher,
            subject=subject,
            date=today,
            start_time="11:00",
            end_time="12:00",
        )
        adhoc_auto = AdHocSessionAttendance.objects.create(
            ad_hoc_session=adhoc,
            student=self.student,
            status='late',
            auto_marked_by_checkin=self.checkin,
        )

        self.client.force_authenticate(user=self.staff)
        response = self.client.delete(f"/api/v1/check-ins/{self.checkin.id}/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        auto_row.refresh_from_db()
        manual_row.refresh_from_db()
        adhoc_auto.refresh_from_db()
        self.assertEqual(auto_row.status, 'absent')
        self.assertIsNone(auto_row.auto_marked_by_checkin_id)
        self.assertEqual(manual_row.status, 'present')
        self.assertEqual(adhoc_auto.status, 'absent')
        self.assertIsNone(adhoc_auto.auto_marked_by_checkin_id)


class CheckInOverviewAggregateTests(APITestCase):
    """Server-side aggregate for /check-ins/overview/ (class / search / summary modes)."""

    URL = "/api/v1/check-ins/overview/"

    def setUp(self):
        from timetable.models import Class, ClassStudent

        self.client = APIClient()
        self.staff = User.objects.create_user(
            username="staff_overview", role="staff", clerk_id="clerk_staff_ov_1"
        )
        self.terminal = User.objects.create_user(
            username="terminal_overview", role="terminal", clerk_id="clerk_term_ov_1"
        )
        self.today = timezone.localdate()

        self.class_a = Class.objects.create(education_level="Year7", cohort_identifier="A")
        self.class_b = Class.objects.create(education_level="Year8", cohort_identifier="B")

        self.arrived_student = Student.objects.create(name="Alice Arrived", check_in_token="ov_alice")
        self.missing_student = Student.objects.create(name="Bob Missing", check_in_token="ov_bob")
        self.other_class_student = Student.objects.create(name="Cara Other", check_in_token="ov_cara")

        ClassStudent.objects.create(class_obj=self.class_a, student=self.arrived_student)
        ClassStudent.objects.create(class_obj=self.class_a, student=self.missing_student)
        ClassStudent.objects.create(class_obj=self.class_b, student=self.other_class_student)

        # Alice checked in today; Bob did not.
        self.checkin = CheckIn.objects.create(
            student=self.arrived_student, check_in_type="qr", date=self.today
        )

    def test_requires_staff(self):
        self.client.force_authenticate(user=self.terminal)
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_classes_summary_mode(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(self.URL, {"date": self.today.isoformat()})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["mode"], "classes")
        summary = {row["id"]: row for row in response.data["classes"]}
        self.assertEqual(summary[self.class_a.id]["total"], 2)
        self.assertEqual(summary[self.class_a.id]["arrived"], 1)
        self.assertEqual(summary[self.class_b.id]["total"], 1)
        self.assertEqual(summary[self.class_b.id]["arrived"], 0)

    def test_class_roster_mode(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(
            self.URL, {"date": self.today.isoformat(), "class_id": self.class_a.id}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["mode"], "class")
        self.assertEqual(response.data["total"], 2)
        self.assertEqual(response.data["arrived"], 1)
        by_id = {s["id"]: s for s in response.data["students"]}
        self.assertIsNotNone(by_id[self.arrived_student.id]["check_in"])
        self.assertEqual(by_id[self.arrived_student.id]["check_in"]["check_in_type"], "qr")
        self.assertIsNone(by_id[self.missing_student.id]["check_in"])

    def test_class_roster_unknown_class_404(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(self.URL, {"class_id": 999999})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_school_wide_roster_mode(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(
            self.URL, {"date": self.today.isoformat(), "class_id": "all"}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["mode"], "school")
        self.assertEqual(response.data["total"], 3)
        self.assertEqual(response.data["arrived"], 1)
        self.assertEqual(response.data["count"], 3)
        self.assertEqual(response.data["page"], 1)
        self.assertEqual(response.data["page_size"], 50)
        self.assertEqual(response.data["num_pages"], 1)
        by_id = {s["id"]: s for s in response.data["students"]}
        self.assertIn("class_label", by_id[self.arrived_student.id])
        self.assertIsNotNone(by_id[self.arrived_student.id]["check_in"])
        self.assertIsNone(by_id[self.missing_student.id]["check_in"])
        self.assertIsNone(by_id[self.other_class_student.id]["check_in"])

    def test_school_wide_pagination(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(
            self.URL,
            {
                "date": self.today.isoformat(),
                "class_id": "all",
                "page": 1,
                "page_size": 1,
            },
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["mode"], "school")
        self.assertEqual(response.data["total"], 3)
        self.assertEqual(response.data["arrived"], 1)
        self.assertEqual(response.data["count"], 3)
        self.assertEqual(response.data["page_size"], 1)
        self.assertEqual(len(response.data["students"]), 1)
        self.assertEqual(response.data["num_pages"], 3)

        page_two = self.client.get(
            self.URL,
            {
                "date": self.today.isoformat(),
                "class_id": "all",
                "page": 2,
                "page_size": 1,
            },
        )
        self.assertEqual(len(page_two.data["students"]), 1)
        self.assertNotEqual(
            response.data["students"][0]["id"],
            page_two.data["students"][0]["id"],
        )

    def test_school_wide_status_missing_and_arrived(self):
        self.client.force_authenticate(user=self.staff)
        missing = self.client.get(
            self.URL,
            {
                "date": self.today.isoformat(),
                "class_id": "all",
                "status": "missing",
            },
        )
        self.assertEqual(missing.status_code, status.HTTP_200_OK)
        self.assertEqual(missing.data["status"], "missing")
        self.assertEqual(missing.data["count"], 2)
        self.assertEqual(missing.data["arrived"], 1)
        self.assertEqual(missing.data["total"], 3)
        self.assertTrue(all(row["check_in"] is None for row in missing.data["students"]))

        arrived = self.client.get(
            self.URL,
            {
                "date": self.today.isoformat(),
                "class_id": "all",
                "status": "arrived",
            },
        )
        self.assertEqual(arrived.data["status"], "arrived")
        self.assertEqual(arrived.data["count"], 1)
        self.assertEqual(len(arrived.data["students"]), 1)
        self.assertIsNotNone(arrived.data["students"][0]["check_in"])
        self.assertEqual(arrived.data["students"][0]["id"], self.arrived_student.id)

    def test_school_wide_invalid_status_400(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(
            self.URL,
            {"class_id": "all", "status": "late"},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_search_mode_matches_across_classes(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(
            self.URL, {"date": self.today.isoformat(), "search": "Cara"}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["mode"], "search")
        self.assertEqual(response.data["count"], 1)
        row = response.data["results"][0]
        self.assertEqual(row["student_id"], self.other_class_student.id)
        self.assertEqual(row["class_id"], self.class_b.id)
        self.assertIsNone(row["check_in"])

    def test_search_mode_matches_unique_code_and_status(self):
        self.arrived_student.refresh_from_db()
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(
            self.URL,
            {"date": self.today.isoformat(), "search": self.arrived_student.unique_code},
        )
        self.assertEqual(response.data["count"], 1)
        row = response.data["results"][0]
        self.assertEqual(row["student_id"], self.arrived_student.id)
        self.assertIsNotNone(row["check_in"])

    def test_search_pagination(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(
            self.URL, {"search": "a", "page": 1, "page_size": 1}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["page_size"], 1)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertGreaterEqual(response.data["count"], 2)
        self.assertGreaterEqual(response.data["num_pages"], 2)

    def test_invalid_date_returns_400(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(self.URL, {"date": "not-a-date"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class SessionAttendanceBulkUpsertTests(APITestCase):
    URL = "/api/v1/session-attendances/bulk_upsert/"

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="bulk_att_admin", role="admin", clerk_id="clerk_bulk_att_1"
        )
        from timetable.models import Class, TimetableSlot
        from people.models import Teacher, Subject

        self.class_obj = Class.objects.create(education_level="IG", cohort_identifier="B")
        self.teacher = Teacher.objects.create(name="Bulk Att Teacher")
        self.subject = Subject.objects.create(name="Bulk Att Subject")
        self.student_a = Student.objects.create(name="Bulk Att A")
        self.student_b = Student.objects.create(name="Bulk Att B")
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
            start_time=timezone.make_aware(
                datetime.combine(today, datetime.min.time().replace(hour=9, minute=0))
            ),
            end_time=timezone.make_aware(
                datetime.combine(today, datetime.min.time().replace(hour=10, minute=0))
            ),
        )

    def test_bulk_upsert_create_with_records_wrapper(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            self.URL,
            {
                "records": [
                    {
                        "session_id": self.session.id,
                        "student_id": self.student_a.id,
                        "status": "present",
                    },
                    {
                        "session_id": self.session.id,
                        "student_id": self.student_b.id,
                        "status": "absent",
                    },
                ]
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["created_count"], 2)
        self.assertEqual(response.data["updated_count"], 0)
        self.assertEqual(
            SessionAttendance.objects.get(
                session=self.session, student=self.student_a
            ).status,
            "present",
        )

    def test_bulk_upsert_update_existing(self):
        SessionAttendance.objects.create(
            session=self.session, student=self.student_a, status="absent"
        )
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            self.URL,
            [
                {
                    "session_id": self.session.id,
                    "student_id": self.student_a.id,
                    "status": "late",
                }
            ],
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["created_count"], 0)
        self.assertEqual(response.data["updated_count"], 1)
        self.assertEqual(
            SessionAttendance.objects.get(
                session=self.session, student=self.student_a
            ).status,
            "late",
        )

    def test_bulk_upsert_invalid_status(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            self.URL,
            {
                "records": [
                    {
                        "session_id": self.session.id,
                        "student_id": self.student_a.id,
                        "status": "not-a-status",
                    }
                ]
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)
        self.assertFalse(
            SessionAttendance.objects.filter(
                session=self.session, student=self.student_a
            ).exists()
        )


class AdHocSessionAttendanceBulkUpsertTests(APITestCase):
    URL = "/api/v1/adhoc-session-attendances/bulk_upsert/"

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="bulk_adhoc_admin", role="admin", clerk_id="clerk_bulk_adhoc_1"
        )
        from people.models import Teacher, Subject

        self.teacher = Teacher.objects.create(name="Bulk Adhoc Teacher")
        self.subject = Subject.objects.create(name="Bulk Adhoc Subject")
        self.student_a = Student.objects.create(name="Bulk Adhoc A")
        self.student_b = Student.objects.create(name="Bulk Adhoc B")
        self.adhoc = AdHocSession.objects.create(
            teacher=self.teacher,
            subject=self.subject,
            date=timezone.localdate(),
            start_time="14:00",
            end_time="15:00",
        )

    def test_bulk_upsert_create_with_records_wrapper(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            self.URL,
            {
                "records": [
                    {
                        "adhoc_session_id": self.adhoc.id,
                        "student_id": self.student_a.id,
                        "status": "present",
                    },
                    {
                        "adhoc_session_id": self.adhoc.id,
                        "student_id": self.student_b.id,
                        "status": "excused",
                    },
                ]
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["created_count"], 2)
        self.assertEqual(response.data["updated_count"], 0)
        self.assertEqual(
            AdHocSessionAttendance.objects.get(
                ad_hoc_session=self.adhoc, student=self.student_a
            ).status,
            "present",
        )

    def test_bulk_upsert_update_existing(self):
        AdHocSessionAttendance.objects.create(
            ad_hoc_session=self.adhoc, student=self.student_a, status="absent"
        )
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            self.URL,
            [
                {
                    "adhoc_session_id": self.adhoc.id,
                    "student_id": self.student_a.id,
                    "status": "late",
                }
            ],
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["created_count"], 0)
        self.assertEqual(response.data["updated_count"], 1)
        self.assertEqual(
            AdHocSessionAttendance.objects.get(
                ad_hoc_session=self.adhoc, student=self.student_a
            ).status,
            "late",
        )

    def test_bulk_upsert_invalid_status(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            self.URL,
            {
                "records": [
                    {
                        "adhoc_session_id": self.adhoc.id,
                        "student_id": self.student_a.id,
                        "status": "nope",
                    }
                ]
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)
        self.assertFalse(
            AdHocSessionAttendance.objects.filter(
                ad_hoc_session=self.adhoc, student=self.student_a
            ).exists()
        )


class PageBoundaryListTests(APITestCase):
    """page_size=2 → page1/page2 disjoint IDs, stable count on hot list ViewSets."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username="page_bound_admin", role="admin", clerk_id="clerk_page_bound_1"
        )
        from timetable.models import Class, TimetableSlot
        from people.models import Teacher, Subject

        self.class_obj = Class.objects.create(education_level="IG", cohort_identifier="P")
        self.teacher = Teacher.objects.create(name="Page Bound Teacher")
        self.subject = Subject.objects.create(name="Page Bound Subject")
        self.slot = TimetableSlot.objects.create(
            class_obj=self.class_obj,
            subject=self.subject,
            teacher=self.teacher,
            day_of_week=2,
            start_time="11:00",
            end_time="12:00",
        )
        base = date(2026, 8, 1)
        self.sessions = []
        for i in range(5):
            d = base + timedelta(days=i)
            self.sessions.append(
                Session.objects.create(
                    timetable_slot=self.slot,
                    teacher=self.teacher,
                    class_obj=self.class_obj,
                    start_time=timezone.make_aware(
                        datetime.combine(d, datetime.min.time().replace(hour=11))
                    ),
                    end_time=timezone.make_aware(
                        datetime.combine(d, datetime.min.time().replace(hour=12))
                    ),
                )
            )
        self.students = [
            Student.objects.create(name=f"Page Bound Student {i}") for i in range(5)
        ]
        for i, student in enumerate(self.students):
            CheckIn.objects.create(
                student=student,
                date=base + timedelta(days=i),
                check_in_type="manual",
                checked_by=self.admin,
            )

    def _assert_page_boundary(self, url):
        self.client.force_authenticate(user=self.admin)
        page1 = self.client.get(url, {"page": 1, "page_size": 2})
        page2 = self.client.get(url, {"page": 2, "page_size": 2})
        self.assertEqual(page1.status_code, status.HTTP_200_OK, msg=url)
        self.assertEqual(page2.status_code, status.HTTP_200_OK, msg=url)
        self.assertEqual(page1.data["count"], page2.data["count"], msg=url)
        self.assertGreaterEqual(page1.data["count"], 4, msg=url)
        self.assertEqual(len(page1.data["results"]), 2, msg=url)
        self.assertEqual(len(page2.data["results"]), 2, msg=url)
        ids1 = {row["id"] for row in page1.data["results"]}
        ids2 = {row["id"] for row in page2.data["results"]}
        self.assertTrue(ids1.isdisjoint(ids2), msg=f"{url}: {ids1} vs {ids2}")

    def test_sessions_page_boundary(self):
        self._assert_page_boundary("/api/v1/sessions/")

    def test_check_ins_page_boundary(self):
        self._assert_page_boundary("/api/v1/check-ins/")

