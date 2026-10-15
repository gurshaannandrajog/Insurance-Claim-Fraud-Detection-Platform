from django.db.models import Q
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.accounts.permissions import IsAdjuster, IsAnyRole, IsCustomer
from apps.core.filters import day_range_q
from apps.documents import services as doc_services
from apps.documents.serializers import ClaimDocumentSerializer, DocumentUploadSerializer
from apps.fraud.serializers import FraudAssessmentSerializer

from . import services
from .models import Appeal, AppealStatus
from .selectors import claims_visible_to
from .serializers import (AppealDecisionSerializer, AppealSerializer, ApproveSerializer, ClaimCreateSerializer,
                          ClaimCustomerSerializer, ClaimInputSerializer, ClaimListCustomerSerializer,
                          ClaimListStaffSerializer, ClaimStaffSerializer, NoteSerializer, ReasonSerializer,
                          RejectSerializer)

CUSTOMER_ACTIONS = {"create", "partial_update", "withdraw", "appeal", "accept_decision"}
ADJUSTER_ACTIONS = {"start_review", "request_documents", "escalate", "approve", "reject", "rerun_fraud"}


def parse_documents(request, types_key="document_types", files_key="files"):
    """Multipart: parallel lists `document_types[]` and `files[]` (same order)."""
    types = request.data.getlist(types_key) if hasattr(request.data, "getlist") else []
    files = request.FILES.getlist(files_key)
    if len(types) != len(files):
        raise ValidationError({"documents": ["Each uploaded file needs exactly one document type."]})
    return list(zip(types, files))


class ClaimViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    http_method_names = ["get", "post", "patch"]

    def get_permissions(self):
        if self.action in CUSTOMER_ACTIONS:
            return [IsCustomer()]
        if self.action in ADJUSTER_ACTIONS:
            return [IsAdjuster()]
        return [IsAnyRole()]

    def get_queryset(self):
        qs = claims_visible_to(self.request.user)
        p = self.request.query_params
        if p.get("status"):
            qs = qs.filter(status__in=p["status"].split(","))
        if p.get("claim_type"):
            qs = qs.filter(claim_type=p["claim_type"])
        if p.get("policy"):
            qs = qs.filter(policy_id=p["policy"])
        if self.request.user.role != Role.CUSTOMER:
            if p.get("risk_level"):
                qs = qs.filter(current_risk_level=p["risk_level"])
            if p.get("flagged") == "true":
                qs = qs.filter(is_flagged=True)
            if p.get("assigned") == "me":
                qs = qs.filter(assigned_adjuster=self.request.user)
            if p.get("assigned") == "none":
                qs = qs.filter(assigned_adjuster__isnull=True)
        qs = qs.filter(day_range_q("submitted_at", p.get("date_from"), p.get("date_to")))
        if p.get("search"):
            q = p["search"]
            qs = qs.filter(Q(claim_number__icontains=q) | Q(policy__vehicle__registration_number__icontains=q) |
                           Q(policy__policy_number__icontains=q) | Q(policy__customer__user__full_name__icontains=q))
        ordering = p.get("ordering")
        if ordering in {"submitted_at", "-submitted_at", "requested_amount", "-requested_amount",
                        "current_risk_score", "-current_risk_score"}:
            qs = qs.order_by(ordering)
        return qs

    def get_serializer_class(self):
        customer = self.request.user.role == Role.CUSTOMER
        if self.action == "list":
            return ClaimListCustomerSerializer if customer else ClaimListStaffSerializer
        return ClaimCustomerSerializer if customer else ClaimStaffSerializer

    def _respond(self, claim, code=status.HTTP_200_OK):
        claim = self.get_queryset().model.objects.get(pk=claim.pk)
        return Response(self.get_serializer_class()(claim, context={"request": self.request}).data, status=code)

    # ------------------------------------------------------------------ customer
    def create(self, request):
        s = ClaimCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = dict(s.validated_data)
        claim = services.submit_claim(request.user, vehicle_id=data.pop("vehicle_id"),
                                      policy_id=data.pop("policy_id"), data=data,
                                      documents=parse_documents(request), request=request)
        return self._respond(claim, status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        claim = self.get_object()
        s = ClaimInputSerializer(data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        claim = services.edit_claim(request.user, claim, s.validated_data, request)
        return self._respond(claim)

    @action(detail=True, methods=["post"])
    def withdraw(self, request, pk=None):
        return self._respond(services.withdraw_claim(request.user, self.get_object(), request))

    @action(detail=True, methods=["post"], url_path="accept-decision")
    def accept_decision(self, request, pk=None):
        return self._respond(services.accept_rejection(request.user, self.get_object(), request))

    @action(detail=True, methods=["post"])
    def appeal(self, request, pk=None):
        reason = request.data.get("reason", "")
        services.submit_appeal(request.user, self.get_object(), reason, parse_documents(request), request)
        return self._respond(self.get_object(), status.HTTP_201_CREATED)

    # ------------------------------------------------------------------ documents (customer + adjuster)
    @action(detail=True, methods=["get", "post"])
    def documents(self, request, pk=None):
        claim = self.get_object()   # 404 if the user may not see the claim (IDOR protection)
        if request.method == "GET":
            return Response(ClaimDocumentSerializer(claim.documents.all(), many=True).data)
        s = DocumentUploadSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        doc = doc_services.upload_document(request.user, claim, s.validated_data["file"],
                                           s.validated_data["document_type"],
                                           replaces_id=s.validated_data.get("replaces"), request=request)
        return Response(ClaimDocumentSerializer(doc).data, status=status.HTTP_201_CREATED)

    # ------------------------------------------------------------------ adjuster
    @action(detail=True, methods=["post"], url_path="start-review")
    def start_review(self, request, pk=None):
        return self._respond(services.start_review(request.user, self.get_object(), request))

    @action(detail=True, methods=["post"], url_path="request-documents")
    def request_documents(self, request, pk=None):
        s = NoteSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return self._respond(services.request_documents(request.user, self.get_object(), s.validated_data["note"],
                                                        request))

    @action(detail=True, methods=["post"])
    def escalate(self, request, pk=None):
        s = ReasonSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return self._respond(services.escalate_to_siu(request.user, self.get_object(), s.validated_data["reason"],
                                                      request))

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        s = ApproveSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return self._respond(services.approve_claim(request.user, self.get_object(), request=request,
                                                    **s.validated_data))

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        s = RejectSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return self._respond(services.reject_claim(request.user, self.get_object(), request=request,
                                                   **s.validated_data))

    @action(detail=True, methods=["post"], url_path="rerun-fraud")
    def rerun_fraud(self, request, pk=None):
        assessment = services.rerun_fraud_assessment(request.user, self.get_object(), request)
        return Response(FraudAssessmentSerializer(assessment).data, status=status.HTTP_201_CREATED)


class AppealViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = AppealSerializer

    def get_permissions(self):
        return [IsAdjuster()] if self.action == "decide" else [IsAnyRole()]

    def get_queryset(self):
        qs = Appeal.objects.select_related("claim", "decided_by").filter(
            claim__in=claims_visible_to(self.request.user))
        if self.request.query_params.get("status"):
            qs = qs.filter(status=self.request.query_params["status"])
        return qs

    @action(detail=True, methods=["post"])
    def decide(self, request, pk=None):
        s = AppealDecisionSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        appeal = services.decide_appeal(request.user, self.get_object(), request=request, **s.validated_data)
        return Response(self.get_serializer(appeal).data)


__all__ = ["ClaimViewSet", "AppealViewSet", "AppealStatus"]
