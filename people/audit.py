import contextvars
from contextlib import contextmanager

from rest_framework import status
from rest_framework.response import Response

from people.models import AuditLog

_mute = contextvars.ContextVar('audit_mute', default=False)
_actor = contextvars.ContextVar('audit_actor', default=None)

CATEGORY_STUDENT = 'student'
CATEGORY_TEACHER = 'teacher'
CATEGORY_STAFF = 'staff'
CATEGORY_CLASS = 'class'
CATEGORY_SESSION = 'session'
CATEGORY_CHECK_IN = 'check_in'
CATEGORY_USER = 'user'
CATEGORY_OTHER = 'other'


def is_muted():
    return _mute.get()


@contextmanager
def mute_audit():
    token = _mute.set(True)
    try:
        yield
    finally:
        _mute.reset(token)


@contextmanager
def audit_actor(user):
    token = _actor.set(_authenticated_user(user))
    try:
        yield
    finally:
        _actor.reset(token)


def current_actor(fallback=None):
    return _actor.get() or _authenticated_user(fallback)


def _authenticated_user(user):
    if user is None:
        return None
    if getattr(user, 'is_authenticated', True) is False:
        return None
    return user


def log_event(
    *,
    category,
    action,
    summary,
    user=None,
    model_name='',
    record_id='',
    field_name=None,
    old_value=None,
    new_value=None,
):
    """Create one human-readable audit row. No-op while mute_audit() is active."""
    if is_muted():
        return None
    actor = current_actor(user)
    return AuditLog.objects.create(
        user=actor,
        category=category,
        summary=(summary or '')[:255],
        model_name=model_name or '',
        record_id=str(record_id) if record_id not in (None, '') else '',
        action=action,
        field_name=field_name,
        old_value=str(old_value) if old_value is not None else None,
        new_value=str(new_value) if new_value is not None else None,
    )


def log_sessions_generated(user, created_count, context_label):
    if not created_count:
        return None
    noun = 'session' if created_count == 1 else 'sessions'
    return log_event(
        user=user,
        category=CATEGORY_SESSION,
        action='create',
        summary=f"Generated {created_count} {noun} for {context_label}",
        model_name='Session',
        record_id='',
        new_value=str(created_count),
    )


class AuditActorMixin:
    """Stamp request.user onto audit logs created during this request.

    Authentication runs inside DRF ``initial()``, so the actor must be set
    there rather than in ``dispatch()``.
    """

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        user = request.user if getattr(request.user, 'is_authenticated', False) else None
        self._audit_actor_token = _actor.set(_authenticated_user(user))

    def finalize_response(self, request, response, *args, **kwargs):
        token = getattr(self, '_audit_actor_token', None)
        if token is not None:
            _actor.reset(token)
            self._audit_actor_token = None
        return super().finalize_response(request, response, *args, **kwargs)


class AuditedViewSetMixin(AuditActorMixin):
    """Log create / update / delete (and bulk variants) as one summary each."""

    audit_category = CATEGORY_OTHER
    audit_noun = 'record'
    audit_noun_plural = 'records'
    audit_label_attr = None

    def audit_label(self, instance):
        attr = self.audit_label_attr
        if attr:
            return getattr(instance, attr, None) or str(instance)
        return str(instance)

    def audit_summary(self, action, instance):
        verb = {'create': 'Created', 'update': 'Updated', 'delete': 'Deleted'}[action]
        return f"{verb} {self.audit_noun} {self.audit_label(instance)}"

    def _log_instance(self, action, instance, **extra):
        request = getattr(self, 'request', None)
        user = getattr(request, 'user', None) if request else None
        log_event(
            user=user,
            category=self.audit_category,
            action=action,
            summary=self.audit_summary(action, instance),
            model_name=instance.__class__.__name__,
            record_id=instance.pk,
            **extra,
        )

    def perform_create(self, serializer):
        instance = serializer.save()
        self._log_instance('create', instance)
        return instance

    def perform_update(self, serializer):
        instance = serializer.save()
        self._log_instance('update', instance)
        return instance

    def perform_destroy(self, instance):
        label_instance = instance
        pk = instance.pk
        model_name = instance.__class__.__name__
        summary = self.audit_summary('delete', label_instance)
        instance.delete()
        request = getattr(self, 'request', None)
        log_event(
            user=getattr(request, 'user', None) if request else None,
            category=self.audit_category,
            action='delete',
            summary=summary,
            model_name=model_name,
            record_id=pk,
        )

    def perform_bulk_create(self, serializer):
        instances = serializer.save()
        count = len(instances) if instances is not None else 0
        if count:
            request = getattr(self, 'request', None)
            log_event(
                user=getattr(request, 'user', None) if request else None,
                category=self.audit_category,
                action='create',
                summary=f"Imported {count} {self.audit_noun_plural}",
                model_name=getattr(self, 'queryset').model.__name__,
                record_id='',
                new_value=str(count),
            )
        return instances

    def bulk_delete(self, request):
        ids = request.data.get('ids', [])
        count = 0
        if isinstance(ids, list) and ids:
            count = self.get_queryset().filter(pk__in=ids).count()
        response = super().bulk_delete(request)
        if isinstance(response, Response) and response.status_code == status.HTTP_200_OK and count:
            log_event(
                user=request.user,
                category=self.audit_category,
                action='delete',
                summary=f"Deleted {count} {self.audit_noun_plural}",
                model_name=getattr(self, 'queryset').model.__name__,
                record_id='',
                new_value=str(count),
            )
        return response
