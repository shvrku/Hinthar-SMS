# Payroll models archived — not yet a focus feature

# from django.db import models
# from decimal import Decimal
# from people.models import Teacher
# from class_sessions.models import Session


# class PayPeriod(models.Model):
#     start_date = models.DateField()
#     end_date = models.DateField()

#     class Meta:
#         indexes = [
#             models.Index(fields=['start_date', 'end_date']),
#         ]

#     def __str__(self):
#         return f"Pay Period {self.start_date} to {self.end_date}"


# class Payslip(models.Model):
#     STATUS_CHOICES = [
#         ('draft', 'Draft'),
#         ('approved', 'Approved'),
#         ('paid', 'Paid'),
#     ]

#     teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE, related_name='payslips')
#     pay_period = models.ForeignKey(PayPeriod, on_delete=models.CASCADE, related_name='payslips')
#     session_count = models.IntegerField()
#     rate_applied = models.DecimalField(max_digits=10, decimal_places=2)
#     gross_pay = models.DecimalField(max_digits=10, decimal_places=2)
#     tax_deduction = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
#     other_deductions = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
#     adjustments_total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
#     net_pay = models.DecimalField(max_digits=10, decimal_places=2)
#     status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
#     issued_date = models.DateField(auto_now_add=True)

#     def save(self, *args, **kwargs):
#         self.net_pay = self.gross_pay - self.tax_deduction - self.other_deductions + self.adjustments_total
#         super().save(*args, **kwargs)

#     class Meta:
#         indexes = [
#             models.Index(fields=['teacher', 'pay_period']),
#             models.Index(fields=['status']),
#         ]

#     def __str__(self):
#         return f"Payslip for {self.teacher.name} ({self.pay_period})"


# class Adjustment(models.Model):
#     STATUS_CHOICES = [
#         ('pending', 'Pending'),
#         ('applied', 'Applied'),
#     ]

#     teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE, related_name='adjustments')
#     session = models.ForeignKey(Session, on_delete=models.SET_NULL, null=True, blank=True, related_name='adjustments')
#     reason = models.TextField()
#     amount = models.DecimalField(max_digits=10, decimal_places=2)
#     status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
#     created_date = models.DateField(auto_now_add=True)
#     applied_payslip = models.ForeignKey(Payslip, on_delete=models.SET_NULL, null=True, blank=True, related_name='adjustments')

#     class Meta:
#         indexes = [
#             models.Index(fields=['teacher', 'status', 'applied_payslip']),
#         ]

#     def __str__(self):
#         return f"Adjustment for {self.teacher.name}: {self.amount} ({self.get_status_display()})"
