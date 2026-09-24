from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APIClient

from people.models import Student, Subject, User
from timetable.models import Class, ClassStudent
from .models import (
    AcademicYear, Term, SubjectOffering, Assessment, AssessmentResult,
    ReportCard, grade_for,
)


class AcademicsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user(username="academic-staff", clerk_id="test-staff", role="staff")
        cls.owner = User.objects.create_user(username="academic-student", clerk_id="test-student", role="student")
        cls.student = Student.objects.create(name="Test Student", user=cls.owner)
        cls.other = Student.objects.create(name="Other Student")
        cls.class_obj = Class.objects.create(education_level="Year1", cohort_identifier="A")
        ClassStudent.objects.create(student=cls.student, class_obj=cls.class_obj)
        cls.subject = Subject.objects.create(name="Mathematics")
        cls.year = AcademicYear.objects.create(name="2026-2027", start_date=date(2026, 6, 1), end_date=date(2027, 5, 31))
        cls.term = cls.year.terms.get(number=1)
        cls.offering = SubjectOffering.objects.create(
            class_obj=cls.class_obj, subject=cls.subject, term=cls.term,
            exam_weight=Decimal("60"), quiz_weight=Decimal("20"), assignment_weight=Decimal("20"),
        )
        cls.assessments = [Assessment.objects.create(
            offering=cls.offering, title=kind, kind=kind, max_marks=Decimal("100")
        ) for kind in Assessment.Kind.values]

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.staff)

    def post(self, path, data):
        return self.client.post(f"/api/v1/{path}/", data, format="json")

    def fill_marks(self, marks=(80, 70, 90)):
        for assessment, mark in zip(self.assessments, marks):
            result = self.post("assessment-results", {
                "assessment": assessment.pk, "student": self.student.pk, "marks": str(mark),
            })
            self.assertEqual(result.status_code, 201, result.data)

    def report(self):
        return self.post("report-cards", {"student": self.student.pk,
                                         "class_obj": self.class_obj.pk, "term": self.term.pk})

    def test_year_creates_exactly_two_terms_and_bad_dates_fail(self):
        response = self.post("academic-years", {
            "name": "2027-2028", "start_date": "2027-06-01", "end_date": "2028-05-31",
        })
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual([term["name"] for term in response.data["terms"]], ["Semester 1", "Semester 2"])
        invalid = self.post("academic-years", {
            "name": "invalid", "start_date": "2027-06-01", "end_date": "2027-01-01",
        })
        self.assertEqual(invalid.status_code, 400)
        self.assertFalse(AcademicYear.objects.filter(name="invalid").exists())
        with self.assertRaises(ValidationError):
            Term.objects.create(academic_year=self.year, number=3)
        self.assertEqual(self.client.delete(f"/api/v1/terms/{self.term.pk}/").status_code, 405)

    def test_weights_validated_on_partial_update(self):
        response = self.client.patch(f"/api/v1/subject-offerings/{self.offering.pk}/", {"exam_weight": "70"}, format="json")
        self.assertEqual(response.status_code, 400, response.data)
        self.offering.refresh_from_db()
        self.assertEqual(self.offering.exam_weight, Decimal("60"))

    def test_fractional_weights(self):
        for exam, quiz, assignment in [("33.33", "33.33", "33.34"),
                                       ("0.10", "0.20", "99.70"),
                                       ("40.10", "20.20", "39.70")]:
            response = self.client.patch(f"/api/v1/subject-offerings/{self.offering.pk}/", {
                "exam_weight": exam, "quiz_weight": quiz, "assignment_weight": assignment,
            }, format="json")
            self.assertEqual(response.status_code, 200, response.data)

    def test_database_constraints(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            SubjectOffering.objects.filter(pk=self.offering.pk).update(exam_weight=80)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Term.objects.bulk_create([Term(academic_year=self.year, number=3)])

    def test_marks_require_membership_and_range(self):
        for student, marks in [(self.other.pk, "30"), (self.student.pk, "101"), (self.student.pk, "-1")]:
            response = self.post("assessment-results", {"student": student, "assessment": self.assessments[0].pk, "marks": marks})
            self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(AssessmentResult.objects.count(), 0)

    def test_duplicate_marks_and_spoofed_actor(self):
        data = {"student": self.student.pk, "assessment": self.assessments[0].pk,
                "marks": "80", "recorded_by": self.owner.pk}
        response = self.post("assessment-results", data)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["recorded_by"], self.staff.pk)
        self.assertEqual(self.post("assessment-results", data).status_code, 400)

    def test_assessment_maximum_cannot_change_after_marks(self):
        self.fill_marks()
        response = self.client.patch(f"/api/v1/assessments/{self.assessments[0].pk}/", {"max_marks": "10"}, format="json")
        self.assertEqual(response.status_code, 400, response.data)

    def test_missing_marks_block_report(self):
        response = self.report()
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(ReportCard.objects.count(), 0)

    def test_weighted_report_and_grade(self):
        self.fill_marks()
        response = self.report()
        self.assertEqual(response.status_code, 201, response.data)
        subject = response.data["snapshot"]["subjects"][0]
        self.assertEqual(subject["percentage"], "80.00")
        self.assertEqual(subject["grade"], "A")
        self.assertEqual(response.data["status"], "draft")

    def test_points_weighted_within_category(self):
        self.fill_marks()
        extra = Assessment.objects.create(offering=self.offering, title="Short quiz", kind="quiz", max_marks=Decimal("10"))
        AssessmentResult.objects.create(assessment=extra, student=self.student, marks=Decimal("0"))
        response = self.report()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["snapshot"]["subjects"][0]["percentage"], "78.73")

    def test_grade_boundaries(self):
        for value, grade in [(0, "F"), (49.99, "F"), (50, "D"), (59.99, "D"), (60, "C"),
                             (69.99, "C"), (70, "B"), (79.99, "B"), (80, "A"), (100, "A")]:
            self.assertEqual(grade_for(Decimal(str(value))), grade)

    def test_zero_scores_and_zero_weight_categories(self):
        self.offering.exam_weight = Decimal("100")
        self.offering.quiz_weight = self.offering.assignment_weight = Decimal("0")
        self.offering.save()
        AssessmentResult.objects.create(assessment=self.assessments[0], student=self.student, marks=Decimal("0"))
        response = self.report()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["snapshot"]["subjects"][0]["grade"], "F")

    def test_student_sees_only_own_published_reports(self):
        self.fill_marks()
        report_id = self.report().data["id"]
        ClassStudent.objects.create(student=self.other, class_obj=self.class_obj)
        for assessment in self.assessments:
            AssessmentResult.objects.create(assessment=assessment, student=self.other, marks=Decimal("100"))
        other_response = self.post("report-cards", {"student": self.other.pk, "class_obj": self.class_obj.pk, "term": self.term.pk})
        other_id = other_response.data["id"]
        self.post(f"report-cards/{other_id}/publish", {})
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.get(f"/api/v1/report-cards/{report_id}/").status_code, 404)
        self.assertEqual(self.post(f"report-cards/{report_id}/publish", {}).status_code, 403)
        self.assertEqual(self.report().status_code, 403)
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.post(f"report-cards/{report_id}/publish", {}).status_code, 200)
        self.client.force_authenticate(self.owner)
        response = self.client.get("/api/v1/report-cards/")
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], report_id)
        self.assertEqual(self.client.get(f"/api/v1/report-cards/{other_id}/").status_code, 404)
        self.assertEqual(self.client.get("/api/v1/assessment-results/").status_code, 403)
        self.assertEqual(self.client.get(f"/api/v1/report-cards/?student_id={self.other.pk}").data["count"], 0)

    def test_denied_roles_and_inactive_staff(self):
        for role in ("terminal", "pending", "teacher"):
            user = User.objects.create_user(username=role, clerk_id=f"test-{role}", role=role)
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get("/api/v1/report-cards/").status_code, 403)
            self.assertEqual(self.client.get("/api/v1/assessments/").status_code, 403)
        self.staff.is_active = False
        self.staff.save()
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.get("/api/v1/report-cards/").status_code, 403)
        self.client.force_authenticate(user=None)
        self.assertIn(self.client.get("/api/v1/report-cards/").status_code, (401, 403))

    def test_publish_refreshes_draft_and_snapshot_survives_edits(self):
        self.fill_marks()
        report_id = self.report().data["id"]
        result = AssessmentResult.objects.get(assessment=self.assessments[0], student=self.student)
        response = self.client.patch(f"/api/v1/assessment-results/{result.pk}/", {"marks": "100"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        published = self.post(f"report-cards/{report_id}/publish", {})
        self.assertEqual(published.status_code, 200, published.data)
        self.assertEqual(published.data["snapshot"]["subjects"][0]["percentage"], "92.00")
        self.client.patch(f"/api/v1/assessment-results/{result.pk}/", {"marks": "0"}, format="json")
        again = self.post(f"report-cards/{report_id}/publish", {})
        self.assertEqual(again.data["snapshot"], published.data["snapshot"])
        revised = self.report()
        self.assertEqual(revised.data["revision"], 2)
        self.assertEqual(revised.data["snapshot"]["subjects"][0]["percentage"], "32.00")
        report = ReportCard.objects.get(pk=report_id)
        report.comments = "tamper"
        with self.assertRaises(ValidationError):
            report.save()

    def test_report_retained_after_current_enrollment_removed(self):
        self.fill_marks()
        report_id = self.report().data["id"]
        self.post(f"report-cards/{report_id}/publish", {})
        ClassStudent.objects.filter(student=self.student).delete()
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.get(f"/api/v1/report-cards/{report_id}/").status_code, 200)

    def test_invalid_filter_returns_400(self):
        response = self.client.get("/api/v1/assessments/?term_id=abc")
        self.assertEqual(response.status_code, 400)

    def test_clerk_authentication_is_inherited(self):
        from people.authentication import ClerkJWTAuthentication
        from .views import AssessmentViewSet, ReportCardViewSet
        self.assertIn(ClerkJWTAuthentication, AssessmentViewSet.authentication_classes)
        self.assertIn(ClerkJWTAuthentication, ReportCardViewSet.authentication_classes)
