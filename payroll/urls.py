# Payroll URLs archived — not yet a focus feature

# from django.urls import path, include
# from rest_framework.routers import DefaultRouter
# from payroll import views

# router = DefaultRouter()
# router.register(r'pay-periods', views.PayPeriodViewSet)
# router.register(r'payslips', views.PayslipViewSet)
# router.register(r'adjustments', views.AdjustmentViewSet)

# urlpatterns = [
#     path('', include(router.urls)),
#     path('payslips/preview/', views.PayslipPreviewView.as_view(), name='payslip-preview'),
#     path('payslips/confirm/', views.ConfirmPayslipView.as_view(), name='confirm-payslip'),
# ]
