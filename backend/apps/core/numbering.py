"""Race-free human-readable numbers: insert with a unique temporary value, then derive from the primary key."""
import uuid

from django.utils import timezone


def temporary_number():
    return "TMP-" + uuid.uuid4().hex[:18]


def assign_number(obj, prefix, field):
    value = f"{prefix}-{timezone.localdate():%Y}-{obj.pk:06d}"
    type(obj).objects.filter(pk=obj.pk).update(**{field: value})
    setattr(obj, field, value)
    return value
