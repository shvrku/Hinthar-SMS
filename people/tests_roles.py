from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIRequestFactory, APITestCase, APIClient

from people.authentication import ClerkJWTAuthentication
from people.models import Student
from people.permissions import IsStaffOrAbove, CanCheckIn, IsAdmin
from people.roles import ROLE_RANK, is_staff_or_above, can_check_in

User = get_user_model()


class RoleHelpersTest(TestCase):
    def test_rank_order(self):
        self.assertLess(ROLE_RANK['pending'], ROLE_RANK['student'])
        self.assertLess(ROLE_RANK['terminal'], ROLE_RANK['staff'])
        self.assertLess(ROLE_RANK['staff'], ROLE_RANK['admin'])

    def test_staff_or_above(self):
        staff = User.objects.create_user(username='s', role='staff', clerk_id='c_s')
        pending = User.objects.create_user(username='p', role='pending', clerk_id='c_p')
        terminal = User.objects.create_user(username='t', role='terminal', clerk_id='c_t')
        self.assertTrue(is_staff_or_above(staff))
        self.assertFalse(is_staff_or_above(pending))
        self.assertFalse(is_staff_or_above(terminal))
        self.assertTrue(can_check_in(terminal))
        self.assertFalse(can_check_in(pending))


class StaffOrAbovePermissionTest(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.permission = IsStaffOrAbove()

    def test_anonymous_denied(self):
        request = self.factory.get('/api/v1/students/')
        request.user = AnonymousUser()
        self.assertFalse(self.permission.has_permission(request, None))

    def test_pending_denied(self):
        request = self.factory.get('/api/v1/students/')
        request.user = User.objects.create_user(username='pend', role='pending', clerk_id='c_pend')
        self.assertFalse(self.permission.has_permission(request, None))

    def test_student_denied(self):
        request = self.factory.get('/api/v1/students/')
        request.user = User.objects.create_user(username='stu', role='student', clerk_id='c_stu')
        self.assertFalse(self.permission.has_permission(request, None))

    def test_terminal_denied_for_staff_routes(self):
        request = self.factory.get('/api/v1/students/')
        request.user = User.objects.create_user(username='term', role='terminal', clerk_id='c_term')
        self.assertFalse(self.permission.has_permission(request, None))

    def test_staff_allowed(self):
        request = self.factory.get('/api/v1/students/')
        request.user = User.objects.create_user(username='staff', role='staff', clerk_id='c_staff')
        self.assertTrue(self.permission.has_permission(request, None))

    def test_admin_allowed(self):
        request = self.factory.get('/api/v1/students/')
        request.user = User.objects.create_user(username='adm', role='admin', clerk_id='c_adm')
        self.assertTrue(self.permission.has_permission(request, None))


class CanCheckInPermissionTest(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.permission = CanCheckIn()

    def test_terminal_allowed(self):
        request = self.factory.post('/api/v1/check-ins/qr/')
        request.user = User.objects.create_user(username='term2', role='terminal', clerk_id='c_term2')
        self.assertTrue(self.permission.has_permission(request, None))

    def test_teacher_denied(self):
        request = self.factory.post('/api/v1/check-ins/qr/')
        request.user = User.objects.create_user(username='teach', role='teacher', clerk_id='c_teach')
        self.assertFalse(self.permission.has_permission(request, None))


class IsAdminPermissionTest(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.permission = IsAdmin()

    def test_staff_denied(self):
        request = self.factory.patch('/api/v1/users/1/')
        request.user = User.objects.create_user(username='staff2', role='staff', clerk_id='c_staff2')
        self.assertFalse(self.permission.has_permission(request, None))

    def test_admin_allowed(self):
        request = self.factory.patch('/api/v1/users/1/')
        request.user = User.objects.create_user(username='adm2', role='admin', clerk_id='c_adm2')
        self.assertTrue(self.permission.has_permission(request, None))


class StaffRouteRoleDenialTests(APITestCase):
    """SEC-H3: pending/terminal must get 403 on staff-default API routes."""

    def setUp(self):
        self.client = APIClient()
        self.pending = User.objects.create_user(
            username='deny_pending', role='pending', clerk_id='clerk_deny_pending'
        )
        self.terminal = User.objects.create_user(
            username='deny_terminal', role='terminal', clerk_id='clerk_deny_terminal'
        )
        Student.objects.create(name='Gate Student')

    def test_pending_denied_students_list(self):
        self.client.force_authenticate(user=self.pending)
        res = self.client.get('/api/v1/students/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_terminal_denied_students_list(self):
        self.client.force_authenticate(user=self.terminal)
        res = self.client.get('/api/v1/students/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_pending_denied_sessions_list(self):
        self.client.force_authenticate(user=self.pending)
        res = self.client.get('/api/v1/sessions/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_terminal_denied_sessions_list(self):
        self.client.force_authenticate(user=self.terminal)
        res = self.client.get('/api/v1/sessions/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_terminal_denied_teachers_list(self):
        self.client.force_authenticate(user=self.terminal)
        res = self.client.get('/api/v1/teachers/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)


class InactiveUserAuthTests(APITestCase):
    """SEC-H1: deactivated users cannot authenticate via mock auth."""

    @override_settings(DEBUG=True, ENABLE_MOCK_AUTH=True)
    def test_inactive_mock_user_rejected(self):
        user = User.objects.create_user(
            username='user_mock_token_inactive',
            role='staff',
            clerk_id='clerk_mock_token_inactive',
            is_active=False,
        )
        auth = ClerkJWTAuthentication()
        factory = APIRequestFactory()
        request = factory.get('/api/v1/me/')
        request.META['HTTP_AUTHORIZATION'] = 'Bearer mock_token_inactive'
        with self.assertRaises(AuthenticationFailed):
            auth.authenticate(request)
        user.refresh_from_db()
        self.assertFalse(user.is_active)


class LastAdminGuardTests(APITestCase):
    """SEC-M3: last-admin protection applies to PUT and PATCH."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='only_admin', role='admin', clerk_id='clerk_only_admin'
        )

    def test_cannot_demote_last_admin_via_patch(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.patch(
            f'/api/v1/users/{self.admin.id}/',
            {'role': 'staff'},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.role, 'admin')

    def test_cannot_demote_last_admin_via_put(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.put(
            f'/api/v1/users/{self.admin.id}/',
            {
                'username': self.admin.username,
                'email': self.admin.email or 'admin@example.com',
                'role': 'staff',
                'is_active': True,
            },
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.role, 'admin')


class CheckInTokenListOmitTests(APITestCase):
    """SEC-H2: list omits token; detail includes it for staff."""

    def setUp(self):
        self.client = APIClient()
        self.staff = User.objects.create_user(
            username='token_staff', role='staff', clerk_id='clerk_token_staff'
        )
        self.student = Student.objects.create(name='Token Student')

    def test_list_omits_check_in_token(self):
        self.client.force_authenticate(user=self.staff)
        res = self.client.get('/api/v1/students/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data.get('results', res.data)
        self.assertTrue(len(results) >= 1)
        self.assertNotIn('check_in_token', results[0])

    def test_detail_includes_check_in_token(self):
        self.client.force_authenticate(user=self.staff)
        res = self.client.get(f'/api/v1/students/{self.student.id}/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('check_in_token', res.data)
        self.assertTrue(res.data['check_in_token'])

    def test_dedicated_token_endpoint(self):
        self.client.force_authenticate(user=self.staff)
        res = self.client.get(f'/api/v1/students/{self.student.id}/check_in_token/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('check_in_token', res.data)
