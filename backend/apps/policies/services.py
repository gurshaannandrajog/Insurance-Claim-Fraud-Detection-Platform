"""Policy business rules (SRS §4.3, §4.4, REQ-BR-001..008, 021)."""
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditAction
from apps.audit.services import log_event
from apps.core.exceptions import BusinessRuleError, ConflictError
from apps.core.numbering import assign_number, temporary_number
from apps.notifications.models import NotificationType
from apps.notifications.services import notify, notify_role
from apps.vehicles.models import Vehicle

from .models import Policy, PolicyRequest, PolicyRequestStatus, PolicyStatus

TWO = Decimal("0.01")


def calculate_premium(idv, rate_percent, term_months):
    return (Decimal(idv) * Decimal(rate_percent) / 100 * Decimal(term_months) / 12).quantize(TWO, ROUND_HALF_UP)


def vehicle_has_live_policy(vehicle):
    return vehicle.policies.filter(status__in=PolicyStatus.live()).exists()


# ----------------------------------------------------------------------------- requests (customer)
@transaction.atomic
def create_policy_request(customer, *, vehicle, plan, requested_idv, notes="", request=None):
    vehicle = Vehicle.objects.select_for_update().get(pk=vehicle.pk)
    if vehicle.customer_id != customer.pk:
        raise BusinessRuleError("You can only request policies for your own vehicles.", code="not_owner",
                                status_code=404)
    if not plan.is_active:
        raise BusinessRuleError("This plan is no longer offered.", code="plan_inactive")
    if not (plan.min_idv <= requested_idv <= plan.max_idv):
        raise BusinessRuleError(f"IDV must be between {plan.min_idv:,.0f} and {plan.max_idv:,.0f} for this plan.",
                                code="idv_out_of_range", fields={"requested_idv": ["Outside plan limits."]})
    if vehicle_has_live_policy(vehicle):  # REQ-VEH-008 / REQ-BR-003
        raise ConflictError("This vehicle already has a policy that is Active, Partially Claimed or Claimed. "
                            "A new policy can be requested once it has Expired or been Cancelled.",
                            code="vehicle_has_live_policy")
    if vehicle.policy_requests.filter(status=PolicyRequestStatus.PENDING).exists():
        raise ConflictError("A policy request for this vehicle is already pending review.", code="request_pending")
    pr = PolicyRequest.objects.create(customer=customer, vehicle=vehicle, plan=plan, requested_idv=requested_idv,
                                      notes=notes)
    log_event(AuditAction.POLICY_REQUESTED, pr, request=request,
              metadata={"vehicle": vehicle.registration_number, "plan": plan.code, "idv": str(requested_idv)})
    notify_role("ADMIN", NotificationType.POLICY_REQUEST, "New policy request",
                f"{customer.user.full_name} requested a {plan.name} policy for {vehicle.registration_number}.",
                link="/admin/policy-requests")
    return pr


@transaction.atomic
def withdraw_policy_request(pr, request=None):
    pr = PolicyRequest.objects.select_for_update().get(pk=pr.pk)
    if pr.status != PolicyRequestStatus.PENDING:
        raise ConflictError("Only pending requests can be withdrawn.", code="request_not_pending")
    pr.status = PolicyRequestStatus.WITHDRAWN
    pr.save(update_fields=["status", "updated_at"])
    log_event(AuditAction.POLICY_REQUEST_WITHDRAWN, pr, request=request)
    return pr


# ----------------------------------------------------------------------------- review (administrator)


@transaction.atomic
def approve_policy_request(admin, pr, *, start_date=None, idv=None, decision_note="", request=None):
    """REQ-POL-002/003/005: creates the policy (Active) with a unique number, linked to one customer + vehicle."""
    pr = PolicyRequest.objects.select_for_update().select_related("plan", "customer__user").get(pk=pr.pk)
    if pr.status != PolicyRequestStatus.PENDING:
        raise ConflictError("This request has already been reviewed.", code="request_not_pending")
    vehicle = Vehicle.objects.select_for_update().get(pk=pr.vehicle_id)   # serialises concurrent approvals
    if vehicle_has_live_policy(vehicle):                                 # REQ-VEH-006 / REQ-BR-002
        raise ConflictError("This vehicle already has a live policy.", code="vehicle_has_live_policy")
    plan = pr.plan
    idv = Decimal(idv) if idv is not None else pr.requested_idv
    if not (plan.min_idv <= idv <= plan.max_idv):
        raise BusinessRuleError("IDV is outside the plan limits.", code="idv_out_of_range")
    start = start_date or timezone.localdate()
    if start < timezone.localdate():
        raise BusinessRuleError("Start date cannot be in the past.", code="invalid_start_date")
    policy = Policy.objects.create(
        policy_number=temporary_number(),
        customer=pr.customer, vehicle=vehicle, request=pr, plan=plan, plan_name=plan.name,
        premium_rate_percent=plan.premium_rate_percent, start_date=start,
        end_date=start + relativedelta(months=plan.term_months) - relativedelta(days=1),
        idv=idv, premium_amount=calculate_premium(idv, plan.premium_rate_percent, plan.term_months),
        status=PolicyStatus.ACTIVE, created_by=admin,
    )
    assign_number(policy, "POL", "policy_number")
    pr.status, pr.reviewed_by, pr.reviewed_at, pr.decision_note = (PolicyRequestStatus.APPROVED, admin,
                                                                   timezone.now(), decision_note)
    pr.save()
    log_event(AuditAction.POLICY_CREATED, policy, actor=admin, request=request,
              metadata={"policy_number": policy.policy_number, "vehicle": vehicle.registration_number,
                        "idv": str(idv), "request_id": pr.pk})
    notify(pr.customer.user, NotificationType.POLICY, "Your policy is active",
           f"Policy {policy.policy_number} for {vehicle.registration_number} is active from {policy.start_date} "
           f"to {policy.end_date}. IDV ₹{policy.idv:,.2f}, premium ₹{policy.premium_amount:,.2f}.",
           link="/policies")
    return policy


@transaction.atomic
def reject_policy_request(admin, pr, reason, request=None):
    pr = PolicyRequest.objects.select_for_update().select_related("customer__user", "vehicle").get(pk=pr.pk)
    if pr.status != PolicyRequestStatus.PENDING:
        raise ConflictError("This request has already been reviewed.", code="request_not_pending")
    if not reason or not reason.strip():
        raise BusinessRuleError("A reason is required.", code="reason_required", fields={"reason": ["Required."]})
    pr.status, pr.reviewed_by, pr.reviewed_at, pr.decision_note = (PolicyRequestStatus.REJECTED, admin,
                                                                   timezone.now(), reason.strip())
    pr.save()
    log_event(AuditAction.POLICY_REQUEST_REJECTED, pr, actor=admin, request=request, metadata={"reason": reason})
    notify(pr.customer.user, NotificationType.POLICY_REQUEST, "Policy request not approved",
           f"Your policy request for {pr.vehicle.registration_number} was not approved. Reason: {reason}",
           link="/policies")
    return pr


# ----------------------------------------------------------------------------- status management
def _set_status(policy, new_status, actor=None, request=None, reason=""):
    old = policy.status
    if old == new_status:
        return
    policy.status = new_status
    log_event(AuditAction.POLICY_STATUS_CHANGED, policy, actor=actor, request=request,
              metadata={"from": old, "to": new_status, "reason": reason})


def recalculate_status(policy):
    """REQ-POL-008/009/010 — derived from cumulative approved amount vs IDV (never for Expired/Cancelled)."""
    if policy.status in (PolicyStatus.EXPIRED, PolicyStatus.CANCELLED):
        return policy.status
    if policy.cumulative_approved_amount >= policy.idv:
        return PolicyStatus.CLAIMED
    if policy.cumulative_approved_amount > 0:
        return PolicyStatus.PARTIALLY_CLAIMED
    return PolicyStatus.ACTIVE


def apply_approved_claim_amount(policy, amount, actor=None, request=None):
    """Must be called inside the claim-approval transaction (REQ-CLM-010). Locks the policy row."""
    policy = Policy.objects.select_for_update().get(pk=policy.pk)
    amount = Decimal(amount)
    if amount > policy.remaining_idv:
        raise BusinessRuleError(f"Approved amount exceeds the remaining insured value (₹{policy.remaining_idv:,.2f}).",
                                code="exceeds_remaining_idv", fields={"approved_amount": ["Exceeds remaining IDV."]})
    policy.cumulative_approved_amount += amount
    _set_status(policy, recalculate_status(policy), actor, request, reason="claim approved")
    policy.save(update_fields=["cumulative_approved_amount", "status", "updated_at"])
    return policy


@transaction.atomic
def cancel_policy(admin, policy, reason, request=None):
    """REQ-POL-012 / REQ-BR-008."""
    from apps.claims.models import ClaimStatus

    policy = Policy.objects.select_for_update().select_related("customer__user").get(pk=policy.pk)
    if policy.status not in PolicyStatus.live():
        raise ConflictError(f"A {policy.get_status_display()} policy cannot be cancelled.", code="invalid_policy_status")
    if not reason or not reason.strip():
        raise BusinessRuleError("A cancellation reason is required.", code="reason_required",
                                fields={"reason": ["Required."]})
    open_claims = policy.claims.exclude(status__in=ClaimStatus.terminal()).count()
    if open_claims:
        raise ConflictError(f"The policy has {open_claims} claim(s) still being processed. "
                            "Resolve them before cancelling.", code="open_claims_exist")
    _set_status(policy, PolicyStatus.CANCELLED, admin, request, reason)
    policy.cancelled_by, policy.cancelled_at, policy.cancellation_reason = admin, timezone.now(), reason.strip()
    policy.save()
    log_event(AuditAction.POLICY_CANCELLED, policy, actor=admin, request=request, metadata={"reason": reason})
    notify(policy.customer.user, NotificationType.POLICY, "Policy cancelled",
           f"Policy {policy.policy_number} has been cancelled. Reason: {reason}", link="/policies")
    return policy


def expire_due_policies(today=None):
    """REQ-POL-011 / REQ-BR-007. Idempotent; run by `manage.py run_maintenance` and lazily before claim checks."""
    today = today or timezone.localdate()
    due = list(Policy.objects.filter(status__in=PolicyStatus.live(), end_date__lt=today).select_related(
        "customer__user"))
    for policy in due:
        with transaction.atomic():
            p = Policy.objects.select_for_update().get(pk=policy.pk)
            if p.status not in PolicyStatus.live() or p.end_date >= today:
                continue
            _set_status(p, PolicyStatus.EXPIRED, reason="validity period ended")
            p.save(update_fields=["status", "updated_at"])
            log_event(AuditAction.POLICY_EXPIRED, p, metadata={"end_date": str(p.end_date)})
            notify(policy.customer.user, NotificationType.POLICY, "Policy expired",
                   f"Policy {p.policy_number} expired on {p.end_date}. You can request a new policy for this vehicle.",
                   link="/policies")
    return len(due)


def is_claimable(policy, incident_date: date):
    if policy.status not in PolicyStatus.claimable():
        return False, f"Claims cannot be filed against a {policy.get_status_display()} policy."
    if not (policy.start_date <= incident_date <= policy.end_date):
        return False, "The incident date is outside the policy period."
    return True, ""
