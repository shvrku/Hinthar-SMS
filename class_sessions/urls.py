from django.urls import path, include
from rest_framework.routers import DefaultRouter
from class_sessions import views

router = DefaultRouter()
router.register(r'sessions', views.SessionViewSet)
router.register(r'session-attendances', views.SessionAttendanceViewSet)
router.register(r'check-ins', views.CheckInViewSet)
router.register(r'adhoc-sessions', views.AdHocSessionViewSet)
router.register(r'adhoc-session-attendances', views.AdHocSessionAttendanceViewSet)

urlpatterns = [
    # Explicit paths first, before the router, so they take priority
    path('stats/', views.StatsView.as_view(), name='stats'),
    path('check-ins/lookup/', views.CheckInLookupView.as_view(), name='checkin-lookup'),
    path('check-ins/qr/', views.QRCheckInView.as_view(), name='checkin-qr'),
    path('check-ins/manual/', views.ManualCheckInView.as_view(), name='checkin-manual'),
    path('sessions/generate/<int:class_id>/', views.GenerateClassSessionsView.as_view(), name='generate-class-sessions'),
    path('attendance/matrix/', views.AttendanceMatrixView.as_view(), name='attendance-matrix'),
    path('adhoc-attendance/matrix/', views.AdHocAttendanceMatrixView.as_view(), name='adhoc-attendance-matrix'),
    # Router (catches check-ins/ list detail routes)
    path('', include(router.urls)),
]
