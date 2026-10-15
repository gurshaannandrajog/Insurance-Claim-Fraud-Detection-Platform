from django.db.models import Q
from rest_framework import mixins, status, viewsets
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.accounts.permissions import IsAnyRole, IsCustomer

from . import services
from .models import Vehicle
from .serializers import VehicleSerializer


class VehicleViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                     mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """
    Customers: own vehicles only (REQ-VEH-011/012, REQ-CUST-008) — other customers' vehicles return 404.
    Staff: read-only. There is intentionally no DELETE (REQ-VEH-010).
    """
    serializer_class = VehicleSerializer
    http_method_names = ["get", "post", "patch"]

    def get_permissions(self):
        if self.action in ("create", "partial_update", "update"):
            return [IsCustomer()]
        return [IsAnyRole()]

    def get_queryset(self):
        qs = Vehicle.objects.select_related("customer__user").prefetch_related("policies")
        user = self.request.user
        if user.role == Role.CUSTOMER:
            qs = qs.filter(customer__user=user)
        q = self.request.query_params.get("search")
        if q:
            qs = qs.filter(Q(registration_number__icontains=q) | Q(make__icontains=q) | Q(model__icontains=q))
        return qs

    def create(self, request, *args, **kwargs):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        vehicle = services.create_vehicle(request.user.customer_profile, s.validated_data, request)
        return Response(self.get_serializer(vehicle).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        vehicle = self.get_object()
        s = self.get_serializer(vehicle, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        vehicle = services.update_vehicle(vehicle, s.validated_data, request)
        return Response(self.get_serializer(vehicle).data)
