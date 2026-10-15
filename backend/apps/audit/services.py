from .models import AuditLog


def client_ip(request):
    if request is None:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def log_event(action, entity, *, actor=None, request=None, description="", metadata=None, entity_type=None):
    """Write one audit row. `entity` may be a model instance or None (then pass entity_type)."""
    if actor is None and request is not None and getattr(request, "user", None) and request.user.is_authenticated:
        actor = request.user
    if actor is not None and not getattr(actor, "is_authenticated", False):
        actor = None
    return AuditLog.objects.create(
        actor=actor,
        actor_email=getattr(actor, "email", "") or "",
        actor_role=getattr(actor, "role", "") or "",
        action=action,
        entity_type=entity_type or (entity._meta.model_name if entity is not None else "system"),
        entity_id=str(getattr(entity, "pk", "") or ""),
        description=description[:255],
        metadata=metadata or {},
        ip_address=client_ip(request),
    )
