from django.contrib import admin
from django.test import RequestFactory, TestCase
from django.urls import reverse

from people.models import Student, User
from timetable.models import Class, ClassStudent


class ClassStudentAdminTests(TestCase):
    def test_changelist_renders_with_and_without_enrollments(self):
        request = RequestFactory().get(reverse("admin:timetable_classstudent_changelist"))
        request.user = User(
            username="admin", is_active=True, is_staff=True, is_superuser=True,
        )
        model_admin = admin.site._registry[ClassStudent]

        response = model_admin.changelist_view(request)
        response.render()
        self.assertEqual(response.status_code, 200)

        class_obj = Class.objects.create(
            education_level="IG", cohort_identifier="K", cohort_sub_category="3",
        )
        student = Student.objects.create(name="Admin Render Student")
        ClassStudent.objects.create(class_obj=class_obj, student=student)

        response = model_admin.changelist_view(request)
        response.render()
        self.assertContains(response, "Admin Render Student")
        self.assertContains(response, "IG K3")
