from django.db import IntegrityError, transaction

from apps.audit.models import AuditAction
from apps.audit.services import log_event
from apps.core.exceptions import ConflictError

from .models import Vehicle

UNIQUE_FIELDS = {"registration_number": "registration number", "engine_number": "engine number",
                 "chassis_number": "chassis number"}


def _check_unique(data, exclude_pk=None):
    for field, label in UNIQUE_FIELDS.items():
        if field in data and Vehicle.objects.exclude(pk=exclude_pk).filter(**{field: data[field]}).exists():
            raise ConflictError(f"A vehicle with this {label} is already registered.", code=f"duplicate_{field}",
                                fields={field: [f"This {label} is already registered."]})


def create_vehicle(customer_profile, data, request=None):
    _check_unique(data)
    try:
        with transaction.atomic():
            vehicle = Vehicle.objects.create(customer=customer_profile, **data)
            log_event(AuditAction.VEHICLE_CREATED, vehicle, request=request,
                      metadata={"registration_number": vehicle.registration_number})
    except IntegrityError:  # race between the check and the insert — DB unique index is the final guard
        raise ConflictError("A vehicle with these identifiers is already registered.", code="duplicate_vehicle")
    return vehicle


def update_vehicle(vehicle, data, request=None):
    with transaction.atomic():
        vehicle = Vehicle.objects.select_for_update().get(pk=vehicle.pk)
        if vehicle.is_locked:  # REQ-VEH-009
            raise ConflictError("Vehicle details cannot be changed after the vehicle is associated with a policy.",
                                code="vehicle_locked")
        _check_unique(data, exclude_pk=vehicle.pk)
        for k, v in data.items():
            setattr(vehicle, k, v)
        vehicle.save()
        log_event(AuditAction.VEHICLE_UPDATED, vehicle, request=request, metadata={"fields": sorted(data)})
    return vehicle
