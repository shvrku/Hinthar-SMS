from django.urls import path, include
from rest_framework.routers import DefaultRouter
from class_sessions import views

router = DefaultRouter()
router.register(r'sessions', views.SessionViewSet)
router.register(r'session-attendances', views.SessionAttendanceViewSet)
router.register(r'check-ins', views.CheckInViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('sessions/generate/', views.GenerateSessionsView.as_view(), name='generate-sessions'),
    path('check-ins/qr/', views.QRCheckInView.as_view(), name='checkin-qr'),
    path('check-ins/manual/', views.ManualCheckInView.as_view(), name='checkin-manual'),
]