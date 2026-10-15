from django.http import JsonResponse
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.accounts.urls import admin_urlpatterns, auth_urlpatterns, profile_urlpatterns
from apps.audit.views import AuditLogListView
from apps.claims.views import AppealViewSet, ClaimViewSet
from apps.documents.views import DocumentViewSet
from apps.fraud.views import FraudAssessmentViewSet, FraudServiceHealthView
from apps.investigations.views import InvestigationViewSet
from apps.notifications.views import NotificationViewSet
from apps.policies.views import PolicyPlanViewSet, PolicyRequestViewSet, PolicyViewSet
from apps.reports.views import DashboardView, ReportExportView, ReportView
from apps.vehicles.views import VehicleViewSet

router = DefaultRouter(trailing_slash=True)
router.include_root_view = False
router.register("vehicles", VehicleViewSet, basename="vehicle")
router.register("policy-plans", PolicyPlanViewSet, basename="policy-plan")
router.register("policy-requests", PolicyRequestViewSet, basename="policy-request")
router.register("policies", PolicyViewSet, basename="policy")
router.register("claims", ClaimViewSet, basename="claim")
router.register("appeals", AppealViewSet, basename="appeal")
router.register("documents", DocumentViewSet, basename="document")
router.register("fraud/assessments", FraudAssessmentViewSet, basename="fraud-assessment")
router.register("investigations", InvestigationViewSet, basename="investigation")
router.register("notifications", NotificationViewSet, basename="notification")


def health(request):
    return JsonResponse({"status": "ok"})


def not_found(request, exception=None):
    return JsonResponse({"error": {"code": "not_found", "message": "Not found."}}, status=404)


def server_error(request):
    return JsonResponse({"error": {"code": "server_error", "message": "Something went wrong."}}, status=500)


handler404 = not_found
handler500 = server_error

urlpatterns = [
    path("api/health/", health),
    path("api/auth/", include(auth_urlpatterns)),
    path("api/profile/", include(profile_urlpatterns)),
    path("api/admin/", include(admin_urlpatterns)),
    path("api/audit-logs/", AuditLogListView.as_view()),
    path("api/dashboard/", DashboardView.as_view()),
    path("api/reports/", ReportView.as_view()),
    path("api/reports/export/", ReportExportView.as_view()),
    path("api/fraud/health/", FraudServiceHealthView.as_view()),
    path("api/", include(router.urls)),
]
