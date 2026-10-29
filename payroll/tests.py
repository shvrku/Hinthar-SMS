from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from academics.models import AcademicYear
from people.models import Staff, Student
from .models import FeePayment, StaffSalary, StudentFee


class FinanceAPITestCase(APITestCase):
    def setUp(self):
        User = get_user_model()
        user_fields = {field.name for field in User._meta.fields}
        values = {"username": "finance-admin", "password": "test-password",
                  "is_staff": True, "is_superuser": False}
        if "clerk_id" in user_fields:
            values["clerk_id"] = "test-finance-admin"
        if "role" in user_fields:
            values["role"] = "admin"
        self.admin = User.objects.create_user(**values)
        self.client.force_authenticate(self.admin)

        # Adapt these fixtures if your external models have other required fields.
        self.student = Student.objects.create(name="Test Student")
        self.staff = Staff.objects.create(name="Test Employee")
        self.year = AcademicYear.objects.create(
            name="2026-2027", start_date=date(2026, 6, 1), end_date=date(2027, 5, 31)
        )
        self.fee = StudentFee.objects.create(
            student=self.student, academic_year=self.year,
            fee_type=StudentFee.FeeType.TUITION, amount_due=Decimal("100.00"),
            due_date=timezone.localdate() + timedelta(days=30),
        )

    def pay(self, amount):
        return self.client.post(reverse("fee-payment-list"), {
            "student_fee": self.fee.pk, "amount_paid": str(amount),
            "payment_date": timezone.localdate().isoformat(), "payment_method": "cash",
        }, format="json")

    @staticmethod
    def rows(response):
        return response.data["results"] if isinstance(response.data, dict) else response.data


class StudentFeeAPITests(FinanceAPITestCase):
    def test_create_ignores_client_status(self):
        response = self.client.post(reverse("student-fee-list"), {
            "student": self.student.pk, "academic_year": self.year.pk,
            "fee_type": "library", "amount_due": "25.00",
            "due_date": (timezone.localdate() + timedelta(days=10)).isoformat(),
            "status": "paid",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["status"], "pending")

    def test_nested_payments_and_filters(self):
        self.assertEqual(self.pay("25.00").status_code, 201)
        response = self.client.get(reverse("student-fee-list"), {
            "student_id": self.student.pk, "status": "partial",
        })
        self.assertEqual(response.status_code, 200)
        rows = self.rows(response)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["payments"][0]["amount_paid"], "25.00")
        response = self.client.get(reverse("student-fee-list"), {"status": "paid"})
        self.assertEqual(len(self.rows(response)), 0)

    def test_overdue_updates_at_read_time_without_payment(self):
        tomorrow_after_due = self.fee.due_date + timedelta(days=1)
        with patch("payroll.models.timezone.localdate", return_value=tomorrow_after_due):
            response = self.client.get(reverse("student-fee-list"), {"status": "overdue"})
        self.assertEqual(len(self.rows(response)), 1)
        self.assertEqual(self.rows(response)[0]["status"], "overdue")

    def test_cannot_reduce_fee_below_payments(self):
        self.pay("50.00")
        response = self.client.patch(reverse("student-fee-detail", args=[self.fee.pk]),
                                     {"amount_due": "40.00"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.fee.refresh_from_db()
        self.assertEqual(self.fee.amount_due, Decimal("100.00"))

    def test_cannot_delete_fee_with_payments(self):
        self.pay("20.00")
        response = self.client.delete(reverse("student-fee-detail", args=[self.fee.pk]))
        self.assertEqual(response.status_code, 400)
        self.assertTrue(StudentFee.objects.filter(pk=self.fee.pk).exists())

    def test_anonymous_and_inactive_admin_denied(self):
        self.client.force_authenticate(user=None)
        self.assertIn(self.client.get(reverse("student-fee-list")).status_code, (401, 403))
        self.admin.is_active = False
        self.admin.save()
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(reverse("student-fee-list")).status_code, 403)


class FeePaymentAPITests(FinanceAPITestCase):
    def test_partial_then_paid(self):
        self.assertEqual(self.pay("40.00").status_code, 201)
        self.fee.refresh_from_db()
        self.assertEqual(self.fee.status, StudentFee.Status.PARTIAL)
        self.assertEqual(self.pay("60.00").status_code, 201)
        self.fee.refresh_from_db()
        self.assertEqual(self.fee.status, StudentFee.Status.PAID)

    def test_model_save_updates_status_without_serializer(self):
        FeePayment.objects.create(student_fee=self.fee, amount_paid=Decimal("100.00"),
                                  payment_method="bank_transfer")
        self.fee.refresh_from_db()
        self.assertEqual(self.fee.status, StudentFee.Status.PAID)

    def test_overdue_precedence_until_fully_paid(self):
        self.fee.due_date = timezone.localdate() - timedelta(days=1)
        self.fee.save()
        self.pay("10.00")
        self.fee.refresh_from_db()
        self.assertEqual(self.fee.status, StudentFee.Status.OVERDUE)
        self.pay("90.00")
        self.fee.refresh_from_db()
        self.assertEqual(self.fee.status, StudentFee.Status.PAID)

    def test_edit_and_delete_recalculate_status(self):
        payment_id = self.pay("100.00").data["id"]
        url = reverse("fee-payment-detail", args=[payment_id])
        response = self.client.patch(url, {"amount_paid": "30.00"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.fee.refresh_from_db()
        self.assertEqual(self.fee.status, StudentFee.Status.PARTIAL)
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.fee.refresh_from_db()
        self.assertEqual(self.fee.status, StudentFee.Status.PENDING)

    def test_overpayments_zero_and_negative_rejected(self):
        for amount in ("101.00", "0.00", "-1.00"):
            self.assertEqual(self.pay(amount).status_code, 400)
        self.assertEqual(self.fee.payments.count(), 0)

    def test_payment_cannot_move_to_another_fee(self):
        payment_id = self.pay("20.00").data["id"]
        other = StudentFee.objects.create(student=self.student, academic_year=self.year,
                                          fee_type="exam", amount_due=Decimal("50.00"),
                                          due_date=self.fee.due_date)
        response = self.client.patch(reverse("fee-payment-detail", args=[payment_id]),
                                     {"student_fee": other.pk}, format="json")
        self.assertEqual(response.status_code, 400)


class StaffSalaryAPITests(FinanceAPITestCase):
    def salary_payload(self, **changes):
        data = {"staff": self.staff.pk, "month": "2026-09-15", "base_salary": "1000.00",
                "allowances": "200.00", "deductions": "50.00"}
        data.update(changes)
        return data

    def test_net_salary_calculated_and_read_only(self):
        response = self.client.post(reverse("staff-salary-list"),
                                    self.salary_payload(net_salary="999999.00"), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["net_salary"], "1150.00")
        self.assertEqual(response.data["month"], "2026-09-01")
        salary = StaffSalary.objects.get(pk=response.data["id"])
        self.assertEqual(salary.net_salary, Decimal("1150.00"))

    def test_patch_recalculates_net_salary(self):
        response = self.client.post(reverse("staff-salary-list"), self.salary_payload(), format="json")
        url = reverse("staff-salary-detail", args=[response.data["id"]])
        response = self.client.patch(url, {"allowances": "300.00", "net_salary": "1.00"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["net_salary"], "1250.00")

    def test_model_save_calculates_net_salary(self):
        salary = StaffSalary.objects.create(staff=self.staff, month=date(2026, 9, 20),
                                            base_salary=Decimal("500.00"))
        self.assertEqual(salary.net_salary, Decimal("500.00"))
        self.assertEqual(salary.month, date(2026, 9, 1))

    def test_duplicate_employee_month_rejected(self):
        self.client.post(reverse("staff-salary-list"), self.salary_payload(), format="json")
        response = self.client.post(reverse("staff-salary-list"),
                                    self.salary_payload(month="2026-09-30"), format="json")
        self.assertEqual(response.status_code, 400)

    def test_invalid_deductions_and_payment_date_rejected(self):
        for changes in ({"deductions": "1201.00"}, {"status": "paid"},
                        {"payment_date": "2026-09-30"}, {"base_salary": "-1.00"}):
            response = self.client.post(reverse("staff-salary-list"),
                                        self.salary_payload(**changes), format="json")
            self.assertEqual(response.status_code, 400, response.data)

    def test_staff_and_status_filters(self):
        response = self.client.post(reverse("staff-salary-list"), self.salary_payload(
            status="paid", payment_date="2026-09-30"), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        response = self.client.get(reverse("staff-salary-list"), {"staff_id": self.staff.pk, "status": "paid"})
        self.assertEqual(len(self.rows(response)), 1)
        response = self.client.get(reverse("staff-salary-list"), {"status": "pending"})
        self.assertEqual(len(self.rows(response)), 0)

    def test_non_admin_cannot_read_salaries(self):
        self.admin.is_staff = False
        if hasattr(self.admin, "role"):
            self.admin.role = "staff"
        self.admin.save()
        response = self.client.get(reverse("staff-salary-list"))
        self.assertEqual(response.status_code, 403)
