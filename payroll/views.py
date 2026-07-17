# Payroll views archived — not yet a focus feature

# from rest_framework.viewsets import ModelViewSet
# from rest_framework.views import APIView
# from rest_framework.response import Response
# from rest_framework.permissions import IsAuthenticated
# from rest_framework.exceptions import NotFound
# from django.db import transaction
# from django.db.models import Sum
# from payroll.models import PayPeriod, Payslip, Adjustment
# from payroll.serializers import (
#     PayPeriodSerializer, PayslipSerializer, AdjustmentSerializer
# )
# from people.permissions import IsAdmin
# from people.models import Teacher
# from class_sessions.models import Session

# class PayPeriodViewSet(ModelViewSet):
#     queryset = PayPeriod.objects.all()
#     serializer_class = PayPeriodSerializer
#     permission_classes = [IsAuthenticated]

#     def get_permissions(self):
#         if self.action in ['create', 'update', 'partial_update', 'destroy']:
#             return [IsAdmin()]
#         return [IsAuthenticated()]

# class PayslipViewSet(ModelViewSet):
#     queryset = Payslip.objects.select_related(
#         'teacher', 'teacher__user', 'pay_period'
#     ).all()
#     serializer_class = PayslipSerializer
#     permission_classes = [IsAuthenticated]

#     def get_permissions(self):
#         if self.action in ['create', 'update', 'partial_update', 'destroy']:
#             return [IsAdmin()]
#         return [IsAuthenticated()]

# class AdjustmentViewSet(ModelViewSet):
#     queryset = Adjustment.objects.all()
#     serializer_class = AdjustmentSerializer
#     permission_classes = [IsAuthenticated]

#     def get_permissions(self):
#         if self.action in ['update', 'partial_update', 'destroy']:
#             return [IsAdmin()]
#         return [IsAuthenticated()]

# class PayslipPreviewView(APIView):
#     permission_classes = [IsAdmin]

#     def get(self, request):
#         teacher_id = request.query_params.get('teacher_id')
#         pay_period_id = request.query_params.get('pay_period_id')

#         if not teacher_id or not pay_period_id:
#             return Response({'error': 'teacher_id and pay_period_id are required'}, status=400)

#         try:
#             pay_period = PayPeriod.objects.get(id=pay_period_id)
#             teacher = Teacher.objects.get(id=teacher_id)
#         except PayPeriod.DoesNotExist:
#             raise NotFound(detail='Pay period not found')
#         except Teacher.DoesNotExist:
#             raise NotFound(detail='Teacher not found')

#         sessions = Session.objects.filter(
#             teacher=teacher,
#             start_time__date__range=(pay_period.start_date, pay_period.end_date),
#             status='completed',
#             paid=False
#         )
#         session_count = sessions.count()

#         rate_applied = teacher.default_rate

#         gross_pay = session_count * rate_applied
#         tax_deduction = gross_pay * 0.15
#         other_deductions = 0
#         adjustments_total = Adjustment.objects.filter(
#             teacher=teacher,
#             status='pending',
#             applied_payslip__isnull=True
#         ).aggregate(total=Sum('amount'))['total'] or 0
#         net_pay = gross_pay - tax_deduction - other_deductions + adjustments_total

#         return Response({
#             'teacher_id': teacher_id,
#             'pay_period_id': pay_period_id,
#             'session_count': session_count,
#             'rate_applied': rate_applied,
#             'gross_pay': gross_pay,
#             'tax_deduction': tax_deduction,
#             'other_deductions': other_deductions,
#             'adjustments_total': adjustments_total,
#             'net_pay': net_pay
#         })

# class ConfirmPayslipView(APIView):
#     permission_classes = [IsAdmin]

#     @transaction.atomic
#     def post(self, request):
#         teacher_id = request.data.get('teacher_id')
#         pay_period_id = request.data.get('pay_period_id')

#         if not teacher_id or not pay_period_id:
#             return Response({'error': 'teacher_id and pay_period_id are required'}, status=400)

#         try:
#             pay_period = PayPeriod.objects.get(id=pay_period_id)
#             teacher = Teacher.objects.get(id=teacher_id)
#         except PayPeriod.DoesNotExist:
#             raise NotFound(detail='Pay period not found')
#         except Teacher.DoesNotExist:
#             raise NotFound(detail='Teacher not found')

#         sessions = Session.objects.select_for_update().filter(
#             teacher=teacher,
#             start_time__date__range=(pay_period.start_date, pay_period.end_date),
#             status='completed',
#             paid=False
#         )
#         session_count = sessions.count()

#         if session_count == 0:
#             return Response(
#                 {'error': 'No unpaid completed sessions found for this teacher in the selected pay period.'},
#                 status=400
#             )

#         rate_applied = teacher.default_rate

#         gross_pay = session_count * rate_applied
#         tax_deduction = gross_pay * 0.15
#         other_deductions = 0

#         adjustments = Adjustment.objects.select_for_update().filter(
#             teacher=teacher,
#             status='pending',
#             applied_payslip__isnull=True
#         )
#         adjustments_total = sum(adj.amount for adj in adjustments)

#         net_pay = gross_pay - tax_deduction - other_deductions + adjustments_total

#         payslip = Payslip(
#             teacher=teacher,
#             pay_period=pay_period,
#             session_count=session_count,
#             rate_applied=rate_applied,
#             gross_pay=gross_pay,
#             tax_deduction=tax_deduction,
#             other_deductions=other_deductions,
#             adjustments_total=adjustments_total,
#             net_pay=net_pay,
#             status='approved'
#         )
#         payslip._audit_user = request.user
#         payslip.save()

#         # Mark sessions as paid and link to payslip
#         for session in sessions:
#             session.paid = True
#             session.payslip = payslip
#             session._audit_user = request.user
#             session.save()

#         # Mark adjustments as applied and link to payslip
#         adjustments.update(status='applied', applied_payslip=payslip)

#         serializer = PayslipSerializer(payslip)
#         return Response(serializer.data)
