"""
Two output serializers on purpose:
* ClaimCustomerSerializer — what a policyholder may see. It has NO fraud fields at all, maps FRAUD_REVIEW to
  UNDER_REVIEW and strips reasons from internal timeline entries (REQ-FRD-010, REQ-BR-019, REQ-SEC-012).
* ClaimStaffSerializer — adjusters, SIU, administrators.
Choosing the serializer by role (not hiding fields in the UI) is what actually protects the data.
"""
from django.utils import timezone
from rest_framework import serializers

from apps.documents.serializers import ClaimDocumentSerializer
from apps.documents.services import document_checklist
from apps.fraud.serializers import FraudAssessmentSerializer
from apps.investigations.serializers import InvestigationSerializer

from .models import Appeal, Claim, ClaimStatus, ClaimType
from .selectors import available_actions
from .services import appeal_deadline
from .workflow import customer_visible_status


class ClaimInputSerializer(serializers.Serializer):
    claim_type = serializers.ChoiceField(choices=ClaimType.choices)
    incident_date = serializers.DateField()
    incident_time = serializers.TimeField()
    incident_location = serializers.CharField(min_length=3, max_length=255)
    description = serializers.CharField(min_length=20, max_length=5000)
    requested_amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=1)


class ClaimCreateSerializer(ClaimInputSerializer):
    vehicle_id = serializers.IntegerField()
    policy_id = serializers.IntegerField()


class AppealSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    decided_by_name = serializers.CharField(source="decided_by.full_name", read_only=True, default=None)
    claim_id = serializers.IntegerField(source="claim.id", read_only=True)
    claim_number = serializers.CharField(source="claim.claim_number", read_only=True)

    class Meta:
        model = Appeal
        fields = ["id", "claim_id", "claim_number", "sequence", "reason", "status", "status_display",
                  "decided_by_name", "decided_at", "decision_note", "further_appeal_allowed", "created_at"]


def _vehicle(claim):
    v = claim.policy.vehicle
    return {"id": v.id, "registration_number": v.registration_number, "make": v.make, "model": v.model,
            "vehicle_type": v.vehicle_type, "manufacturing_year": v.manufacturing_year, "color": v.color,
            "owner_name": v.owner_name, "engine_number": v.engine_number, "chassis_number": v.chassis_number}


def _policy(claim):
    p = claim.policy
    return {"id": p.id, "policy_number": p.policy_number, "plan_name": p.plan_name, "status": p.status,
            "status_display": p.get_status_display(), "start_date": p.start_date, "end_date": p.end_date,
            "idv": p.idv, "cumulative_approved_amount": p.cumulative_approved_amount, "remaining_idv": p.remaining_idv}


class ClaimListCustomerSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()
    status_display = serializers.SerializerMethodField()
    claim_type_display = serializers.CharField(source="get_claim_type_display", read_only=True)
    vehicle_registration = serializers.CharField(source="policy.vehicle.registration_number", read_only=True)
    policy_number = serializers.CharField(source="policy.policy_number", read_only=True)

    class Meta:
        model = Claim
        fields = ["id", "claim_number", "claim_type", "claim_type_display", "incident_date", "requested_amount",
                  "approved_amount", "status", "status_display", "vehicle_registration", "policy_number",
                  "submitted_at", "updated_at"]

    def get_status(self, obj):
        return customer_visible_status(obj.status)

    def get_status_display(self, obj):
        return ClaimStatus(customer_visible_status(obj.status)).label


class ClaimCustomerSerializer(ClaimListCustomerSerializer):
    vehicle = serializers.SerializerMethodField()
    policy = serializers.SerializerMethodField()
    timeline = serializers.SerializerMethodField()
    documents = serializers.SerializerMethodField()
    document_checklist = serializers.SerializerMethodField()
    appeals = AppealSerializer(many=True, read_only=True)
    is_editable = serializers.BooleanField(read_only=True)
    edit_deadline = serializers.DateTimeField(read_only=True)
    edit_seconds_remaining = serializers.SerializerMethodField()
    appeal_deadline = serializers.SerializerMethodField()
    actions = serializers.SerializerMethodField()

    class Meta(ClaimListCustomerSerializer.Meta):
        fields = ClaimListCustomerSerializer.Meta.fields + [
            "incident_time", "incident_location", "description", "rejection_reason", "decided_at",
            "further_appeal_allowed", "appeal_count", "closure_reason", "vehicle", "policy", "timeline",
            "documents", "document_checklist", "appeals", "is_editable", "edit_deadline", "edit_seconds_remaining",
            "appeal_deadline", "actions"]

    def get_vehicle(self, obj):
        return _vehicle(obj)

    def get_policy(self, obj):
        return _policy(obj)

    def get_timeline(self, obj):
        out, last = [], None
        for h in obj.history.select_related("actor").all():
            to = customer_visible_status(h.to_status)
            frm = customer_visible_status(h.from_status) if h.from_status else ""
            if h.is_internal:
                if to == last:      # e.g. UNDER_REVIEW → FRAUD_REVIEW looks like no change to the customer
                    continue
                reason = "Your claim is being reviewed."
            else:
                reason = h.reason
            actor = None if (h.is_internal or h.actor is None) else (
                "You" if h.actor_id == obj.policy.customer.user_id else h.actor.get_role_display())
            out.append({"id": h.id, "from_status": frm, "to_status": to, "to_status_display": ClaimStatus(to).label,
                        "reason": reason, "actor": actor, "created_at": h.created_at})
            last = to
        return out

    def get_documents(self, obj):
        docs = obj.documents.select_related("uploaded_by", "verified_by", "replaced_by").prefetch_related(
            "reviews__actor")
        return ClaimDocumentSerializer(docs, many=True).data

    def get_document_checklist(self, obj):
        return document_checklist(obj)

    def get_edit_seconds_remaining(self, obj):
        if not obj.is_editable:
            return 0
        return max(0, int((obj.edit_deadline - timezone.now()).total_seconds()))

    def get_appeal_deadline(self, obj):
        return appeal_deadline(obj) if obj.status == ClaimStatus.REJECTED else None

    def get_actions(self, obj):
        return available_actions(obj, self.context["request"].user)


class ClaimListStaffSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    claim_type_display = serializers.CharField(source="get_claim_type_display", read_only=True)
    vehicle_registration = serializers.CharField(source="policy.vehicle.registration_number", read_only=True)
    policy_number = serializers.CharField(source="policy.policy_number", read_only=True)
    customer_name = serializers.CharField(source="policy.customer.user.full_name", read_only=True)
    assigned_adjuster_name = serializers.CharField(source="assigned_adjuster.full_name", read_only=True, default=None)

    class Meta:
        model = Claim
        fields = ["id", "claim_number", "claim_type", "claim_type_display", "incident_date", "requested_amount",
                  "approved_amount", "status", "status_display", "vehicle_registration", "policy_number",
                  "customer_name", "assigned_adjuster_name", "current_risk_score", "current_risk_level", "is_flagged",
                  "submitted_at", "updated_at"]


class ClaimStaffSerializer(ClaimListStaffSerializer):
    customer = serializers.SerializerMethodField()
    vehicle = serializers.SerializerMethodField()
    policy = serializers.SerializerMethodField()
    timeline = serializers.SerializerMethodField()
    documents = serializers.SerializerMethodField()
    document_checklist = serializers.SerializerMethodField()
    fraud_assessments = serializers.SerializerMethodField()
    investigations = serializers.SerializerMethodField()
    appeals = AppealSerializer(many=True, read_only=True)
    customer_claim_history = serializers.SerializerMethodField()
    decided_by_name = serializers.CharField(source="decided_by.full_name", read_only=True, default=None)
    actions = serializers.SerializerMethodField()
    edit_deadline = serializers.DateTimeField(read_only=True)

    class Meta(ClaimListStaffSerializer.Meta):
        fields = ClaimListStaffSerializer.Meta.fields + [
            "incident_time", "incident_location", "description", "assessment_notes", "rejection_reason",
            "decided_by_name", "decided_at", "review_started_at", "edit_deadline", "appeal_count",
            "further_appeal_allowed", "closure_reason", "siu_cleared_at", "customer", "vehicle", "policy",
            "timeline", "documents", "document_checklist", "fraud_assessments", "investigations", "appeals",
            "customer_claim_history", "actions"]

    def get_customer(self, obj):
        u = obj.policy.customer.user
        p = obj.policy.customer
        return {"id": u.id, "full_name": u.full_name, "email": u.email, "phone": p.phone,
                "address": f"{p.address_line}, {p.city}, {p.state} {p.postal_code}", "member_since": u.date_joined}

    def get_vehicle(self, obj):
        return _vehicle(obj)

    def get_policy(self, obj):
        return _policy(obj)

    def get_timeline(self, obj):
        return [{"id": h.id, "from_status": h.from_status, "to_status": h.to_status,
                 "to_status_display": ClaimStatus(h.to_status).label, "reason": h.reason, "is_internal": h.is_internal,
                 "actor": h.actor.full_name if h.actor else "System", "created_at": h.created_at}
                for h in obj.history.select_related("actor").all()]

    def get_documents(self, obj):
        docs = obj.documents.select_related("uploaded_by", "verified_by", "replaced_by").prefetch_related(
            "reviews__actor")
        return ClaimDocumentSerializer(docs, many=True).data

    def get_document_checklist(self, obj):
        return document_checklist(obj)

    def get_fraud_assessments(self, obj):
        return FraudAssessmentSerializer(obj.fraud_assessments.prefetch_related("indicators")
                                         .select_related("requested_by"), many=True).data

    def get_investigations(self, obj):
        return InvestigationSerializer(obj.investigations.select_related("investigator", "opened_by", "assessment")
                                       .prefetch_related("notes__author"), many=True).data

    def get_customer_claim_history(self, obj):
        others = Claim.objects.filter(policy__customer=obj.policy.customer).exclude(pk=obj.pk).select_related(
            "policy__vehicle")[:10]
        return [{"id": c.id, "claim_number": c.claim_number, "claim_type": c.get_claim_type_display(),
                 "incident_date": c.incident_date, "status": c.status, "status_display": c.get_status_display(),
                 "requested_amount": c.requested_amount, "approved_amount": c.approved_amount,
                 "vehicle_registration": c.policy.vehicle.registration_number} for c in others]

    def get_actions(self, obj):
        return available_actions(obj, self.context["request"].user)


class ApproveSerializer(serializers.Serializer):
    approved_amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=1)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=5000)


class RejectSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=5000)
    allow_further_appeal = serializers.BooleanField(required=False, allow_null=True, default=None)


class NoteSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=5000)


class ReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=5000)


class AppealDecisionSerializer(serializers.Serializer):
    accept = serializers.BooleanField()
    note = serializers.CharField(max_length=5000)
    allow_further_appeal = serializers.BooleanField(required=False, allow_null=True, default=None)

