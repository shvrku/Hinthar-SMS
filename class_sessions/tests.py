from datetime import date, datetime, timedelta
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from people.models import Student
from class_sessions.models import CheckIn, Session, SessionAttendance

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
        
        from timetable.models import Class
        from people.models import Teacher, Subject
        self.class_obj = Class.objects.create(education_level='IG', cohort_identifier='B')
        self.teacher = Teacher.objects.create(name="Mr. Smith")
        
        # Create today's session
        today = timezone.localdate()
        
        # Session 1: 09:00 - 10:00 (Student checks in at 09:10 -> present)
        # Session 2: 11:00 - 12:00 (Student checks in at 09:10 -> early/present) -> Actually logic says <= 15 mins after start -> present
        # Session 3: 08:00 - 09:00 (Student checks in at 09:10 -> after end -> absent)
        # Session 4: 08:30 - 09:30 (Student checks in at 09:10 -> > 15 mins after start, but before end -> late)
        
        self.session_present = Session.objects.create(
            teacher=self.teacher, class_obj=self.class_obj,
            start_time=timezone.make_aware(datetime.combine(today, datetime.min.time().replace(hour=9, minute=0))),
            end_time=timezone.make_aware(datetime.combine(today, datetime.min.time().replace(hour=10, minute=0)))
        )
        self.att_present = SessionAttendance.objects.create(session=self.session_present, student=self.student, status='absent')
        
        self.session_late = Session.objects.create(
            teacher=self.teacher, class_obj=self.class_obj,
            start_time=timezone.make_aware(datetime.combine(today, datetime.min.time().replace(hour=8, minute=30))),
            end_time=timezone.make_aware(datetime.combine(today, datetime.min.time().replace(hour=9, minute=30)))
        )
        self.att_late = SessionAttendance.objects.create(session=self.session_late, student=self.student, status='absent')
        
        self.session_absent = Session.objects.create(
            teacher=self.teacher, class_obj=self.class_obj,
            start_time=timezone.make_aware(datetime.combine(today, datetime.min.time().replace(hour=8, minute=0))),
            end_time=timezone.make_aware(datetime.combine(today, datetime.min.time().replace(hour=9, minute=0)))
        )
        self.att_absent = SessionAttendance.objects.create(session=self.session_absent, student=self.student, status='absent')
        
        # Session with manual override
        self.session_override = Session.objects.create(
            teacher=self.teacher, class_obj=self.class_obj,
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

