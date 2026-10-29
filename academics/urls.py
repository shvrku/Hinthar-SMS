from rest_framework.routers import DefaultRouter

from .views import (
    AcademicYearViewSet, TermViewSet, SubjectOfferingViewSet, AssessmentViewSet,
    AssessmentResultViewSet, ReportCardViewSet,
)

router = DefaultRouter()
router.register("academic-years", AcademicYearViewSet, basename="academic-year")
router.register("terms", TermViewSet, basename="academic-term")
router.register("subject-offerings", SubjectOfferingViewSet, basename="subject-offering")
router.register("assessments", AssessmentViewSet, basename="assessment")
router.register("assessment-results", AssessmentResultViewSet, basename="assessment-result")
router.register("report-cards", ReportCardViewSet, basename="report-card")

urlpatterns = router.urls
