from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models, transaction
from django.db.models import F, Q
from django.db.models.functions import Round
from django.db.models.lookups import Exact


def grade_for(percentage):
    """Continuous bands: B is 70 <= percentage < 80, and so on."""
    for minimum, letter in ((80, "A"), (70, "B"), (60, "C"), (50, "D")):
        if percentage >= minimum:
            return letter
    return "F"


def rounded(value):
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class ValidatedModel(models.Model):
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class AcademicYear(ValidatedModel):
    name = models.CharField(max_length=30, unique=True)
    start_date = models.DateField()
    end_date = models.DateField()

    class Meta:
        ordering = ["-start_date", "pk"]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__gt=F("start_date")),
                name="academic_year_dates_valid",
            ),
        ]

    def clean(self):
        if self.start_date and self.end_date and self.end_date <= self.start_date:
            raise ValidationError({"end_date": "Must be after start_date."})

    def save(self, *args, **kwargs):
        # The year and its two semesters are created in one transaction.
        with transaction.atomic():
            super().save(*args, **kwargs)
            for number in (1, 2):
                Term.objects.get_or_create(academic_year=self, number=number)

    def __str__(self):
        return self.name


class Term(ValidatedModel):
    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.PROTECT, related_name="terms"
    )
    number = models.PositiveSmallIntegerField(
        choices=[(1, "Semester 1"), (2, "Semester 2")]
    )

    class Meta:
        ordering = ["academic_year_id", "number"]
        constraints = [
            models.UniqueConstraint(
                fields=["academic_year", "number"], name="unique_year_semester"
            ),
            models.CheckConstraint(
                condition=Q(number__in=[1, 2]), name="semester_one_or_two"
            ),
        ]

    def __str__(self):
        return f"{self.academic_year} - {self.get_number_display()}"


class SubjectOffering(ValidatedModel):
    # Reuse existing entities. Do not introduce another Student or Class model.
    class_obj = models.ForeignKey(
        "timetable.Class", on_delete=models.PROTECT, related_name="academic_offerings"
    )
    subject = models.ForeignKey(
        "people.Subject", on_delete=models.PROTECT, related_name="academic_offerings"
    )
    term = models.ForeignKey(Term, on_delete=models.PROTECT, related_name="offerings")
    # Explicitly supplied, rather than assuming the school's preferred split.
    exam_weight = models.DecimalField(
        max_digits=5, decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    quiz_weight = models.DecimalField(
        max_digits=5, decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    assignment_weight = models.DecimalField(
        max_digits=5, decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )

    class Meta:
        ordering = ["term_id", "class_obj_id", "subject_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["class_obj", "subject", "term"], name="unique_class_subject_term"
            ),
            models.CheckConstraint(
                condition=(Q(exam_weight__gte=0, exam_weight__lte=100)
                           & Q(quiz_weight__gte=0, quiz_weight__lte=100)
                           & Q(assignment_weight__gte=0, assignment_weight__lte=100)
                           & Exact(Round(F("exam_weight") + F("quiz_weight")
                                         + F("assignment_weight"), precision=2), Decimal("100"))),
                name="academic_weights_total_100",
            ),
        ]

    def clean(self):
        weights = (self.exam_weight, self.quiz_weight, self.assignment_weight)
        if all(w is not None for w in weights) and sum(weights) != Decimal("100"):
            raise ValidationError("Exam, quiz and assignment weights must sum to 100.")
        if self.pk:
            old = type(self).objects.get(pk=self.pk)
            if any(getattr(old, f) != getattr(self, f)
                   for f in ("class_obj_id", "subject_id", "term_id")):
                raise ValidationError("An offering's class, subject and term cannot change.")

    def __str__(self):
        return f"{self.class_obj} / {self.subject} / {self.term}"


class Assessment(ValidatedModel):
    class Kind(models.TextChoices):
        EXAM = "exam", "Exam"
        QUIZ = "quiz", "Quiz"
        ASSIGNMENT = "assignment", "Assignment"

    offering = models.ForeignKey(
        SubjectOffering, on_delete=models.PROTECT, related_name="assessments"
    )
    title = models.CharField(max_length=150)
    kind = models.CharField(max_length=12, choices=Kind.choices)
    max_marks = models.DecimalField(
        max_digits=8, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )

    class Meta:
        ordering = ["offering_id", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["offering", "title"], name="unique_offering_assessment_title"
            ),
            models.CheckConstraint(condition=Q(max_marks__gt=0), name="positive_max_marks"),
            models.CheckConstraint(
                condition=Q(kind__in=["exam", "quiz", "assignment"]),
                name="valid_assessment_kind",
            ),
        ]

    def clean(self):
        if self.pk:
            old = type(self).objects.get(pk=self.pk)
            if old.offering_id != self.offering_id:
                raise ValidationError({"offering": "Cannot change after creation."})
            if self.results.exists() and (old.kind != self.kind or old.max_marks != self.max_marks):
                raise ValidationError("Kind and maximum marks cannot change after marks exist.")

    def __str__(self):
        return self.title


class AssessmentResult(ValidatedModel):
    assessment = models.ForeignKey(
        Assessment, on_delete=models.PROTECT, related_name="results"
    )
    student = models.ForeignKey(
        "people.Student", on_delete=models.PROTECT, related_name="academic_results"
    )
    marks = models.DecimalField(
        max_digits=8, decimal_places=2, validators=[MinValueValidator(0)]
    )
    remarks = models.CharField(max_length=500, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="recorded_academic_results", editable=False,
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["assessment_id", "student_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["assessment", "student"], name="unique_assessment_student_mark"
            ),
            models.CheckConstraint(condition=Q(marks__gte=0), name="nonnegative_marks"),
        ]

    def clean(self):
        from timetable.models import ClassStudent

        if not self.assessment_id or not self.student_id:
            return
        # Fetch current maximum, even when a serializer cached the related object.
        assessment = Assessment.objects.select_related("offering").get(pk=self.assessment_id)
        if self.marks is not None and self.marks > assessment.max_marks:
            raise ValidationError({"marks": "Cannot exceed the assessment maximum."})
        if self.pk:
            old = type(self).objects.get(pk=self.pk)
            if old.student_id != self.student_id or old.assessment_id != self.assessment_id:
                raise ValidationError("Student and assessment cannot change after creation.")
        elif not ClassStudent.objects.filter(
            student_id=self.student_id, class_obj_id=assessment.offering.class_obj_id
        ).exists():
            raise ValidationError({"student": "Student is not enrolled in this class."})


class ReportCard(ValidatedModel):
    student = models.ForeignKey(
        "people.Student", on_delete=models.PROTECT, related_name="report_cards"
    )
    class_obj = models.ForeignKey(
        "timetable.Class", on_delete=models.PROTECT, related_name="report_cards"
    )
    term = models.ForeignKey(Term, on_delete=models.PROTECT, related_name="report_cards")
    revision = models.PositiveIntegerField()
    comments = models.TextField(blank=True)
    # Server-built snapshot; clients cannot supply grades or totals.
    snapshot = models.JSONField(default=dict, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="created_report_cards", editable=False,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True, editable=False)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="published_report_cards", editable=False,
    )

    class Meta:
        ordering = ["-created_at", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "class_obj", "term", "revision"],
                name="unique_student_report_revision",
            ),
            models.CheckConstraint(condition=Q(revision__gte=1), name="report_revision_positive"),
        ]

    def clean(self):
        if self.pk:
            old = type(self).objects.get(pk=self.pk)
            if old.published_at:
                raise ValidationError("Published reports are immutable; create a new revision.")
            if any(getattr(old, f) != getattr(self, f)
                   for f in ("student_id", "class_obj_id", "term_id", "revision")):
                raise ValidationError("Report identity cannot change after creation.")


def build_report_snapshot(student, class_obj, term):
    """Point-weighted categories, then category-weighted subject percentages.

    Missing marks block generation. Explicit zero is a valid score. Each
    subject is independent; this phase does not assume credits or GPA rules.
    """
    offerings = SubjectOffering.objects.filter(
        class_obj=class_obj, term=term
    ).select_related("subject").prefetch_related("assessments")
    marks = dict(AssessmentResult.objects.filter(
        student=student, assessment__offering__class_obj=class_obj,
        assessment__offering__term=term,
    ).values_list("assessment_id", "marks"))
    subjects = []
    for offering in offerings:
        total = Decimal("0")
        categories = []
        for kind in Assessment.Kind.values:
            weight = getattr(offering, f"{kind}_weight")
            assessments = [a for a in offering.assessments.all() if a.kind == kind]
            details = []
            if weight > 0:
                if not assessments:
                    raise ValidationError(f"{offering.subject}: no {kind} assessments configured.")
                missing = [a.title for a in assessments if a.pk not in marks]
                if missing:
                    raise ValidationError(f"{offering.subject}: missing marks for {', '.join(missing)}.")
                earned = sum((marks[a.pk] for a in assessments), Decimal("0"))
                maximum = sum((a.max_marks for a in assessments), Decimal("0"))
                percentage = earned / maximum * Decimal("100")
                total += percentage * weight / Decimal("100")
                details = [{"assessment_id": a.pk, "title": a.title,
                            "marks": str(marks[a.pk]), "max_marks": str(a.max_marks)}
                           for a in assessments]
            else:
                percentage = None
            categories.append({"kind": kind, "weight": str(weight),
                               "percentage": str(rounded(percentage)) if percentage is not None else None,
                               "assessments": details})
        # Grade the same rounded percentage displayed to the user.
        percentage = rounded(total)
        subjects.append({"subject_id": offering.subject_id,
                         "subject_name": offering.subject.name,
                         "percentage": str(percentage), "grade": grade_for(percentage),
                         "categories": categories})
    if not subjects:
        raise ValidationError("No subjects are configured for this class and term.")
    return {"schema_version": 1, "student_name": student.name,
            "student_code": student.unique_code, "class_name": str(class_obj),
            "academic_year": term.academic_year.name, "term": term.get_number_display(),
            "calculation": "Points within category; category percentages weighted per subject.",
            "rounding": "ROUND_HALF_UP to 2 decimal places before assigning the grade.",
            "grade_bands": {"A": ">=80", "B": ">=70,<80", "C": ">=60,<70",
                            "D": ">=50,<60", "F": "<50"},
            "subjects": subjects}
