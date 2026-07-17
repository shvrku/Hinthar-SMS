# Payroll serializers archived — not yet a focus feature

# from rest_framework import serializers
# from payroll.models import PayPeriod, Payslip, Adjustment
# from people.serializers import TeacherSerializer

# class PayPeriodSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = PayPeriod
#         fields = ['id', 'start_date', 'end_date']

# class PayslipSerializer(serializers.ModelSerializer):
#     teacher = TeacherSerializer(read_only=True)
#     pay_period = PayPeriodSerializer(read_only=True)

#     class Meta:
#         model = Payslip
#         fields = [
#             'id', 'teacher', 'pay_period', 'session_count', 'rate_applied',
#             'gross_pay', 'tax_deduction', 'other_deductions', 'adjustments_total',
#             'net_pay', 'status', 'issued_date'
#         ]

# class AdjustmentSerializer(serializers.ModelSerializer):
#     teacher = TeacherSerializer(read_only=True)
#     applied_payslip = PayslipSerializer(read_only=True)

#     class Meta:
#         model = Adjustment
#         fields = [
#             'id', 'teacher', 'session', 'reason', 'amount',
#             'status', 'created_date', 'applied_payslip'
#         ]
