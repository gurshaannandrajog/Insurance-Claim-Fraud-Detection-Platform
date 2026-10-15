import { AlertTriangle, ArrowLeft, CheckCircle2, FileSearch, Play, RefreshCw, Siren, XCircle } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, api, errorMessage } from "../../api/client";
import type { Investigation, StaffClaim } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Checklist, ClaimStatusBadge, DocumentList, RiskBadge, RiskMeter, StatusRail, Timeline } from "../../components/claim-parts";
import { useToast } from "../../components/Toast";
import { Badge, Banner, ErrorState, Field, Input, Modal, Panel, Select, Spinner, Textarea } from "../../components/ui";
import { date, dateTime, money } from "../../lib/format";
import { INVESTIGATION_TONE, RECOMMENDATIONS } from "../../lib/labels";
import { useApi } from "../../lib/useApi";

type Dialog = null | "approve" | "reject" | "docs" | "escalate" | "appeal";

function Section({ title, children, actions }: { title: string; children: ReactNode; actions?: ReactNode }) {
  return <Panel title={title} actions={actions}>{children}</Panel>;
}

function InvestigationPanel({ inv, canWork, onChanged }: { inv: Investigation; canWork: boolean; onChanged: () => void }) {
  const toast = useToast();
  const [findings, setFindings] = useState(inv.findings);
  const [evidence, setEvidence] = useState(inv.evidence_notes);
  const [note, setNote] = useState("");
  const [rec, setRec] = useState(inv.recommendation);
  const [busy, setBusy] = useState(false);
  const editable = canWork && inv.status !== "COMPLETED";

  const call = async (path: string, body: object, msg: string) => {
    setBusy(true);
    try { await api.post(`/investigations/${inv.id}/${path}/`, body); toast(msg); setNote(""); onChanged(); }
    catch (e) { toast(errorMessage(e), "error"); } finally { setBusy(false); }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <Badge tone={INVESTIGATION_TONE[inv.status]}>{inv.status_display}</Badge>
        <span className="text-ink-500">{inv.trigger_display}, opened {dateTime(inv.created_at)}</span>
        {inv.investigator_name && <span className="text-ink-500">Investigator: {inv.investigator_name}</span>}
      </div>
      <p className="rounded bg-paper px-3 py-2 text-sm text-ink-700">{inv.trigger_reason}</p>
      {editable && inv.status === "OPEN" && (
        <button className="btn-primary" disabled={busy} onClick={() => call("start", {}, "Investigation assigned to you")}><Play className="h-4 w-4" />Take this investigation</button>
      )}
      {editable && inv.status === "IN_PROGRESS" ? (
        <div className="space-y-4">
          <Field label="Findings" required hint="Permanent once the investigation is completed."><Textarea rows={4} value={findings} onChange={(e) => setFindings(e.target.value)} /></Field>
          <Field label="Evidence and comments"><Textarea rows={3} value={evidence} onChange={(e) => setEvidence(e.target.value)} /></Field>
          <Field label="Add a case note"><Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Spoke to the workshop manager" /></Field>
          <Field label="Recommendation to the claim adjuster" required>
            <Select value={rec} onChange={(e) => setRec(e.target.value)}><option value="">Choose…</option>{RECOMMENDATIONS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select>
          </Field>
          <div className="flex flex-wrap gap-2">
            <button className="btn-secondary" disabled={busy} onClick={() => call("progress", { findings, evidence_notes: evidence, note }, "Progress saved")}>Save progress</button>
            <button className="btn-primary" disabled={busy || !findings.trim() || !rec}
              onClick={() => call("complete", { findings, evidence_notes: evidence, recommendation: rec }, "Findings recorded — the claim is back with the adjuster")}>
              Complete investigation</button>
          </div>
        </div>
      ) : (inv.findings || inv.recommendation) && (
        <dl className="dl">
          {inv.recommendation && <><dt>Recommendation</dt><dd>{inv.recommendation_display}</dd></>}
          {inv.findings && <><dt>Findings</dt><dd className="whitespace-pre-wrap font-normal">{inv.findings}</dd></>}
          {inv.evidence_notes && <><dt>Evidence</dt><dd className="whitespace-pre-wrap font-normal">{inv.evidence_notes}</dd></>}
          {inv.completed_at && <><dt>Completed</dt><dd>{dateTime(inv.completed_at)}</dd></>}
        </dl>
      )}
      {inv.notes.length > 0 && (
        <div>
          <p className="mb-2 text-sm font-medium">Case notes</p>
          <ul className="space-y-2">{inv.notes.map((n) => <li key={n.id} className="text-sm"><span className="text-ink-500">{dateTime(n.created_at)}, {n.author_name}:</span> {n.note}</li>)}</ul>
        </div>
      )}
    </div>
  );
}

export default function StaffClaimDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const toast = useToast();
  const { data: c, setData, loading, error, reload } = useApi<StaffClaim>(`/claims/${id}/`);
  const [dialog, setDialog] = useState<Dialog>(null);
  const [form, setForm] = useState({ amount: "", notes: "", reason: "", allow: "", note: "", accept: "" });
  const [formError, setFormError] = useState("");
  const [busy, setBusy] = useState(false);

  if (loading && !c) return <Spinner />;
  if (error || !c) return <ErrorState message={error ?? "Claim not found."} onRetry={reload} />;
  const can = (a: string) => c.actions.includes(a);
  const latest = c.fraud_assessments.find((a) => a.status === "COMPLETED");
  const lastRun = c.fraud_assessments[0];
  const pendingAppeal = c.appeals.find((a) => a.status === "PENDING");
  const backTo = user?.role === "SIU" ? "/siu" : user?.role === "ADMIN" ? "/staff/claims" : "/staff";

  const open = (d: Dialog) => { setForm({ amount: c.requested_amount, notes: "", reason: "", allow: "", note: "", accept: "" }); setFormError(""); setDialog(d); };

  const post = async (path: string, body: object, msg: string) => {
    setBusy(true); setFormError("");
    try {
      const r = await api.post(path, body);
      if (path.startsWith(`/claims/${c.id}/`) && !path.endsWith("rerun-fraud/")) setData(r.data as StaffClaim); else reload();
      toast(msg); setDialog(null);
    } catch (e) {
      const extra = e instanceof ApiError && Array.isArray(e.extra.missing) ? ` Missing: ${(e.extra.missing as string[]).join(", ")}.` : "";
      if (dialog) setFormError(errorMessage(e) + extra); else toast(errorMessage(e) + extra, "error");
    } finally { setBusy(false); }
  };

  const needsAppealDecision = c.appeal_count >= 1;

  return (
    <div className="space-y-6">
      <Link to={backTo} className="inline-flex items-center gap-1.5 text-sm text-ink-500 hover:text-ink"><ArrowLeft className="h-4 w-4" />Back</Link>

      <section className="panel p-5 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-3">
              <h1>{c.claim_number}</h1><ClaimStatusBadge status={c.status} label={c.status_display} />
              {c.is_flagged && <Badge tone="bad">Flagged</Badge>}
            </div>
            <p className="mt-1 text-sm text-ink-500">
              {c.claim_type_display} on {c.vehicle.registration_number} for {c.customer.full_name}. Submitted {dateTime(c.submitted_at)}.
              {c.assigned_adjuster_name ? ` Assigned to ${c.assigned_adjuster_name}.` : " Not yet assigned."}
            </p>
          </div>
          <div className="flex gap-6 text-right">
            <div><div className="text-sm text-ink-500">Requested</div><div className="text-xl font-semibold">{money(c.requested_amount)}</div></div>
            <div><div className="text-sm text-ink-500">Approved</div><div className="text-xl font-semibold text-ok">{money(c.approved_amount)}</div></div>
          </div>
        </div>
        <div className="mt-6"><StatusRail status={c.status} label={c.status_display} /></div>

        {c.actions.length > 0 && user?.role === "ADJUSTER" && (
          <div className="mt-5 flex flex-wrap gap-2 border-t border-line pt-5">
            {can("start_review") && <button className="btn-primary" disabled={busy} onClick={() => post(`/claims/${c.id}/start-review/`, {}, "Review started — the customer can no longer edit")}><Play className="h-4 w-4" />Start review</button>}
            {can("resume_review") && <button className="btn-primary" disabled={busy} onClick={() => post(`/claims/${c.id}/start-review/`, {}, "Review resumed")}><Play className="h-4 w-4" />Resume review</button>}
            {can("approve") && <button className="btn-primary" onClick={() => open("approve")}><CheckCircle2 className="h-4 w-4" />Approve</button>}
            {can("reject") && <button className="btn-danger" onClick={() => open("reject")}><XCircle className="h-4 w-4" />Reject</button>}
            {can("request_documents") && <button className="btn-secondary" onClick={() => open("docs")}>Request documents</button>}
            {can("escalate") && <button className="btn-secondary" onClick={() => open("escalate")}><Siren className="h-4 w-4" />Escalate to SIU</button>}
            {can("decide_appeal") && <button className="btn-primary" onClick={() => open("appeal")}>Decide appeal</button>}
            {can("rerun_fraud") && <button className="btn-ghost" disabled={busy} onClick={() => post(`/claims/${c.id}/rerun-fraud/`, {}, "Fraud assessment re-run")}><RefreshCw className="h-4 w-4" />Re-run fraud check</button>}
          </div>
        )}
        {c.status === "FRAUD_REVIEW" && user?.role === "ADJUSTER" && (
          <div className="mt-4"><Banner tone="warn">This claim is with the Special Investigation Unit. It returns to you for a decision when the investigation is completed.</Banner></div>
        )}
        {user?.role === "ADMIN" && <div className="mt-4"><Banner tone="info">Read-only oversight view. Administrators do not approve or reject claims.</Banner></div>}
      </section>

      <div className="grid gap-6 xl:grid-cols-[1.55fr_1fr]">
        <div className="space-y-6">
          <Section title="Claim information">
            <dl className="dl">
              <dt>Incident</dt><dd>{date(c.incident_date)} at {c.incident_time.slice(0, 5)}</dd>
              <dt>Location</dt><dd>{c.incident_location}</dd>
              <dt>Review started</dt><dd>{dateTime(c.review_started_at)}</dd>
              {c.decided_by_name && <><dt>Decision by</dt><dd>{c.decided_by_name}, {dateTime(c.decided_at)}</dd></>}
              {c.assessment_notes && <><dt>Assessment</dt><dd className="font-normal">{c.assessment_notes}</dd></>}
              {c.rejection_reason && <><dt>Rejection reason</dt><dd className="font-normal text-bad">{c.rejection_reason}</dd></>}
            </dl>
            <p className="mt-4 whitespace-pre-wrap rounded bg-paper px-4 py-3 text-sm text-ink-700">{c.description}</p>
          </Section>

          <Section title="Documents">
            <div className="mb-4"><Checklist items={c.document_checklist} /></div>
            <DocumentList claimId={c.id} documents={c.documents} staff canReview={can("review_documents")} canUpload={can("upload_document")} canReplaceAny onChanged={reload} />
          </Section>

          {(c.investigations.length > 0) && (
            <Section title="SIU investigation">
              <div className="space-y-6 divide-y divide-line">
                {c.investigations.map((inv) => (
                  <div key={inv.id} className="pt-4 first:pt-0">
                    <InvestigationPanel inv={inv} canWork={user?.role === "SIU" && can("investigate")} onChanged={reload} />
                  </div>
                ))}
              </div>
            </Section>
          )}

          {c.appeals.length > 0 && (
            <Section title="Appeals">
              <ul className="space-y-3">{c.appeals.map((a) => (
                <li key={a.id} className="rounded-md border border-line p-4 text-sm">
                  <div className="flex items-center justify-between"><span className="font-medium">Appeal {a.sequence}, {dateTime(a.created_at)}</span>
                    <Badge tone={a.status === "ACCEPTED" ? "ok" : a.status === "DECLINED" ? "bad" : "warn"}>{a.status_display}</Badge></div>
                  <p className="mt-2">{a.reason}</p>
                  {a.decision_note && <p className="mt-2 text-ink-500">{a.decided_by_name}: {a.decision_note}{a.further_appeal_allowed === false && " (no further appeal)"}</p>}
                </li>))}
              </ul>
            </Section>
          )}

          <Section title="Claim timeline"><Timeline entries={c.timeline} staff /></Section>
        </div>

        <div className="space-y-6">
          <Section title="Fraud assessment">
            {latest && latest.risk_score !== null ? (
              <div className="space-y-4">
                <RiskMeter score={latest.risk_score} level={latest.risk_level} />
                <div>
                  <p className="mb-2 text-sm font-medium">Contributing factors</p>
                  {latest.indicators.length === 0 ? <p className="text-sm text-ink-500">No risk factors found.</p> : (
                    <ul className="space-y-2">{latest.indicators.map((i) => (
                      <li key={i.code} className="flex items-start gap-3 text-sm">
                        <span className="w-9 shrink-0 rounded bg-paper py-0.5 text-center text-xs font-semibold">+{i.weight}</span>
                        <span><span className="block">{i.description}</span><span className="text-xs text-ink-500">{i.category}</span></span>
                      </li>))}
                    </ul>
                  )}
                </div>
                <p className="text-xs text-ink-500">Engine {latest.engine}, {dateTime(latest.created_at)}, {c.fraud_assessments.length} run(s). A risk score flags a claim for review; it never rejects it.</p>
              </div>
            ) : <p className="text-sm text-ink-500">No completed assessment yet.</p>}
            {lastRun?.status === "FAILED" && (
              <div className="mt-4 flex gap-2 rounded bg-warn-light px-3 py-2 text-sm text-warn">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />The last assessment failed ({lastRun.error_message}). Re-run it once the fraud service is available.
              </div>
            )}
          </Section>

          <Section title="Customer">
            <dl className="dl">
              <dt>Name</dt><dd>{c.customer.full_name}</dd><dt>Email</dt><dd className="truncate">{c.customer.email}</dd>
              <dt>Phone</dt><dd>{c.customer.phone}</dd><dt>Address</dt><dd className="font-normal">{c.customer.address}</dd>
              <dt>Customer since</dt><dd>{date(c.customer.member_since)}</dd>
            </dl>
          </Section>
          <Section title="Vehicle and policy">
            <dl className="dl">
              <dt>Vehicle</dt><dd>{c.vehicle.registration_number}, {c.vehicle.make} {c.vehicle.model} ({c.vehicle.manufacturing_year})</dd>
              <dt>Registered owner</dt><dd>{c.vehicle.owner_name}</dd>
              <dt>Policy</dt><dd>{c.policy.policy_number} <Badge tone={c.policy.status === "ACTIVE" ? "ok" : "cover"}>{c.policy.status_display}</Badge></dd>
              <dt>Plan</dt><dd>{c.policy.plan_name}</dd>
              <dt>Period</dt><dd>{date(c.policy.start_date)} to {date(c.policy.end_date)}</dd>
              <dt>IDV</dt><dd>{money(c.policy.idv)}</dd>
              <dt>Already paid</dt><dd>{money(c.policy.cumulative_approved_amount)}</dd>
              <dt>Remaining cover</dt><dd>{money(c.policy.remaining_idv)}</dd>
            </dl>
          </Section>
          <Section title="Customer's other claims">
            {c.customer_claim_history.length === 0 ? <p className="text-sm text-ink-500">No other claims.</p> : (
              <ul className="space-y-2 text-sm">{c.customer_claim_history.map((h) => (
                <li key={h.id} className="flex items-center justify-between gap-2">
                  <span><Link to={`/staff/claims/${h.id}`} className="font-medium hover:underline">{h.claim_number}</Link><span className="block text-xs text-ink-500">{h.claim_type}, {date(h.incident_date)}, {money(h.requested_amount)}</span></span>
                  <ClaimStatusBadge status={h.status} label={h.status_display} />
                </li>))}
              </ul>
            )}
          </Section>
        </div>
      </div>

      {/* ---------------------------------------------------------------- decision dialogs */}
      <Modal open={dialog === "approve"} title="Approve claim" onClose={() => setDialog(null)} footer={<>
        <button className="btn-secondary" onClick={() => setDialog(null)}>Cancel</button>
        <button className="btn-primary" disabled={busy} onClick={() => post(`/claims/${c.id}/approve/`, { approved_amount: form.amount, notes: form.notes }, "Claim approved")}>Approve {money(form.amount)}</button></>}>
        {formError && <Banner tone="bad">{formError}</Banner>}
        <p className="text-sm text-ink-700">Customer requested {money(c.requested_amount)}. Remaining cover on the policy is {money(c.policy.remaining_idv)}.</p>
        {latest && <p className="text-sm">Current risk: <RiskBadge level={latest.risk_level} score={latest.risk_score} /></p>}
        <Field label="Approved amount (₹)" required hint="Based on documents, repair estimates and your assessment. The customer's requested amount is kept separately."><Input type="number" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} /></Field>
        <Field label="Assessment notes"><Textarea value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} placeholder="e.g. Approved per Sai Motors estimate; depreciation applied on plastic parts." /></Field>
      </Modal>

      <Modal open={dialog === "reject"} title="Reject claim" onClose={() => setDialog(null)} footer={<>
        <button className="btn-secondary" onClick={() => setDialog(null)}>Cancel</button>
        <button className="btn-danger" disabled={busy || !form.reason.trim() || (needsAppealDecision && !form.allow)}
          onClick={() => post(`/claims/${c.id}/reject/`, { reason: form.reason, allow_further_appeal: needsAppealDecision ? form.allow === "yes" : null }, "Claim rejected — the customer has been notified")}>Reject claim</button></>}>
        {formError && <Banner tone="bad">{formError}</Banner>}
        <Field label="Reason shared with the customer" required><Textarea value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} /></Field>
        {needsAppealDecision ? (
          <Field label="May the customer appeal again?" required hint="This claim has already been appealed. If you choose no, it becomes permanently rejected.">
            <Select value={form.allow} onChange={(e) => setForm({ ...form, allow: e.target.value })}><option value="">Choose…</option><option value="yes">Yes, allow one more appeal</option><option value="no">No, reject permanently</option></Select>
          </Field>
        ) : <p className="text-sm text-ink-500">The customer can appeal this first rejection.</p>}
      </Modal>

      <Modal open={dialog === "docs"} title="Request documents" onClose={() => setDialog(null)} footer={<>
        <button className="btn-secondary" onClick={() => setDialog(null)}>Cancel</button>
        <button className="btn-primary" disabled={busy || !form.note.trim()} onClick={() => post(`/claims/${c.id}/request-documents/`, { note: form.note }, "Customer asked for documents")}>Send request</button></>}>
        {formError && <Banner tone="bad">{formError}</Banner>}
        <Field label="What's missing?" required hint="Sent to the customer by email and in the app; the claim moves to Documents Pending."><Textarea value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} /></Field>
      </Modal>

      <Modal open={dialog === "escalate"} title="Escalate to the SIU" onClose={() => setDialog(null)} footer={<>
        <button className="btn-secondary" onClick={() => setDialog(null)}>Cancel</button>
        <button className="btn-danger" disabled={busy || !form.reason.trim()} onClick={() => post(`/claims/${c.id}/escalate/`, { reason: form.reason }, "Escalated — an SIU investigation is open")}><FileSearch className="h-4 w-4" />Escalate</button></>}>
        {formError && <Banner tone="bad">{formError}</Banner>}
        <Field label="Why does this claim need investigation?" required hint="Internal: never shown to the customer."><Textarea value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} /></Field>
      </Modal>

      <Modal open={dialog === "appeal"} title={`Decide appeal ${pendingAppeal ? pendingAppeal.sequence : ""}`} onClose={() => setDialog(null)} footer={<>
        <button className="btn-secondary" onClick={() => setDialog(null)}>Cancel</button>
        <button className="btn-primary" disabled={busy || !form.accept || !form.note.trim() || (form.accept === "no" && !form.allow)}
          onClick={() => pendingAppeal && post(`/appeals/${pendingAppeal.id}/decide/`, { accept: form.accept === "yes", note: form.note, allow_further_appeal: form.accept === "no" ? form.allow === "yes" : null }, "Appeal decided")}>Record decision</button></>}>
        {formError && <Banner tone="bad">{formError}</Banner>}
        {pendingAppeal && <p className="rounded bg-paper px-3 py-2 text-sm">{pendingAppeal.reason}</p>}
        <Field label="Decision" required>
          <Select value={form.accept} onChange={(e) => setForm({ ...form, accept: e.target.value })}><option value="">Choose…</option><option value="yes">Accept — reopen and reassess the claim</option><option value="no">Decline — keep the rejection</option></Select>
        </Field>
        {form.accept === "no" && (
          <Field label="May the customer appeal again?" required>
            <Select value={form.allow} onChange={(e) => setForm({ ...form, allow: e.target.value })}><option value="">Choose…</option><option value="yes">Yes</option><option value="no">No, reject permanently</option></Select>
          </Field>
        )}
        <Field label="Note to the customer" required><Textarea value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} /></Field>
      </Modal>
    </div>
  );
}
