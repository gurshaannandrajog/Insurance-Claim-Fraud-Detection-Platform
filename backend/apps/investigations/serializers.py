from rest_framework import serializers

from .models import Investigation, InvestigationNote, Recommendation


class InvestigationNoteSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source="author.full_name", read_only=True)

    class Meta:
        model = InvestigationNote
        fields = ["id", "author_name", "note", "created_at"]


class InvestigationSerializer(serializers.ModelSerializer):
    notes = InvestigationNoteSerializer(many=True, read_only=True)
    investigator_name = serializers.CharField(source="investigator.full_name", read_only=True, default=None)
    opened_by_name = serializers.CharField(source="opened_by.full_name", read_only=True, default=None)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    trigger_display = serializers.CharField(source="get_trigger_display", read_only=True)
    recommendation_display = serializers.CharField(source="get_recommendation_display", read_only=True)
    claim_id = serializers.IntegerField(source="claim.id", read_only=True)
    claim_number = serializers.CharField(source="claim.claim_number", read_only=True)
    claim_type = serializers.CharField(source="claim.claim_type", read_only=True)
    claim_status = serializers.CharField(source="claim.status", read_only=True)
    requested_amount = serializers.DecimalField(source="claim.requested_amount", max_digits=12, decimal_places=2,
                                                read_only=True)
    customer_name = serializers.CharField(source="claim.policy.customer.user.full_name", read_only=True)
    risk_score = serializers.IntegerField(source="claim.current_risk_score", read_only=True)
    risk_level = serializers.CharField(source="claim.current_risk_level", read_only=True)
    top_factors = serializers.SerializerMethodField()

    class Meta:
        model = Investigation
        fields = ["id", "claim_id", "claim_number", "claim_type", "claim_status", "requested_amount", "customer_name",
                  "risk_score", "risk_level", "top_factors", "trigger", "trigger_display", "trigger_reason",
                  "opened_by_name", "investigator_name", "status", "status_display", "findings", "evidence_notes",
                  "recommendation", "recommendation_display", "created_at", "started_at", "completed_at", "notes"]

    def get_top_factors(self, obj):
        a = obj.assessment
        return [i.description for i in a.indicators.all()[:3]] if a else []


class InvestigationProgressSerializer(serializers.Serializer):
    findings = serializers.CharField(required=False, allow_blank=True, max_length=5000)
    evidence_notes = serializers.CharField(required=False, allow_blank=True, max_length=5000)
    note = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class InvestigationCompleteSerializer(serializers.Serializer):
    findings = serializers.CharField(max_length=5000)
    evidence_notes = serializers.CharField(required=False, allow_blank=True, max_length=5000)
    recommendation = serializers.ChoiceField(choices=Recommendation.choices)
