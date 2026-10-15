from rest_framework import generics, serializers

from apps.accounts.permissions import IsAdmin
from apps.core.filters import day_range_q

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    action_display = serializers.CharField(source="get_action_display", read_only=True)

    class Meta:
        model = AuditLog
        fields = ["id", "actor_email", "actor_role", "action", "action_display", "entity_type", "entity_id",
                  "description", "metadata", "ip_address", "created_at"]


class AuditLogListView(generics.ListAPIView):
    """Read-only (no create/update/delete endpoint exists). Administrators only."""
    permission_classes = [IsAdmin]
    serializer_class = AuditLogSerializer

    def get_queryset(self):
        qs = AuditLog.objects.all()
        p = self.request.query_params
        for param, field in (("action", "action"), ("entity_type", "entity_type"), ("entity_id", "entity_id")):
            if p.get(param):
                qs = qs.filter(**{field: p[param]})
        if p.get("actor"):
            qs = qs.filter(actor_email__icontains=p["actor"])
        qs = qs.filter(day_range_q("created_at", p.get("date_from"), p.get("date_to")))
        return qs
