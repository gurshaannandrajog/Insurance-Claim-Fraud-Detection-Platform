import re
from datetime import date

from rest_framework import serializers

from .models import Vehicle


class UpperNoSpaceField(serializers.CharField):
    def to_internal_value(self, data):
        return re.sub(r"\s+", "", super().to_internal_value(data)).upper()


class VehicleSerializer(serializers.ModelSerializer):
    registration_number = UpperNoSpaceField(max_length=15)
    engine_number = UpperNoSpaceField(max_length=30)
    chassis_number = UpperNoSpaceField(max_length=30)
    vehicle_type_display = serializers.CharField(source="get_vehicle_type_display", read_only=True)
    is_locked = serializers.BooleanField(read_only=True)
    current_policy = serializers.SerializerMethodField()
    customer_name = serializers.CharField(source="customer.user.full_name", read_only=True)
    customer_email = serializers.CharField(source="customer.user.email", read_only=True)

    class Meta:
        model = Vehicle
        fields = ["id", "registration_number", "make", "model", "vehicle_type", "vehicle_type_display",
                  "manufacturing_year", "registration_date", "purchase_date", "engine_number", "chassis_number",
                  "color", "owner_name", "owner_phone", "owner_address", "is_locked", "current_policy",
                  "customer_name", "customer_email", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_current_policy(self, obj):
        p = obj.current_policy
        if not p:
            return None
        return {"id": p.id, "policy_number": p.policy_number, "status": p.status, "end_date": p.end_date}

    def validate_owner_phone(self, value):
        if value and not re.fullmatch(r"\+?[0-9]{10,15}", value):
            raise serializers.ValidationError("Enter a valid phone number.")
        return value

    def validate(self, attrs):
        today = date.today()
        get = lambda k: attrs.get(k, getattr(self.instance, k, None))  # noqa: E731
        errors = {}
        year, reg, pur = get("manufacturing_year"), get("registration_date"), get("purchase_date")
        if year and year > today.year:
            errors["manufacturing_year"] = "Manufacturing year cannot be in the future."
        for key, d in (("registration_date", reg), ("purchase_date", pur)):
            if d and d > today:
                errors[key] = "Date cannot be in the future."
            elif d and year and d.year < year:
                errors[key] = "Date cannot be before the manufacturing year."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs
