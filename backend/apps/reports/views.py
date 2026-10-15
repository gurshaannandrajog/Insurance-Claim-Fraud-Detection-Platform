from django.db.models import Count, Q
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role
from apps.accounts.permissions import IsAdmin, IsAnyRole
from apps.audit.models import AuditAction
from apps.audit.services import log_event
from apps.claims.models import AppealStatus, Claim, ClaimStatus, RiskLevel
from apps.claims.serializers import ClaimListCustomerSerializer, ClaimListStaffSerializer
from apps.claims.workflow import customer_visible_status
from apps.core.exceptions import BusinessRuleError
from apps.investigations.models import Investigation, InvestigationStatus
from apps.investigations.serializers import InvestigationSerializer
from apps.notifications.models import Notification
from apps.notifications.views import NotificationSerializer
from apps.policies.models import Policy, PolicyStatus
from apps.policies.services import expire_due_policies
from apps.vehicles.models import Vehicle

from .exports import EXPORTERS
from .queries import REPORTS, ROW_LIMIT_JSON, admin_dashboard

FILTER_KEYS = ["date_from", "date_to", "claim_type", "claim_status", "policy_status", "risk_level"]


def _filters(request):
    return {k: request.query_params.get(k, "") for k in FILTER_KEYS}


def _report(request):
    name = request.query_params.get("report", "claims")
    if name not in REPORTS:
        raise BusinessRuleError(f"Unknown report '{name}'.", code="unknown_report")
    return name, REPORTS[name](_filters(request))


class ReportView(APIView):
    """REQ-REP-001..009, REQ-REP-011 (administrators only)."""
    permission_classes = [IsAdmin]

    def get(self, request):
        name, rep = _report(request)
        return Response({"report": name, "title": rep["title"], "columns": rep["columns"],
                         "rows": rep["rows"][:ROW_LIMIT_JSON], "total_rows": len(rep["rows"]),
                         "truncated": len(rep["rows"]) > ROW_LIMIT_JSON, "summary": rep["summary"],
                         "filters": _filters(request)})


class ReportExportView(APIView):
    """REQ-REP-010 — CSV, Excel and PDF built from exactly the same filtered data."""
    permission_classes = [IsAdmin]

    def get(self, request):
        fmt = request.query_params.get("format", "csv")
        if fmt not in EXPORTERS:
            raise BusinessRuleError("Format must be csv, xlsx or pdf.", code="unknown_format")
        name, rep = _report(request)
        content, mime, ext = EXPORTERS[fmt](rep, _filters(request))
        log_event(AuditAction.REPORT_EXPORTED, None, entity_type="report", request=request,
                  metadata={"report": name, "format": fmt, "rows": len(rep["rows"]), "filters": _filters(request)})
        resp = HttpResponse(content, content_type=mime)
        resp["Content-Disposition"] = f'attachment; filename="{name}-report-{timezone.localtime():%Y%m%d-%H%M}.{ext}"'
        return resp


class DashboardView(APIView):
    """One endpoint, role-specific content — every figure is a live database query."""
    permission_classes = [IsAnyRole]

    def get(self, request):
        expire_due_policies()
        user = request.user
        builder = {Role.CUSTOMER: self.customer, Role.ADJUSTER: self.adjuster, Role.SIU: self.siu,
                   Role.ADMIN: self.admin}[user.role]
        return Response(builder(request))

    def customer(self, request):
        user = request.user
        claims = Claim.objects.filter(policy__customer__user=user).select_related("policy__vehicle")
        status_counts = {}
        for s in claims.values_list("status", flat=True):
            key = customer_visible_status(s)
            status_counts[key] = status_counts.get(key, 0) + 1
        policies = Policy.objects.filter(customer__user=user)
        return {
            "policies": {"total": policies.count(),
                         "active": policies.filter(status__in=PolicyStatus.claimable()).count(),
                         "by_status": dict(policies.values_list("status").annotate(n=Count("id")))},
            "vehicles": {"total": Vehicle.objects.filter(customer__user=user).count(),
                         "insured": Vehicle.objects.filter(customer__user=user,
                                                           policies__status__in=PolicyStatus.live()).distinct().count()},
            "claims": {"total": claims.count(), "by_status": status_counts,
                       "open": claims.exclude(status__in=ClaimStatus.terminal()).count()},
            "recent_claims": ClaimListCustomerSerializer(claims[:5], many=True).data,
            "notifications": NotificationSerializer(Notification.objects.filter(recipient=user)[:5], many=True).data,
            "unread_notifications": Notification.objects.filter(recipient=user, is_read=False).count(),
        }

    def adjuster(self, request):
        user = request.user
        claims = Claim.objects.select_related("policy__vehicle", "policy__customer__user", "assigned_adjuster")
        ser = lambda qs: ClaimListStaffSerializer(qs, many=True).data  # noqa: E731
        awaiting = claims.filter(Q(status=ClaimStatus.SUBMITTED) | Q(status=ClaimStatus.UNDER_REVIEW,
                                                                       assigned_adjuster__isnull=True))
        return {
            "counts": {
                "awaiting_review": awaiting.count(),
                "my_under_review": claims.filter(status=ClaimStatus.UNDER_REVIEW, assigned_adjuster=user).count(),
                "documents_pending": claims.filter(status=ClaimStatus.DOCUMENTS_PENDING).count(),
                "fraud_review": claims.filter(status=ClaimStatus.FRAUD_REVIEW).count(),
                "pending_appeals": claims.filter(appeals__status=AppealStatus.PENDING).distinct().count(),
                "high_risk_open": claims.filter(current_risk_level=RiskLevel.HIGH,
                                                status__in=ClaimStatus.in_processing()).count(),
            },
            "awaiting_review": ser(awaiting.order_by("submitted_at")[:8]),
            "my_queue": ser(claims.filter(assigned_adjuster=user, status__in=[
                ClaimStatus.UNDER_REVIEW, ClaimStatus.DOCUMENTS_PENDING]).order_by("submitted_at")[:8]),
            "documents_pending": ser(claims.filter(status=ClaimStatus.DOCUMENTS_PENDING)[:8]),
            "fraud_review": ser(claims.filter(status=ClaimStatus.FRAUD_REVIEW)[:8]),
            "pending_appeals": ser(claims.filter(appeals__status=AppealStatus.PENDING).distinct()[:8]),
            "recently_approved": ser(claims.filter(status=ClaimStatus.APPROVED).order_by("-decided_at")[:5]),
            "recently_rejected": ser(claims.filter(status__in=[ClaimStatus.REJECTED, ClaimStatus.PERMANENTLY_REJECTED])
                                     .order_by("-decided_at")[:5]),
        }

    def siu(self, request):
        inv = Investigation.objects.select_related("claim__policy__customer__user", "investigator",
                                                   "assessment").prefetch_related("assessment__indicators", "notes")
        flagged = Claim.objects.filter(investigations__isnull=False).distinct()
        return {
            "counts": {
                "open": inv.filter(status=InvestigationStatus.OPEN).count(),
                "in_progress": inv.filter(status=InvestigationStatus.IN_PROGRESS).count(),
                "mine": inv.filter(investigator=request.user).exclude(status=InvestigationStatus.COMPLETED).count(),
                "completed": inv.filter(status=InvestigationStatus.COMPLETED).count(),
                "fraud_review_claims": Claim.objects.filter(status=ClaimStatus.FRAUD_REVIEW).count(),
                "high_risk_claims": Claim.objects.filter(current_risk_level=RiskLevel.HIGH).count(),
            },
            "queue": InvestigationSerializer(inv.exclude(status=InvestigationStatus.COMPLETED)
                                             .order_by("created_at")[:20], many=True).data,
            "recently_completed": InvestigationSerializer(inv.filter(status=InvestigationStatus.COMPLETED)
                                                          .order_by("-completed_at")[:5], many=True).data,
            "risk_distribution": [{"key": k, "label": label, "value": flagged.filter(current_risk_level=k).count()}
                                  for k, label in RiskLevel.choices],
            "recommendations": list(inv.filter(status=InvestigationStatus.COMPLETED).values("recommendation")
                                    .annotate(value=Count("id"))),
        }

    def admin(self, request):
        return admin_dashboard()
