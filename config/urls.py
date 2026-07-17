"""
URL configuration for config project.
"""

from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # API endpoints version 1
    path('api/v1/', include([
        # Schema documentation endpoints
        path('schema/', SpectacularAPIView.as_view(), name='schema'),
        path('docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
        path('redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
        
        # App-specific endpoints
        path('', include('people.urls')),
        path('', include('timetable.urls')),
        path('', include('class_sessions.urls')),
        # path('', include('payroll.urls')),  # Archived — not yet a focus feature
    ])),
]
