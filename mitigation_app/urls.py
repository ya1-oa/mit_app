"""
Root URL configuration for the Mitigation App.

Each feature is its own Django app with its own urls.py.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # Django admin
    path('admin/', admin.site.urls),

    # Authentication (allauth — login, logout, signup, password reset, etc.)
    path('accounts/', include('allauth.urls')),

    # ── App URLs ─────────────────────────────────────────────────────────────
    # Home (app grid) + dashboard stats + misc helpers
    path('', include('dashboard.urls')),

    # Claims Manager + Push Rooms
    path('claims/', include('claims.urls')),

    # Scope Checklist
    path('scope-checklist/', include('scope_checklist.urls')),

    # Lease Manager
    path('lease-manager/', include('lease_manager.urls')),

    # Email Manager
    path('emails/', include('email_manager.urls')),

    # Labels — Box & Wall
    path('labels/', include('labels.urls')),

    # Reading Browser
    path('readings/', include('readings.urls')),

    # Sensor Renamer (AI)
    path('sensor-renamer/', include('sensor_renamer.urls')),

    # Equipment Checker (AI)
    path('equipment-checker/', include('equipment_checker.urls')),

    # Claim Images Download
    path('claim-images/', include('claim_images.urls')),

    # Encircle Dashboard + Sync + Webhooks
    path('encircle/', include('encircle.urls')),

    # Box Count Calculator
    path('box-calculator/', include('box_calculator.urls')),

    # CPS Schedule of Loss Report
    path('cps-report/', include('cps_report.urls')),

    # Contractor Bid Hub
    path('contractor-hub/', include('contractor_hub.urls')),

    # Dev Hub — internal project tracking + notification hub
    path('dev-hub/', include('dev_hub.urls')),

] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
