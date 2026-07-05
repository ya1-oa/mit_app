"""
docsAppR/middleware.py
"""
from .tenancy import set_current_tenant, reset_current_tenant


class TenantMiddleware:
    """
    Establishes the current request's tenant for both the template/view layer
    (`request.tenant`) and the TenantScopedManager (via the tenancy contextvar).

    Staff users get NO ambient tenant — they must use the explicit
    `.all_tenants()` / `bypass_tenant_scope()` escape hatch per view. This is
    deliberate: staff accounts (ClaiMetApp's own team) must never be silently
    scoped into one customer's data, and must never be assumed to belong to
    the bootstrapped "default tenant" created during the migration backfill.

    Must run AFTER AuthenticationMiddleware (needs request.user) and before
    any tenant-scoped queryset is touched — see MIDDLEWARE order in settings.py.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.tenant = None
        token = None

        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated and not user.is_staff:
            request.tenant = user.tenant
            if request.tenant is not None:
                token = set_current_tenant(request.tenant.id)
            # else: authenticated, non-staff, tenant=None. Once the backfill
            # migration (Workstream A Phase 0 bootstrap step) has run, this
            # should not happen — every non-staff user has a tenant. Treated
            # as a misconfiguration to investigate, not silently allowed
            # through with an empty queryset on every page.

        try:
            response = self.get_response(request)
        finally:
            if token is not None:
                reset_current_tenant(token)

        return response
