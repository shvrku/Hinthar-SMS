from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import Case, F, Q, Sum, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone


ZERO = Decimal("0.00")


class StudentFeeQuerySet(models.QuerySet):
    def with_payment_status(self):
        # Calculate at read time as well: a fee can become overdue overnight.
        return self.annotate(
            _paid_total=Coalesce(
                Sum("payments__amount_paid"), Value(ZERO),
                output_field=models.DecimalField(max_digits=14, decimal_places=2),
            )
        ).annotate(
            _current_status=Case(
                When(_paid_total__gte=F("amount_due"), then=Value("paid")),
                When(due_date__lt=timezone.localdate(), then=Value("overdue")),
                When(_paid_total__gt=ZERO, then=Value("partial")),
                default=Value("pending"), output_field=models.CharField(),
            )
        ).order_by("due_date", "pk")


class StudentFee(models.Model):
    class FeeType(models.TextChoices):
        TUITION = "tuition", "Tuition"
        LIBRARY = "library", "Library"
        TRANSPORT = "transport", "Transport"
        EXAM = "exam", "Exam"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PARTIAL = "partial", "Partial"
        PAID = "paid", "Paid"
        OVERDUE = "overdue", "Overdue"

    student = models.ForeignKey(
        "people.Student", on_delete=models.PROTECT, related_name="fees"
    )
    academic_year = models.ForeignKey(
        "academics.AcademicYear", on_delete=models.PROTECT, related_name="student_fees"
    )
    fee_type = models.CharField(max_length=20, choices=FeeType.choices)
    amount_due = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(ZERO)]
    )
    due_date = models.DateField()
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING, editable=False
    )

    objects = StudentFeeQuerySet.as_manager()

    class Meta:
        ordering = ["due_date", "pk"]
        indexes = [models.Index(fields=["student", "academic_year"])]
        constraints = [
            models.CheckConstraint(condition=Q(amount_due__gte=0), name="fee_amount_nonnegative"),
        ]

    def total_paid(self):
        if not self.pk:
            return ZERO
        return self.payments.aggregate(total=Sum("amount_paid"))["total"] or ZERO

    def status_for(self, total):
        if total >= self.amount_due:
            return self.Status.PAID
        if self.due_date < timezone.localdate():
            return self.Status.OVERDUE
        return self.Status.PARTIAL if total > ZERO else self.Status.PENDING

    @property
    def current_status(self):
        if hasattr(self, "_current_status"):
            return self._current_status
        return self.status_for(self.total_paid())

    def refresh_status(self):
        with transaction.atomic():
            fee = type(self).objects.select_for_update().get(pk=self.pk)
            fee.status = fee.status_for(fee.total_paid())
            type(self).objects.filter(pk=fee.pk).update(status=fee.status)
            self.status = fee.status
            self.__dict__.pop("_current_status", None)
            self.__dict__.pop("_paid_total", None)
        return self.status

    def save(self, *args, **kwargs):
        with transaction.atomic():
            previous = None
            if self.pk:
                previous = type(self).objects.select_for_update().get(pk=self.pk)
            self.full_clean()
            paid = self.total_paid()
            if self.amount_due < paid:
                raise ValidationError({"amount_due": "Cannot be less than payments already received."})
            if previous and self.payments.exists() and (
                previous.student_id != self.student_id
                or previous.academic_year_id != self.academic_year_id
            ):
                raise ValidationError("Cannot reassign a fee that has payments.")
            self.status = self.status_for(paid)
            if kwargs.get("update_fields") is not None:
                kwargs["update_fields"] = set(kwargs["update_fields"]) | {"status"}
            super().save(*args, **kwargs)
            self.__dict__.pop("_current_status", None)
            self.__dict__.pop("_paid_total", None)


class FeePayment(models.Model):
    class PaymentMethod(models.TextChoices):
        CASH = "cash", "Cash"
        BANK_TRANSFER = "bank_transfer", "Bank Transfer"
        MOBILE_MONEY = "mobile_money", "Mobile Money"

    student_fee = models.ForeignKey(
        StudentFee, on_delete=models.PROTECT, related_name="payments"
    )
    amount_paid = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    payment_date = models.DateField(default=timezone.localdate)
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices)
    reference_number = models.CharField(max_length=100, blank=True, default="")

    class Meta:
        ordering = ["-payment_date", "-pk"]
        constraints = [
            models.CheckConstraint(condition=Q(amount_paid__gt=0), name="fee_payment_positive"),
        ]

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self.pk:
                previous = type(self).objects.get(pk=self.pk)
                if previous.student_fee_id != self.student_fee_id:
                    raise ValidationError({"student_fee": "Cannot move a payment to another fee."})
            # Every payment writer locks the parent before calculating its balance.
            fee = StudentFee.objects.select_for_update().get(pk=self.student_fee_id)
            self.full_clean()
            other_paid = fee.payments.exclude(pk=self.pk).aggregate(
                total=Sum("amount_paid")
            )["total"] or ZERO
            if other_paid + self.amount_paid > fee.amount_due:
                raise ValidationError({"amount_paid": "Payment exceeds the outstanding balance."})
            super().save(*args, **kwargs)
            fee.refresh_status()

    def delete(self, *args, **kwargs):
        with transaction.atomic():
            fee = StudentFee.objects.select_for_update().get(pk=self.student_fee_id)
            result = super().delete(*args, **kwargs)
            fee.refresh_status()
            return result


class StaffSalary(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"

    staff = models.ForeignKey(
        "people.Staff", on_delete=models.PROTECT, related_name="salaries"
    )
    month = models.DateField(help_text="Payroll month, stored as its first day.")
    base_salary = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(ZERO)]
    )
    allowances = models.DecimalField(
        max_digits=12, decimal_places=2, default=ZERO, validators=[MinValueValidator(ZERO)]
    )
    deductions = models.DecimalField(
        max_digits=12, decimal_places=2, default=ZERO, validators=[MinValueValidator(ZERO)]
    )
    net_salary = models.DecimalField(
        max_digits=14, decimal_places=2, default=ZERO, editable=False
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    payment_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-month", "staff_id"]
        constraints = [
            models.UniqueConstraint(fields=["staff", "month"], name="unique_staff_salary_month"),
            models.CheckConstraint(
                condition=Q(base_salary__gte=0, allowances__gte=0, deductions__gte=0, net_salary__gte=0),
                name="salary_amounts_nonnegative",
            ),
            models.CheckConstraint(
                condition=(Q(status="paid", payment_date__isnull=False)
                           | Q(status="pending", payment_date__isnull=True)),
                name="salary_payment_date_matches_status",
            ),
        ]

    def clean(self):
        super().clean()
        if self.month:
            self.month = self.month.replace(day=1)
        self.net_salary = self.base_salary + self.allowances - self.deductions
        if self.net_salary < ZERO:
            raise ValidationError({"deductions": "Cannot exceed base salary plus allowances."})
        if self.status == self.Status.PAID and not self.payment_date:
            raise ValidationError({"payment_date": "Required when salary is paid."})
        if self.status == self.Status.PENDING and self.payment_date:
            raise ValidationError({"payment_date": "Must be empty when salary is pending."})

    def save(self, *args, **kwargs):
        self.full_clean()  # Converts fields, normalizes month, and calculates net_salary.
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | {"net_salary", "month"}
        super().save(*args, **kwargs)
