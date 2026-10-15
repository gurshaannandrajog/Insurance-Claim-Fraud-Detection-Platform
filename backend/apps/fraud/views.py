from rest_framework import mixins, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsFraudAuthorised
from apps.claims.selectors import claims_visible_to

from . import client
from .models import FraudAssessment
from .serializers import FraudAssessmentSerializer


class FraudAssessmentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """REQ-FRD-008/009 — adjusters, SIU and administrators only. Customers get 403."""
    permission_classes = [IsFraudAuthorised]
    serializer_class = FraudAssessmentSerializer

    def get_queryset(self):
        qs = FraudAssessment.objects.filter(claim__in=claims_visible_to(self.request.user)).prefetch_related(
            "indicators").select_related("requested_by")
        if self.request.query_params.get("claim"):
            qs = qs.filter(claim_id=self.request.query_params["claim"])
        return qs


class FraudServiceHealthView(APIView):
    permission_classes = [IsFraudAuthorised]

    def get(self, request):
        return Response({"fraud_service_available": client.health()})
