from rest_framework import serializers

from .models import ClaimDocument, DocumentReview


class DocumentReviewSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.full_name", read_only=True)

    class Meta:
        model = DocumentReview
        fields = ["id", "action", "actor_name", "reason", "created_at"]


class ClaimDocumentSerializer(serializers.ModelSerializer):
    document_type_display = serializers.CharField(source="get_document_type_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    uploaded_by_name = serializers.CharField(source="uploaded_by.full_name", read_only=True)
    uploaded_by_role = serializers.CharField(source="uploaded_by.role", read_only=True)
    verified_by_name = serializers.CharField(source="verified_by.full_name", read_only=True, default=None)
    replaced_by_id = serializers.SerializerMethodField()
    download_url = serializers.SerializerMethodField()
    reviews = DocumentReviewSerializer(many=True, read_only=True)

    class Meta:
        model = ClaimDocument
        fields = ["id", "document_type", "document_type_display", "original_filename", "content_type", "size_bytes",
                  "status", "status_display", "is_current", "replaces", "replaced_by_id", "appeal",
                  "uploaded_by_name", "uploaded_by_role", "uploaded_at", "verified_by_name", "verified_at",
                  "rejection_reason", "download_url", "reviews"]

    def get_replaced_by_id(self, obj):
        rep = getattr(obj, "replaced_by", None)
        return rep.pk if rep else None

    def get_download_url(self, obj):
        return f"/api/documents/{obj.pk}/download/"


class DocumentUploadSerializer(serializers.Serializer):
    document_type = serializers.CharField()
    file = serializers.FileField()
    replaces = serializers.IntegerField(required=False)


class DocumentRejectSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500)
