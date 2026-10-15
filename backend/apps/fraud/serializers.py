from rest_framework import serializers

from .models import FraudAssessment, FraudIndicator


class FraudIndicatorSerializer(serializers.ModelSerializer):
    class Meta:
        model = FraudIndicator
        fields = ["code", "category", "description", "weight"]


class FraudAssessmentSerializer(serializers.ModelSerializer):
    """Staff only — never included in any customer response (REQ-FRD-010)."""
    indicators = FraudIndicatorSerializer(many=True, read_only=True)
    requested_by_name = serializers.CharField(source="requested_by.full_name", read_only=True, default=None)
    risk_level_display = serializers.CharField(source="get_risk_level_display", read_only=True)

    class Meta:
        model = FraudAssessment
        fields = ["id", "status", "trigger", "risk_score", "risk_level", "risk_level_display", "flagged", "engine",
                  "error_message", "response_ms", "requested_by_name", "created_at", "indicators"]
