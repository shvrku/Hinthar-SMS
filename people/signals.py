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


# ---- Payslip auditing ----

@receiver(post_save, sender='payroll.Payslip')
def audit_payslip_post_save(sender, instance, created, **kwargs):
    action = 'create' if created else 'update'
    _log_action(
        user=getattr(instance, '_audit_user', None),
        model_name='Payslip',
        record_id=instance.id,
        action=action,
        new_value=f"status={instance.status}, net_pay={instance.net_pay}, gross_pay={instance.gross_pay}",
    )


# ---- Session auditing (status & paid changes) ----

@receiver(pre_save, sender='class_sessions.Session')
def audit_session_pre_save(sender, instance, **kwargs):
    """Capture old values before save for status/paid field changes."""
    if instance.pk:
        try:
            old = sender.objects.get(pk=instance.pk)
            instance._old_status = old.status
            instance._old_paid = old.paid
        except sender.DoesNotExist:
            instance._old_status = None
            instance._old_paid = None
    else:
        instance._old_status = None
        instance._old_paid = None


@receiver(post_save, sender='class_sessions.Session')
def audit_session_post_save(sender, instance, created, **kwargs):
    if created:
        _log_action(
            user=getattr(instance, '_audit_user', None),
            model_name='Session',
            record_id=instance.id,
            action='create',
            new_value=f"status={instance.status}, date={instance.session_date}",
        )
    else:
        # Check status change
        old_status = getattr(instance, '_old_status', None)
        old_paid = getattr(instance, '_old_paid', None)

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
        if old_paid is not None and old_paid != instance.paid:
            _log_action(
                user=getattr(instance, '_audit_user', None),
                model_name='Session',
                record_id=instance.id,
                action='update',
                field_name='paid',
                old_value=old_paid,
                new_value=instance.paid,
            )
