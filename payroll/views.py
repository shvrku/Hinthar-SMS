from django.db.models.deletion import ProtectedError
from rest_framework import permissions, serializers, viewsets

from .models import FeePayment, StaffSalary, StudentFee
from .serializers import FeePaymentSerializer, StaffSalarySerializer, StudentFeeSerializer


class IsFinanceAdministrator(permissions.BasePermission):
    """Use the existing Django role, with a fallback for standard Django users."""
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated or not user.is_active:
            return False
        if user.is_superuser:
            return True
        if hasattr(user, "role"):
            return user.role == "admin"
        return user.is_staff


class FinanceViewSet(viewsets.ModelViewSet):
    # Inherits the project's configured authentication (including Clerk, if configured).
    permission_classes = [IsFinanceAdministrator]
    id_filters = {}
    status_choices = ()
    status_lookup = "status"

    def get_queryset(self):
        queryset = super().get_queryset()
        for parameter, field in self.id_filters.items():
            value = self.request.query_params.get(parameter)
            if value is not None:
                try:
                    value = int(value)
                    if value <= 0:
                        raise ValueError
                except (TypeError, ValueError):
                    raise serializers.ValidationError({parameter: "Must be a positive integer."})
                queryset = queryset.filter(**{field: value})
        status = self.request.query_params.get("status")
        if status is not None and self.status_choices:
            if status not in self.status_choices:
                raise serializers.ValidationError({"status": "Invalid status."})
            queryset = queryset.filter(**{self.status_lookup: status})
        return queryset

    def perform_destroy(self, instance):
        try:
            instance.delete()
        except ProtectedError as exc:
            raise serializers.ValidationError(
                {"detail": "Cannot delete a record with related payments."}
            ) from exc


class StudentFeeViewSet(FinanceViewSet):
    serializer_class = StudentFeeSerializer
    id_filters = {"student_id": "student_id", "academic_year_id": "academic_year_id"}
    status_choices = StudentFee.Status.values
    status_lookup = "_current_status"

    def get_queryset(self):
        # Build this per request so today's date is never frozen at import time.
        self.queryset = StudentFee.objects.with_payment_status().select_related(
            "student", "academic_year"
        ).prefetch_related("payments")
        return super().get_queryset()


class FeePaymentViewSet(FinanceViewSet):
    queryset = FeePayment.objects.select_related("student_fee").all()
    serializer_class = FeePaymentSerializer
    id_filters = {"student_fee_id": "student_fee_id", "student_id": "student_fee__student_id"}


class StaffSalaryViewSet(FinanceViewSet):
    queryset = StaffSalary.objects.select_related("staff").all()
    serializer_class = StaffSalarySerializer
    id_filters = {"staff_id": "staff_id"}
    status_choices = StaffSalary.Status.values
