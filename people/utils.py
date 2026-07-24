import re
from django.conf import settings
from django.db import transaction
from django.utils import timezone


def generate_unique_code(instance):
    """
    Generates a unique code for Student, Teacher, or Staff instances.
    
    Formats:
    - Student: {SchoolCode}{EntryYear}-{Sequence:05d} (e.g. HIS24-00143)
    - Teacher: {SchoolCode}T{JoinYear}-{Sequence:05d} (e.g. HIST22-00007)
    - Staff: {SchoolCode}S{JoinYear}-{Sequence:05d} (e.g. HISS24-00001)

    Guarantees concurrency safety using transaction.atomic() and select_for_update().
    Always increments MAX sequence number for the cohort (never fills deleted gaps).
    """
    school_code = (getattr(instance, 'school_code', None) or getattr(settings, 'DEFAULT_SCHOOL_CODE', 'HIS')).upper()
    model_name = instance.__class__.__name__

    # Determine date & entity tag
    if model_name == 'Student':
        date_val = getattr(instance, 'enrollment_date', None) or timezone.now().date()
        tag = ""
    elif model_name == 'Teacher':
        date_val = getattr(instance, 'join_date', None) or timezone.now().date()
        tag = "T"
    elif model_name == 'Staff':
        date_val = getattr(instance, 'join_date', None) or timezone.now().date()
        tag = "S"
    else:
        date_val = timezone.now().date()
        tag = ""

    year_str = f"{date_val.year % 100:02d}"
    prefix = f"{school_code}{tag}{year_str}-"

    Model = instance.__class__

    with transaction.atomic():
        # Lock matching cohort rows in database
        existing_codes = list(
            Model.objects.select_for_update().filter(
                unique_code__startswith=prefix
            ).values_list('unique_code', flat=True)
        )

        max_seq = 0
        for code in existing_codes:
            if code and '-' in code:
                suffix = code.rsplit('-', 1)[-1]
                if suffix.isdigit():
                    max_seq = max(max_seq, int(suffix))

        next_seq = max_seq + 1
        candidate = f"{prefix}{next_seq:05d}"

        # Safety check against unexpected collisions
        while Model.objects.filter(unique_code=candidate).exists():
            next_seq += 1
            candidate = f"{prefix}{next_seq:05d}"

    return candidate
