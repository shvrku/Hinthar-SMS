from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from people.audit import CATEGORY_SESSION, is_muted, log_event


def _session_label(instance):
    class_obj = getattr(instance, 'class_obj', None)
    start = getattr(instance, 'start_time', None)
    date_str = start.strftime('%d/%m/%y') if start else ''
    if class_obj:
        return f"{class_obj} on {date_str}".strip()
    return f"#{instance.pk} on {date_str}".strip()


def _adhoc_label(instance):
    subject = getattr(instance, 'subject', None)
    day = getattr(instance, 'date', None)
    date_str = day.strftime('%d/%m/%y') if day else ''
    name = str(subject) if subject else f'#{instance.pk}'
    return f"{name} on {date_str}".strip()


def _capture_old_status(sender, instance):
    """
    Prefer status loaded via Model.from_db (_old_status already set).
    Only hit the DB when the instance was constructed without from_db
    (e.g. Session(pk=…) then field assign) and status may have changed.
    """
    if getattr(instance, '_skip_audit', False) or is_muted():
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
    if getattr(instance, '_skip_audit', False) or is_muted():
        return
    label = _session_label(instance)
    if created:
        log_event(
            user=getattr(instance, '_audit_user', None),
            category=CATEGORY_SESSION,
            action='create',
            summary=f"Created session {label}",
            model_name='Session',
            record_id=instance.id,
            new_value=instance.status,
        )
        instance._old_status = instance.status
        return

    old_status = getattr(instance, '_old_status', None)
    if old_status is not None and old_status != instance.status:
        log_event(
            user=getattr(instance, '_audit_user', None),
            category=CATEGORY_SESSION,
            action='update',
            summary=f"Marked session {label} as {instance.status}",
            model_name='Session',
            record_id=instance.id,
            field_name='status',
            old_value=old_status,
            new_value=instance.status,
        )
    instance._old_status = instance.status


@receiver(post_delete, sender='class_sessions.Session')
def audit_session_post_delete(sender, instance, **kwargs):
    if getattr(instance, '_skip_audit', False) or is_muted():
        return
    log_event(
        user=getattr(instance, '_audit_user', None),
        category=CATEGORY_SESSION,
        action='delete',
        summary=f"Deleted session {_session_label(instance)}",
        model_name='Session',
        record_id=instance.pk,
    )


@receiver(pre_save, sender='class_sessions.AdHocSession')
def audit_adhoc_session_pre_save(sender, instance, **kwargs):
    _capture_old_status(sender, instance)


@receiver(post_save, sender='class_sessions.AdHocSession')
def audit_adhoc_session_post_save(sender, instance, created, **kwargs):
    if getattr(instance, '_skip_audit', False) or is_muted():
        return
    label = _adhoc_label(instance)
    if created:
        log_event(
            user=getattr(instance, '_audit_user', None),
            category=CATEGORY_SESSION,
            action='create',
            summary=f"Created ad-hoc session {label}",
            model_name='AdHocSession',
            record_id=instance.id,
            new_value=instance.status,
        )
        instance._old_status = instance.status
        return

    old_status = getattr(instance, '_old_status', None)
    if old_status is not None and old_status != instance.status:
        log_event(
            user=getattr(instance, '_audit_user', None),
            category=CATEGORY_SESSION,
            action='update',
            summary=f"Marked ad-hoc session {label} as {instance.status}",
            model_name='AdHocSession',
            record_id=instance.id,
            field_name='status',
            old_value=old_status,
            new_value=instance.status,
        )
    instance._old_status = instance.status


@receiver(post_delete, sender='class_sessions.AdHocSession')
def audit_adhoc_session_post_delete(sender, instance, **kwargs):
    if getattr(instance, '_skip_audit', False) or is_muted():
        return
    log_event(
        user=getattr(instance, '_audit_user', None),
        category=CATEGORY_SESSION,
        action='delete',
        summary=f"Deleted ad-hoc session {_adhoc_label(instance)}",
        model_name='AdHocSession',
        record_id=instance.pk,
    )
