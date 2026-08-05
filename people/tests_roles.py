from django.test import TestCase
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework.test import APIRequestFactory

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
