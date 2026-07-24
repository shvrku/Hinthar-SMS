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


from people.models import Teacher, Staff
from django.utils import timezone

class UniqueCodeTest(TestCase):
    def test_student_unique_code_format(self):
        student = Student.objects.create(name="Alice")
        year_str = f"{timezone.now().year % 100:02d}"
        self.assertEqual(student.unique_code, f"HIS{year_str}-00001")

    def test_teacher_unique_code_format(self):
        teacher = Teacher.objects.create(name="Bob")
        year_str = f"{timezone.now().year % 100:02d}"
        self.assertEqual(teacher.unique_code, f"HIST{year_str}-00001")

    def test_staff_unique_code_format(self):
        staff = Staff.objects.create(name="Charlie")
        year_str = f"{timezone.now().year % 100:02d}"
        self.assertEqual(staff.unique_code, f"HISS{year_str}-00001")

    def test_sequential_numbers_in_same_year(self):
        s1 = Student.objects.create(name="Student 1")
        s2 = Student.objects.create(name="Student 2")
        year_str = f"{timezone.now().year % 100:02d}"
        self.assertEqual(s1.unique_code, f"HIS{year_str}-00001")
        self.assertEqual(s2.unique_code, f"HIS{year_str}-00002")

    def test_custom_school_code(self):
        student = Student.objects.create(name="David", school_code="SPD")
        year_str = f"{timezone.now().year % 100:02d}"
        self.assertEqual(student.unique_code, f"SPD{year_str}-00001")

    def test_unique_code_not_overwritten_on_save(self):
        student = Student.objects.create(name="Eve")
        code = student.unique_code
        student.name = "Eve Updated"
        student.save()
        self.assertEqual(student.unique_code, code)

    def test_gap_deletion_does_not_reuse_sequence(self):
        s1 = Student.objects.create(name="S1")
        s2 = Student.objects.create(name="S2")
        year_str = f"{timezone.now().year % 100:02d}"
        self.assertEqual(s1.unique_code, f"HIS{year_str}-00001")
        self.assertEqual(s2.unique_code, f"HIS{year_str}-00002")
        s1.delete()
        s3 = Student.objects.create(name="S3")
        self.assertEqual(s3.unique_code, f"HIS{year_str}-00003")

    def test_exam_candidate_number_optional(self):
        s = Student.objects.create(name="Frank")
        self.assertIsNone(s.exam_candidate_number)
        s.exam_candidate_number = "EXAM-2026-99"
        s.save()
        self.assertEqual(s.exam_candidate_number, "EXAM-2026-99")


from people.serializers import StudentSerializer, TeacherSerializer, StaffSerializer

class SchoolCodeValidationTest(TestCase):
    def test_valid_school_codes_pass_validation(self):
        for code in ['HIS', 'SPD', 'SPN', 'YWM']:
            serializer = StudentSerializer(data={'name': 'Test', 'school_code': code})
            self.assertTrue(serializer.is_valid(), f"Failed for code: {code}")

    def test_invalid_school_code_fails_validation(self):
        serializer = StudentSerializer(data={'name': 'Test', 'school_code': 'INVALID'})
        self.assertFalse(serializer.is_valid())
        self.assertIn('school_code', serializer.errors)

    def test_missing_school_code_fails_validation(self):
        serializer = StudentSerializer(data={'name': 'Test'})
        self.assertFalse(serializer.is_valid())
        self.assertIn('school_code', serializer.errors)

    def test_teacher_school_code_required(self):
        serializer = TeacherSerializer(data={'name': 'Teacher Test', 'school_code': 'SPD'})
        self.assertTrue(serializer.is_valid())

    def test_staff_school_code_required(self):
        serializer = StaffSerializer(data={'name': 'Staff Test', 'school_code': 'YWM'})
        self.assertTrue(serializer.is_valid())


