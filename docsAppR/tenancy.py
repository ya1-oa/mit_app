"""
docsAppR/tenancy.py

Multi-tenant data isolation primitives.

The current request's tenant is carried in a contextvar (not just a
`request.tenant` attribute) so that the SAME mechanism scopes Celery tasks,
management commands, and signal handlers, none of which have a `request`
object. Any code running outside a request that needs to touch tenant-scoped
data must call `set_current_tenant(tenant_id)` itself before doing so.

Design goal: FAIL CLOSED. If no tenant is set in the current context,
TenantScopedManager returns an EMPTY queryset, never every tenant's rows. The
unsafe path (seeing across tenants) requires deliberately reaching for
`.unscoped` or `.all_tenants()` — it is never the default.
"""
import contextvars

from django.db import models

_current_tenant_id = contextvars.ContextVar('current_tenant_id', default=None)
_bypass_tenant_scope = contextvars.ContextVar('bypass_tenant_scope', default=False)


def set_current_tenant(tenant_id):
    """Push a tenant id onto the current context. Returns a token for reset_current_tenant()."""
    return _current_tenant_id.set(tenant_id)


def get_current_tenant_id():
    return _current_tenant_id.get()


def reset_current_tenant(token):
    _current_tenant_id.reset(token)


class bypass_tenant_scope:
    """
    Context manager / decorator for explicit, audited cross-tenant access.
    Intended for staff-only code paths (admin, internal reports) — never use
    this to work around a query that "should" be tenant-scoped.

        with bypass_tenant_scope():
            Client.objects.all()   # every tenant's rows
    """
    def __enter__(self):
        self._token = _bypass_tenant_scope.set(True)
        return self

    def __exit__(self, *exc):
        _bypass_tenant_scope.reset(self._token)
        return False


class TenantScopedManager(models.Manager):
    """
    Default manager for tenant-scoped models. Filters by the tenant in the
    current context. If no tenant is set, returns an EMPTY queryset (fail
    closed) rather than every tenant's data.
    """

    def get_queryset(self):
        qs = super().get_queryset()

        # MASTER SWITCH — tenant enforcement is OFF until deliberately enabled.
        # While off, this manager behaves like a normal (unfiltered) manager so
        # the live single-tenant app behaves exactly as it did before the
        # multi-tenant retrofit began (Workstream A Phase 0: "nothing enforced
        # yet; site behaves identically"). Turning this on before every row is
        # backfilled with a tenant_id AND staff/user tenants are assigned will
        # make tenant-scoped lists (leases, claims, etc.) appear EMPTY. Only
        # flip TENANT_ENFORCEMENT_ENABLED=true after the backfill is verified
        # and cross-tenant isolation has been tested in staging.
        from django.conf import settings
        if not getattr(settings, 'TENANT_ENFORCEMENT_ENABLED', False):
            return qs

        if _bypass_tenant_scope.get():
            return qs
        tenant_id = get_current_tenant_id()
        if tenant_id is None:
            return qs.none()
        return qs.filter(tenant_id=tenant_id)

    def all_tenants(self):
        """Explicit escape hatch. Caller is responsible for staff-gating this."""
        with bypass_tenant_scope():
            return self.get_queryset()


class TenantScopedModel(models.Model):
    """
    Abstract base for any model whose rows belong to exactly one tenant.

    `objects` is tenant-scoped and fails closed. `unscoped` is a plain,
    unfiltered manager — named to be greppable for the audit pass called out
    in the multi-tenant retrofit plan; use it only in staff-gated code paths
    (admin, internal reports) or inside data migrations.
    """
    tenant = models.ForeignKey(
        'docsAppR.Tenant', on_delete=models.PROTECT, db_index=True,
        null=True, blank=True,  # null=True only during the migration window for
                                 # this model — tightened to non-nullable once its
                                 # backfill is verified complete (see migration plan).
    )

    objects = TenantScopedManager()
    unscoped = models.Manager()

    class Meta:
        abstract = True
