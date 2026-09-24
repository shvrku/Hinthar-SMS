from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response

from people.audit import AuditedViewSetMixin, log_event
from people.permissions import IsStaffOrAbove
from people.roles import is_active_account, is_staff_or_above
from timetable.models import ClassStudent

from .models import (
    AcademicYear, Term, SubjectOffering, Assessment, AssessmentResult, ReportCard,
    build_report_snapshot,
)
from .serializers import (
    AcademicYearSerializer, TermSerializer, SubjectOfferingSerializer,
    AssessmentSerializer, AssessmentResultSerializer, ReportCardSerializer,
)


class AcademicConflict(APIException):
    status_code = 409
    default_detail = "Conflicting academic record. Refresh the data and retry."


class AcademicQueryMixin:
    filter_fields = {}

    def get_queryset(self):
        qs = super().get_queryset()
        for parameter, lookup in self.filter_fields.items():
            value = self.request.query_params.get(parameter)
            if value is not None:
                try:
                    parsed = int(value)
                    if parsed < 1:
                        raise ValueError
                except (TypeError, ValueError):
                    raise ValidationError({parameter: "Must be a positive integer."})
                qs = qs.filter(**{lookup: parsed})
        return qs

    def handle_exception(self, exc):
        if isinstance(exc, DjangoValidationError):
            exc = ValidationError(
                exc.message_dict if hasattr(exc, "message_dict")
                else {"non_field_errors": exc.messages}
            )
        elif isinstance(exc, IntegrityError):
            exc = AcademicConflict()
        return super().handle_exception(exc)


class AcademicWriteViewSet(
    AcademicQueryMixin, AuditedViewSetMixin,
    mixins.CreateModelMixin, mixins.UpdateModelMixin,
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet,
):
    """Staff/admin writes; inherit Clerk authentication and global pagination.

    No DELETE endpoint. Term locks serialize academic API writes on PostgreSQL.
    SQLite remains suitable for single-user local work, not a lock-equivalent test.
    """
    permission_classes = [IsStaffOrAbove]
    audit_category = "other"
    audit_noun = "academic record"

    def term_for_write(self, values, instance=None):
        return None

    def lock_scope(self, values, instance=None):
        term_id = self.term_for_write(values, instance)
        if term_id:
            get_object_or_404(Term.objects.select_for_update(), pk=term_id)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            self.lock_scope(serializer.validated_data)
            # Revalidate after the lock, using fresh related model instances.
            return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        with transaction.atomic():
            self.lock_scope({}, instance)
            return super().update(request, *args, **kwargs)


class AcademicYearViewSet(AcademicWriteViewSet):
    queryset = AcademicYear.objects.prefetch_related("terms").all()
    serializer_class = AcademicYearSerializer
    audit_noun = "academic year"
    # Year identity/calendar is fixed for this first phase.
    http_method_names = ["get", "post", "head", "options"]


class TermViewSet(AcademicQueryMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Term.objects.select_related("academic_year").all()
    serializer_class = TermSerializer
    permission_classes = [IsStaffOrAbove]
    filter_fields = {"academic_year_id": "academic_year_id"}


class SubjectOfferingViewSet(AcademicWriteViewSet):
    queryset = SubjectOffering.objects.select_related("class_obj", "subject", "term").all()
    serializer_class = SubjectOfferingSerializer
    audit_noun = "subject offering"
    filter_fields = {"class_id": "class_obj_id", "subject_id": "subject_id", "term_id": "term_id"}

    def term_for_write(self, values, instance=None):
        return instance.term_id if instance else values["term"].pk


class AssessmentViewSet(AcademicWriteViewSet):
    queryset = Assessment.objects.select_related("offering").all()
    serializer_class = AssessmentSerializer
    audit_noun = "assessment"
    filter_fields = {"offering_id": "offering_id", "term_id": "offering__term_id",
                     "class_id": "offering__class_obj_id"}

    def term_for_write(self, values, instance=None):
        offering = instance.offering if instance else values["offering"]
        return offering.term_id


class AssessmentResultViewSet(AcademicWriteViewSet):
    queryset = AssessmentResult.objects.select_related("assessment__offering", "student").all()
    serializer_class = AssessmentResultSerializer
    audit_noun = "assessment result"
    filter_fields = {"student_id": "student_id", "assessment_id": "assessment_id",
                     "term_id": "assessment__offering__term_id",
                     "class_id": "assessment__offering__class_obj_id"}

    def term_for_write(self, values, instance=None):
        assessment = instance.assessment if instance else values["assessment"]
        return assessment.offering.term_id

    def perform_create(self, serializer):
        # recorded_by is read-only to the client; records the latest editor.
        serializer.save(recorded_by=self.request.user)
        self._log_instance("create", serializer.instance)

    def perform_update(self, serializer):
        serializer.save(recorded_by=self.request.user)
        self._log_instance("update", serializer.instance)


class CanReadReportCards(permissions.BasePermission):
    def has_permission(self, request, view):
        if not is_active_account(request.user):
            return False
        if is_staff_or_above(request.user):
            return True
        return (request.method in permissions.SAFE_METHODS
                and request.user.role == "student"
                and getattr(request.user, "student_profile", None) is not None)


class ReportCardViewSet(AcademicWriteViewSet):
    queryset = ReportCard.objects.select_related("student", "class_obj", "term__academic_year").all()
    serializer_class = ReportCardSerializer
    permission_classes = [CanReadReportCards]
    audit_noun = "report card"
    http_method_names = ["get", "post", "head", "options"]
    filter_fields = {"student_id": "student_id", "class_id": "class_obj_id", "term_id": "term_id"}

    def get_queryset(self):
        qs = super().get_queryset()
        if is_staff_or_above(self.request.user):
            return qs
        # Applies to BOTH list and detail. Never trust a student_id query parameter.
        return qs.filter(student__user=self.request.user, published_at__isnull=False)

    def term_for_write(self, values, instance=None):
        return instance.term_id if instance else values["term"].pk

    def perform_create(self, serializer):
        values = serializer.validated_data
        student, class_obj, term = values["student"], values["class_obj"], values["term"]
        prior = ReportCard.objects.filter(student=student, class_obj=class_obj, term=term)
        # Existing reports allow corrections after a student has transferred.
        if not ClassStudent.objects.filter(student=student, class_obj=class_obj).exists() and not prior.exists():
            raise ValidationError({"student": "Student is not enrolled in this class."})
        revision = (prior.aggregate(last=Max("revision"))["last"] or 0) + 1
        serializer.save(
            revision=revision, created_by=self.request.user,
            snapshot=build_report_snapshot(student, class_obj, term),
        )
        self._log_instance("create", serializer.instance)

    @action(detail=True, methods=["post"], permission_classes=[IsStaffOrAbove])
    def publish(self, request, pk=None):
        initial = self.get_object()
        with transaction.atomic():
            get_object_or_404(Term.objects.select_for_update(), pk=initial.term_id)
            report = self.get_object()
            if report.published_at:
                return Response(self.get_serializer(report).data)
            if ReportCard.objects.filter(
                student=report.student, class_obj=report.class_obj, term=report.term,
                revision__gt=report.revision, published_at__isnull=False,
            ).exists():
                raise ValidationError("A newer revision is already published.")
            # Refresh draft calculations at publication, then retain the snapshot.
            report.snapshot = build_report_snapshot(report.student, report.class_obj, report.term)
            report.published_at = timezone.now()
            report.published_by = request.user
            report.save()
            log_event(user=request.user, category="other", action="update",
                      summary=f"Published report card #{report.pk} revision {report.revision}",
                      model_name="ReportCard", record_id=report.pk)
            return Response(self.get_serializer(report).data)
