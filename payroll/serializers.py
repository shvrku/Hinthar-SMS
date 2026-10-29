from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from rest_framework import serializers

from .models import FeePayment, StaffSalary, StudentFee


class ValidatedModelSerializer(serializers.ModelSerializer):
    def save(self, **kwargs):
        try:
            with transaction.atomic():
                return super().save(**kwargs)
        except DjangoValidationError as exc:
            detail = exc.message_dict if hasattr(exc, "message_dict") else {
                "non_field_errors": exc.messages
            }
            raise serializers.ValidationError(detail) from exc
        except IntegrityError as exc:
            raise serializers.ValidationError(
                {"non_field_errors": ["A duplicate or conflicting record exists."]}
            ) from exc


class FeePaymentSerializer(ValidatedModelSerializer):
    class Meta:
        model = FeePayment
        fields = ["id", "student_fee", "amount_paid", "payment_date",
                  "payment_method", "reference_number"]
        read_only_fields = ["id"]


class StudentFeeSerializer(ValidatedModelSerializer):
    payments = FeePaymentSerializer(many=True, read_only=True)
    status = serializers.SerializerMethodField()

    def get_status(self, obj):
        return obj.current_status

    class Meta:
        model = StudentFee
        fields = ["id", "student", "academic_year", "fee_type", "amount_due",
                  "due_date", "status", "payments"]
        read_only_fields = ["id", "status", "payments"]


class StaffSalarySerializer(ValidatedModelSerializer):
    def validate_month(self, value):
        return value.replace(day=1)

    class Meta:
        model = StaffSalary
        fields = ["id", "staff", "month", "base_salary", "allowances",
                  "deductions", "net_salary", "status", "payment_date"]
        read_only_fields = ["id", "net_salary"]
