from rest_framework import serializers

from apps.vehicles.models import Vehicle

from .models import Policy, PolicyPlan, PolicyRequest


class PolicyPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = PolicyPlan
        fields = ["id", "code", "name", "description", "premium_rate_percent", "term_months", "min_idv", "max_idv",
                  "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        lo = attrs.get("min_idv", getattr(self.instance, "min_idv", None))
        hi = attrs.get("max_idv", getattr(self.instance, "max_idv", None))
        if lo is not None and hi is not None and hi < lo:
            raise serializers.ValidationError({"max_idv": "Maximum IDV must be ≥ minimum IDV."})
        return attrs


class VehicleBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vehicle
        fields = ["id", "registration_number", "make", "model", "vehicle_type", "manufacturing_year", "color"]


class PolicyRequestSerializer(serializers.ModelSerializer):
    vehicle = VehicleBriefSerializer(read_only=True)
    vehicle_id = serializers.PrimaryKeyRelatedField(source="vehicle", queryset=Vehicle.objects.all(), write_only=True)
    plan = PolicyPlanSerializer(read_only=True)
    plan_id = serializers.PrimaryKeyRelatedField(source="plan", queryset=PolicyPlan.objects.all(), write_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    customer_name = serializers.CharField(source="customer.user.full_name", read_only=True)
    customer_email = serializers.CharField(source="customer.user.email", read_only=True)
    reviewed_by_name = serializers.CharField(source="reviewed_by.full_name", read_only=True, default=None)
    policy_number = serializers.SerializerMethodField()

    class Meta:
        model = PolicyRequest
        fields = ["id", "vehicle", "vehicle_id", "plan", "plan_id", "requested_idv", "notes", "status",
                  "status_display", "customer_name", "customer_email", "reviewed_by_name", "reviewed_at",
                  "decision_note", "policy_number", "created_at"]
        read_only_fields = ["id", "status", "reviewed_at", "decision_note", "created_at"]

    def get_policy_number(self, obj):
        policy = getattr(obj, "policy", None)
        return policy.policy_number if policy else None

    def validate_requested_idv(self, value):
        if value <= 0:
            raise serializers.ValidationError("IDV must be greater than zero.")
        return value


class ApproveRequestSerializer(serializers.Serializer):
    start_date = serializers.DateField(required=False)
    idv = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, min_value=1)
    decision_note = serializers.CharField(max_length=500, required=False, allow_blank=True)


class ReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=1000, trim_whitespace=True)


class PolicySerializer(serializers.ModelSerializer):
    vehicle = VehicleBriefSerializer(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    remaining_idv = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    customer_name = serializers.CharField(source="customer.user.full_name", read_only=True)
    customer_email = serializers.CharField(source="customer.user.email", read_only=True)
    claim_count = serializers.SerializerMethodField()
    is_claimable = serializers.SerializerMethodField()

    class Meta:
        model = Policy
        fields = ["id", "policy_number", "vehicle", "plan_name", "premium_rate_percent", "start_date", "end_date",
                  "idv", "premium_amount", "cumulative_approved_amount", "remaining_idv", "status", "status_display",
                  "customer_name", "customer_email", "claim_count", "is_claimable", "cancelled_at",
                  "cancellation_reason", "created_at"]
        read_only_fields = fields

    def get_claim_count(self, obj):
        return obj.claims.count()

    def get_is_claimable(self, obj):
        return obj.status in ("ACTIVE", "PARTIALLY_CLAIMED")
