from rest_framework.routers import DefaultRouter

from .views import FeePaymentViewSet, StaffSalaryViewSet, StudentFeeViewSet


router = DefaultRouter()
router.register("student-fees", StudentFeeViewSet, basename="student-fee")
router.register("fee-payments", FeePaymentViewSet, basename="fee-payment")
router.register("staff-salaries", StaffSalaryViewSet, basename="staff-salary")

urlpatterns = router.urls
