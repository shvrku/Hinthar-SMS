from datetime import date
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from people.models import Student
from class_sessions.models import CheckIn

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

