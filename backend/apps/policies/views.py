from django.db.models import Q
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.accounts.permissions import IsAdmin, IsAnyRole, IsCustomer
from apps.audit.models import AuditAction
from apps.audit.services import log_event

from . import services
from .models import Policy, PolicyPlan, PolicyRequest, PolicyRequestStatus
from .serializers import (ApproveRequestSerializer, PolicyPlanSerializer, PolicyRequestSerializer, PolicySerializer,
                          ReasonSerializer)


class PolicyPlanViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                        mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Plan configuration (admin). Customers see active plans when requesting a policy."""
    serializer_class = PolicyPlanSerializer
    http_method_names = ["get", "post", "patch"]
    pagination_class = None

    def get_permissions(self):
        return [IsAdmin()] if self.action in ("create", "partial_update", "update") else [IsAnyRole()]

    def get_queryset(self):
        qs = PolicyPlan.objects.all()
        if self.request.user.role != Role.ADMIN:
            qs = qs.filter(is_active=True)
        return qs

    def perform_create(self, serializer):
        plan = serializer.save()
        log_event(AuditAction.POLICY_PLAN_CHANGED, plan, request=self.request, metadata={"created": serializer.data})

    def perform_update(self, serializer):
        plan = serializer.save()
        log_event(AuditAction.POLICY_PLAN_CHANGED, plan, request=self.request,
                  metadata={"changed": {k: str(v) for k, v in serializer.validated_data.items()},
                            "note": "Existing policies keep their snapshot terms (REQ-POL-015)"})


class PolicyRequestViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                           viewsets.GenericViewSet):
    serializer_class = PolicyRequestSerializer

    def get_permissions(self):
        if self.action in ("create", "withdraw"):
            return [IsCustomer()]
        if self.action in ("approve", "reject"):
            return [IsAdmin()]
        return [IsAnyRole()]

    def get_queryset(self):
        qs = PolicyRequest.objects.select_related("vehicle", "plan", "customer__user", "reviewed_by", "policy")
        user = self.request.user
        if user.role == Role.CUSTOMER:
            qs = qs.filter(customer__user=user)
        elif user.role != Role.ADMIN:
            qs = qs.none()
        st = self.request.query_params.get("status")
        if st:
            qs = qs.filter(status=st)
        return qs

    def create(self, request, *args, **kwargs):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        pr = services.create_policy_request(request.user.customer_profile, request=request, **s.validated_data)
        return Response(self.get_serializer(pr).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def withdraw(self, request, pk=None):
        pr = services.withdraw_policy_request(self.get_object(), request)
        return Response(self.get_serializer(pr).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        s = ApproveRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        policy = services.approve_policy_request(request.user, self.get_object(), request=request, **s.validated_data)
        return Response(PolicySerializer(policy).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        s = ReasonSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        pr = services.reject_policy_request(request.user, self.get_object(), s.validated_data["reason"], request)
        return Response(self.get_serializer(pr).data)


class PolicyViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Read-only for everyone (REQ-POL-006: no customer edits); administrators may cancel."""
    serializer_class = PolicySerializer

    def get_permissions(self):
        return [IsAdmin()] if self.action == "cancel" else [IsAnyRole()]

    def get_queryset(self):
        qs = Policy.objects.select_related("vehicle", "customer__user").prefetch_related("claims")
        user = self.request.user
        if user.role == Role.CUSTOMER:
            qs = qs.filter(customer__user=user)          # REQ-POL-016
        p = self.request.query_params
        if p.get("status"):
            qs = qs.filter(status__in=p["status"].split(","))
        if p.get("vehicle"):
            qs = qs.filter(vehicle_id=p["vehicle"])
        if p.get("search"):
            q = p["search"]
            qs = qs.filter(Q(policy_number__icontains=q) | Q(vehicle__registration_number__icontains=q) |
                           Q(customer__user__full_name__icontains=q))
        return qs

    def list(self, request, *args, **kwargs):
        services.expire_due_policies()  # keep statuses correct even if the scheduler has not run yet
        return super().list(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        s = ReasonSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        policy = services.cancel_policy(request.user, self.get_object(), s.validated_data["reason"], request)
        return Response(self.get_serializer(policy).data)


__all__ = ["PolicyPlanViewSet", "PolicyRequestViewSet", "PolicyViewSet", "PolicyRequestStatus"]
