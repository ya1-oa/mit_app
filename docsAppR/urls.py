"""
docsAppR/urls.py

All URL patterns reside in dedicated app modules:

  claims/urls.py          → /claims/
  scope_checklist/urls.py → /scope-checklist/
  lease_manager/urls.py   → /lease-manager/
  email_manager/urls.py   → /emails/
  labels/urls.py          → /labels/
  readings/urls.py        → /readings/
  sensor_renamer/urls.py  → /sensor-renamer/
  equipment_checker/urls.py → /equipment-checker/
  claim_images/urls.py    → /claim-images/
  encircle/urls.py        → /encircle/
  dashboard/urls.py       → / (home, dashboard, misc)

This file is intentionally left empty for most routes.
Invite management lives here since TenantInvite is a docsAppR model.
"""

from django.urls import path
from . import views

urlpatterns = [
    path('settings/', views.tenant_settings, name='tenant_settings'),
]
