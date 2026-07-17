# Payroll admin archived — not yet a focus feature

# from django.contrib import admin
# from payroll.models import PayPeriod, Payslip, Adjustment


# @admin.register(PayPeriod)
# class PayPeriodAdmin(admin.ModelAdmin):
#     list_display = ('id', 'start_date', 'end_date')
#     date_hierarchy = 'start_date'


# @admin.register(Payslip)
# class PayslipAdmin(admin.ModelAdmin):
#     list_display = ('id', 'teacher', 'pay_period', 'net_pay', 'status', 'issued_date')
#     list_filter = ('status', 'pay_period')
#     search_fields = ('teacher__name',)
#     date_hierarchy = 'issued_date'


# @admin.register(Adjustment)
# class AdjustmentAdmin(admin.ModelAdmin):
#     list_display = ('id', 'teacher', 'amount', 'status', 'created_date')
#     list_filter = ('status', 'created_date')
#     search_fields = ('teacher__name', 'reason')
