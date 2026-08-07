from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from people.models import AuditLog


def _log_action(user, model_name, record_id, action, field_name=None, old_value=None, new_value=None):
    """Helper to create an audit log entry (safe to call outside request-response cycle)."""
    if not user or not user.is_authenticated:
        # Use a fallback system user concept or just skip user
        user = None
    AuditLog.objects.create(
        user=user,
        model_name=model_name,
        record_id=str(record_id),
        action=action,
        field_name=field_name,
        old_value=str(old_value) if old_value is not None else None,
        new_value=str(new_value) if new_value is not None else None,
    )


def _capture_old_status(sender, instance):
    """
    Prefer status loaded via Model.from_db (_old_status already set).
    Only hit the DB when the instance was constructed without from_db
    (e.g. Session(pk=…) then field assign) and status may have changed.
    """
    if getattr(instance, '_skip_audit', False):
        return
    if hasattr(instance, '_old_status'):
        return
    if instance.pk:
        instance._old_status = (
            sender.objects.filter(pk=instance.pk).values_list('status', flat=True).first()
        )
    else:
        instance._old_status = None


# ---- Session auditing (status changes) ----

@receiver(pre_save, sender='class_sessions.Session')
def audit_session_pre_save(sender, instance, **kwargs):
    _capture_old_status(sender, instance)


@receiver(post_save, sender='class_sessions.Session')
def audit_session_post_save(sender, instance, created, **kwargs):
    if getattr(instance, '_skip_audit', False):
        return
    if created:
        _log_action(
            user=getattr(instance, '_audit_user', None),
            model_name='Session',
            record_id=instance.id,
            action='create',
            new_value=f"status={instance.status}, start={instance.start_time:%d/%m/%y %H:%M}",
        )
        instance._old_status = instance.status
    else:
        old_status = getattr(instance, '_old_status', None)

        if old_status is not None and old_status != instance.status:
            _log_action(
                user=getattr(instance, '_audit_user', None),
                model_name='Session',
                record_id=instance.id,
                action='update',
                field_name='status',
                old_value=old_status,
                new_value=instance.status,
            )
        instance._old_status = instance.status


@receiver(pre_save, sender='class_sessions.AdHocSession')
def audit_adhoc_session_pre_save(sender, instance, **kwargs):
    _capture_old_status(sender, instance)


@receiver(post_save, sender='class_sessions.AdHocSession')
def audit_adhoc_session_post_save(sender, instance, created, **kwargs):
    if getattr(instance, '_skip_audit', False):
        return
    if created:
        _log_action(
            user=getattr(instance, '_audit_user', None),
            model_name='AdHocSession',
            record_id=instance.id,
            action='create',
            new_value=f"status={instance.status}, date={instance.date:%d/%m/%y}, start={instance.start_time:%H:%M}",
        )
        instance._old_status = instance.status
    else:
        old_status = getattr(instance, '_old_status', None)

        if old_status is not None and old_status != instance.status:
            _log_action(
                user=getattr(instance, '_audit_user', None),
                model_name='AdHocSession',
                record_id=instance.id,
                action='update',
                field_name='status',
                old_value=old_status,
                new_value=instance.status,
            )
        instance._old_status = instance.status
