from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.accounts.permissions import IsAdjuster, IsAnyRole
from apps.audit.models import AuditAction
from apps.audit.services import log_event

from . import services
from .models import ClaimDocument
from .serializers import ClaimDocumentSerializer, DocumentRejectSerializer


class DocumentViewSet(GenericViewSet):
    """
    Documents are never exposed as static files. Every download goes through this view, which re-checks that
    the requester may see the owning claim (REQ-DOC-012, REQ-SEC-013). Unauthorised → 404 (no existence leak).
    """
    queryset = ClaimDocument.objects.select_related("claim__policy__customer__user")
    serializer_class = ClaimDocumentSerializer

    def get_permissions(self):
        return [IsAdjuster()] if self.action in ("verify", "reject") else [IsAnyRole()]

    def _get_doc(self, pk):
        doc = get_object_or_404(self.queryset, pk=pk)
        if not services.can_access_document(self.request.user, doc):
            raise NotFound()
        return doc

    def retrieve(self, request, pk=None):
        return Response(self.get_serializer(self._get_doc(pk)).data)

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        doc = self._get_doc(pk)
        log_event(AuditAction.DOCUMENT_DOWNLOADED, doc, request=request, metadata={"claim": doc.claim.claim_number})
        inline = request.query_params.get("inline") == "1"
        resp = FileResponse(doc.file.open("rb"), content_type=doc.content_type, as_attachment=not inline,
                            filename=doc.original_filename)
        resp["X-Content-Type-Options"] = "nosniff"
        resp["Cache-Control"] = "private, no-store"
        return resp

    @action(detail=True, methods=["post"])
    def verify(self, request, pk=None):
        doc = services.verify_document(request.user, self._get_doc(pk), request)
        return Response(self.get_serializer(doc).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        s = DocumentRejectSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        doc = services.reject_document(request.user, self._get_doc(pk), s.validated_data["reason"], request)
        return Response(self.get_serializer(doc).data)
