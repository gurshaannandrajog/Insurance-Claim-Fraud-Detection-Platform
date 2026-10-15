from django.utils import timezone
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import IsAnyRole

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    type_display = serializers.CharField(source="get_type_display", read_only=True)

    class Meta:
        model = Notification
        fields = ["id", "type", "type_display", "title", "message", "claim", "link", "is_read", "read_at",
                  "email_status", "created_at"]


class NotificationViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Each user only ever sees their own notifications."""
    permission_classes = [IsAnyRole]
    serializer_class = NotificationSerializer

    def get_queryset(self):
        qs = Notification.objects.filter(recipient=self.request.user)
        if self.request.query_params.get("unread") == "true":
            qs = qs.filter(is_read=False)
        return qs

    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request):
        return Response({"unread": Notification.objects.filter(recipient=request.user, is_read=False).count()})

    @action(detail=True, methods=["post"], url_path="read")
    def mark_read(self, request, pk=None):
        note = self.get_object()
        if not note.is_read:
            note.is_read, note.read_at = True, timezone.now()
            note.save(update_fields=["is_read", "read_at"])
        return Response(self.get_serializer(note).data)

    @action(detail=False, methods=["post"], url_path="read-all")
    def mark_all_read(self, request):
        n = Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True,
                                                                                    read_at=timezone.now())
        return Response({"updated": n})
