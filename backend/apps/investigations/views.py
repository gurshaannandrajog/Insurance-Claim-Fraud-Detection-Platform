from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import IsSIU, IsStaff

from . import services
from .models import Investigation
from .serializers import InvestigationCompleteSerializer, InvestigationProgressSerializer, InvestigationSerializer


class InvestigationViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """SIU work queue. Adjusters/administrators can read findings; only SIU can write (REQ-FRD-011)."""
    serializer_class = InvestigationSerializer

    def get_permissions(self):
        return [IsSIU()] if self.action in ("start", "progress", "complete") else [IsStaff()]

    def get_queryset(self):
        qs = Investigation.objects.select_related("claim__policy__customer__user", "investigator", "opened_by",
                                                  "assessment").prefetch_related("notes__author",
                                                                                 "assessment__indicators")
        p = self.request.query_params
        if p.get("status"):
            qs = qs.filter(status__in=p["status"].split(","))
        if p.get("mine") == "true":
            qs = qs.filter(investigator=self.request.user)
        if p.get("claim"):
            qs = qs.filter(claim_id=p["claim"])
        return qs

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        return Response(self.get_serializer(services.start_investigation(request.user, self.get_object(),
                                                                         request)).data)

    @action(detail=True, methods=["post"])
    def progress(self, request, pk=None):
        s = InvestigationProgressSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        inv = services.save_progress(request.user, self.get_object(), request=request, **s.validated_data)
        return Response(self.get_serializer(inv).data)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        s = InvestigationCompleteSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        inv = services.complete_investigation(request.user, self.get_object(), request=request, **s.validated_data)
        return Response(self.get_serializer(inv).data)
