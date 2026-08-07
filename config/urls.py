"""
URL configuration for config project.
"""

from django.conf import settings
from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from config.views import health

urlpatterns = [
    # Public liveness — UptimeRobot / load balancers (no auth)
    path('health/', health, name='health'),

    path('admin/', admin.site.urls),

    # API endpoints version 1
    path('api/v1/', include([
        # App-specific endpoints
        path('', include('people.urls')),
        path('', include('timetable.urls')),
        path('', include('class_sessions.urls')),
        # path('', include('payroll.urls')),  # Archived — not yet a focus feature
    ])),
]

# OpenAPI schema / Swagger — development only (SEC-M6).
# Production recon surface; staff can use local DEBUG or a future admin-only gate.
if settings.DEBUG:
    urlpatterns += [
        path('api/v1/schema/', SpectacularAPIView.as_view(), name='schema'),
        path('api/v1/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
        path('api/v1/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    ]
