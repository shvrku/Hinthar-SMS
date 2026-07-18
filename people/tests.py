from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory
from people.models import Student
from people.permissions import IsAdminOrReadOnlyAuthenticated

User = get_user_model()

class StudentModelTest(TestCase):
    def test_check_in_token_is_automatically_generated(self):
        """Test that a check-in token is generated upon creating a student."""
        student = Student.objects.create(name="Test Student")
        self.assertIsNotNone(student.check_in_token)
        self.assertGreater(len(student.check_in_token), 0)

    def test_regenerate_check_in_token(self):
        """Test that regenerating check-in token updates the database."""
        student = Student.objects.create(name="Test Student")
        old_token = student.check_in_token
        student.regenerate_check_in_token()
        self.assertNotEqual(student.check_in_token, old_token)


from django.contrib.auth.models import AnonymousUser

class IsAdminOrReadOnlyAuthenticatedPermissionTest(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.permission = IsAdminOrReadOnlyAuthenticated()
        
    def test_unauthenticated_request_is_denied(self):
        request = self.factory.get('/api/v1/students/')
        request.user = AnonymousUser()
        self.assertFalse(self.permission.has_permission(request, None))

    def test_authenticated_read_is_allowed(self):
        request = self.factory.get('/api/v1/students/')
        request.user = User.objects.create_user(username="student_user", role="student", clerk_id="c_1")
        self.assertTrue(self.permission.has_permission(request, None))

    def test_authenticated_write_for_non_admin_is_denied(self):
        request = self.factory.post('/api/v1/students/')
        request.user = User.objects.create_user(username="student_user2", role="student", clerk_id="c_2")
        self.assertFalse(self.permission.has_permission(request, None))

    def test_admin_write_is_allowed(self):
        request = self.factory.post('/api/v1/students/')
        request.user = User.objects.create_user(username="admin_user", role="admin", clerk_id="c_3")
        self.assertTrue(self.permission.has_permission(request, None))


class StudentSerializerTest(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.student_user = User.objects.create_user(username="student_user", role="student", clerk_id="s_1")
        self.other_student_user = User.objects.create_user(username="student_user2", role="student", clerk_id="s_2")
        self.terminal_user = User.objects.create_user(username="terminal_user", role="terminal", clerk_id="t_1")
        self.teacher_user = User.objects.create_user(username="teacher_user", role="teacher", clerk_id="te_1")
        
        self.student = Student.objects.create(name="Owned Student", user=self.student_user)
        from people.serializers import StudentSerializer
        self.serializer_class = StudentSerializer

    def test_token_visible_to_student_owner(self):
        request = self.factory.get('/api/v1/students/')
        request.user = self.student_user
        serializer = self.serializer_class(self.student, context={'request': request})
        self.assertIn('check_in_token', serializer.data)

    def test_token_hidden_from_other_students(self):
        request = self.factory.get('/api/v1/students/')
        request.user = self.other_student_user
        serializer = self.serializer_class(self.student, context={'request': request})
        self.assertNotIn('check_in_token', serializer.data)

    def test_token_visible_to_terminal_role(self):
        request = self.factory.get('/api/v1/students/')
        request.user = self.terminal_user
        serializer = self.serializer_class(self.student, context={'request': request})
        self.assertIn('check_in_token', serializer.data)

    def test_token_hidden_from_teacher_role(self):
        request = self.factory.get('/api/v1/students/')
        request.user = self.teacher_user
        serializer = self.serializer_class(self.student, context={'request': request})
        self.assertNotIn('check_in_token', serializer.data)
