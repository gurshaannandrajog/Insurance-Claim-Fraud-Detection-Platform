import { ArrowLeft, Clock, FileUp, Pencil, Scale } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, api, errorMessage } from "../../api/client";
import type { CustomerClaim } from "../../api/types";
import { Checklist, ClaimStatusBadge, DocumentList, StatusRail, Timeline } from "../../components/claim-parts";
import { useToast } from "../../components/Toast";
import { Badge, Banner, ConfirmDialog, ErrorState, Field, Input, Modal, Panel, Select, Spinner, Textarea } from "../../components/ui";
import { date, dateTime, money, todayISO } from "../../lib/format";
import { ACCEPT_FILES, CLAIM_TYPES, DOCUMENT_TYPES, checkFile } from "../../lib/labels";
import { useApi } from "../../lib/useApi";

function Countdown({ seconds, onEnd }: { seconds: number; onEnd: () => void }) {
  const [left, setLeft] = useState(seconds);
  useEffect(() => setLeft(seconds), [seconds]);
  useEffect(() => {
    if (left <= 0) { onEnd(); return; }
    const t = setTimeout(() => setLeft(left - 1), 1000);
    return () => clearTimeout(t);
  }, [left, onEnd]);
  return <span className="font-semibold tabular-nums">{Math.floor(left / 60)}:{String(left % 60).padStart(2, "0")}</span>;
}

function EditClaimModal({ claim, onClose, onSaved }: { claim: CustomerClaim; onClose: () => void; onSaved: (c: CustomerClaim) => void }) {
  const toast = useToast();
  const [d, setD] = useState({ claim_type: claim.claim_type, incident_date: claim.incident_date, incident_time: claim.incident_time.slice(0, 5),
    incident_location: claim.incident_location, description: claim.description, requested_amount: claim.requested_amount });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const bind = (k: keyof typeof d) => ({ id: k, value: d[k], invalid: !!errors[k], onChange: (e: { target: { value: string } }) => setD({ ...d, [k]: e.target.value }) });
  const save = async () => {
    try {
      const r = await api.patch<CustomerClaim>(`/claims/${claim.id}/`, d);
      toast("Claim updated");
      onSaved(r.data);
    } catch (e) {
      if (e instanceof ApiError) setErrors(e.fields);
      setError(errorMessage(e));   // e.g. the 30-minute window closed meanwhile — the server decides
    }
  };
  return (
    <Modal open wide title={`Edit ${claim.claim_number}`} onClose={onClose}
      footer={<><button className="btn-secondary" onClick={onClose}>Cancel</button><button className="btn-primary" onClick={save}>Save changes</button></>}>
      {error && <Banner tone="bad">{error}</Banner>}
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Claim type" id="claim_type"><Select {...bind("claim_type")}>{CLAIM_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}</Select></Field>
        <Field label="Amount claimed (₹)" id="requested_amount" error={errors.requested_amount}><Input type="number" {...bind("requested_amount")} /></Field>
        <Field label="Date of incident" id="incident_date" error={errors.incident_date}><Input type="date" max={todayISO()} {...bind("incident_date")} /></Field>
        <Field label="Time" id="incident_time" error={errors.incident_time}><Input type="time" {...bind("incident_time")} /></Field>
        <div className="sm:col-span-2"><Field label="Location" id="incident_location" error={errors.incident_location}><Input {...bind("incident_location")} /></Field></div>
        <div className="sm:col-span-2"><Field label="Description" id="description" error={errors.description}><Textarea rows={5} {...bind("description")} /></Field></div>
      </div>
    </Modal>
  );
}

function AppealModal({ claim, onClose, onDone }: { claim: CustomerClaim; onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const [reason, setReason] = useState("");
  const [files, setFiles] = useState<{ type: string; file: File }[]>([]);
  const [type, setType] = useState("OTHER");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    if (reason.trim().length < 20) return setError("Explain why the decision should be reconsidered (at least 20 characters).");
    const fd = new FormData();
    fd.append("reason", reason);
    files.forEach((f) => { fd.append("document_types", f.type); fd.append("files", f.file); });
    setBusy(true);
    try { await api.post(`/claims/${claim.id}/appeal/`, fd); toast("Appeal submitted"); onDone(); }
    catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  };
  return (
    <Modal open wide title={`Appeal ${claim.claim_number}`} onClose={onClose}
      footer={<><button className="btn-secondary" onClick={onClose}>Cancel</button><button className="btn-primary" disabled={busy} onClick={submit}>Submit appeal</button></>}>
      {error && <Banner tone="bad">{error}</Banner>}
      <Banner tone="info">A claim adjuster reviews your appeal. If it's accepted, the claim is reopened and reassessed.</Banner>
      <Field label="Grounds for appeal" required hint="Add new information the adjuster didn't have."><Textarea rows={5} value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
      <div>
        <p className="label">Additional evidence</p>
        <div className="flex flex-wrap gap-2">
          <Select className="w-auto" value={type} onChange={(e) => setType(e.target.value)} aria-label="Document type">
            {DOCUMENT_TYPES.filter((d) => !d.staffOnly).map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
          </Select>
          <label className="btn-secondary cursor-pointer"><FileUp className="h-4 w-4" />Add file
            <input type="file" accept={ACCEPT_FILES} className="sr-only" onChange={(e) => {
              const f = e.target.files?.[0]; e.target.value = "";
              if (!f) return; const p = checkFile(f); if (p) return setError(p);
              setFiles([...files, { type, file: f }]);
            }} /></label>
        </div>
        <ul className="mt-2 text-sm">{files.map((f, i) => <li key={i}>{DOCUMENT_TYPES.find((d) => d.value === f.type)?.label}: {f.file.name}</li>)}</ul>
      </div>
    </Modal>
  );
}

export default function CustomerClaimDetail() {
  const { id } = useParams();
  const toast = useToast();
  const { data: claim, setData, loading, error, reload } = useApi<CustomerClaim>(`/claims/${id}/`);
  const [editing, setEditing] = useState(false);
  const [appealing, setAppealing] = useState(false);
  const [confirm, setConfirm] = useState<"withdraw" | "accept" | null>(null);

  if (loading && !claim) return <Spinner />;
  if (error || !claim) return <ErrorState message={error ?? "Claim not found."} onRetry={reload} />;
  const can = (a: string) => claim.actions.includes(a);

  const act = async (path: string, msg: string) => {
    try { const r = await api.post<CustomerClaim>(`/claims/${claim.id}/${path}/`); setData(r.data); toast(msg); }
    catch (e) { toast(errorMessage(e), "error"); } finally { setConfirm(null); }
  };
  const pendingAppeal = claim.appeals.find((a) => a.status === "PENDING");

  return (
    <div className="space-y-6">
      <Link to="/claims" className="inline-flex items-center gap-1.5 text-sm text-ink-500 hover:text-ink"><ArrowLeft className="h-4 w-4" />My claims</Link>
      <section className="panel p-5 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-3"><h1>{claim.claim_number}</h1><ClaimStatusBadge status={claim.status} label={claim.status_display} /></div>
            <p className="mt-1 text-sm text-ink-500">{claim.claim_type_display} claim on {claim.vehicle.registration_number}, submitted {dateTime(claim.submitted_at)}</p>
          </div>
          <div className="text-right">
            <div className="text-sm text-ink-500">Requested</div><div className="text-xl font-semibold">{money(claim.requested_amount)}</div>
            {claim.approved_amount && <div className="text-sm text-ok">Approved {money(claim.approved_amount)}</div>}
          </div>
        </div>
        <div className="mt-6"><StatusRail status={claim.status} label={claim.status_display} /></div>
        {(can("edit") || can("withdraw")) && (
          <div className="mt-5 flex flex-wrap items-center gap-3 rounded-md bg-info-light px-4 py-3 text-sm text-info">
            <Clock className="h-4 w-4" />
            <span>You can edit or withdraw this claim for <Countdown seconds={claim.edit_seconds_remaining} onEnd={reload} /> more, or until an adjuster starts the review.</span>
            <div className="ml-auto flex gap-2">
              {can("edit") && <button className="btn-secondary btn-sm" onClick={() => setEditing(true)}><Pencil className="h-3.5 w-3.5" />Edit claim</button>}
              {can("withdraw") && <button className="btn-ghost btn-sm text-bad" onClick={() => setConfirm("withdraw")}>Withdraw</button>}
            </div>
          </div>
        )}
        {["REJECTED", "PERMANENTLY_REJECTED"].includes(claim.status) && (
          <div className="mt-5 rounded-md border border-bad/30 bg-bad-light px-4 py-3 text-sm">
            <p className="font-medium text-bad">Reason for rejection</p>
            <p className="mt-1 text-ink-700">{claim.rejection_reason}</p>
            {claim.status === "PERMANENTLY_REJECTED" && <p className="mt-2 text-ink-700">No further appeal is permitted. This decision is final.</p>}
            {pendingAppeal && <p className="mt-2 text-ink-700">Your appeal submitted {date(pendingAppeal.created_at)} is awaiting review.</p>}
            {(can("appeal") || can("accept_decision")) && (
              <div className="mt-3 flex flex-wrap items-center gap-2">
                {can("appeal") && <button className="btn-primary btn-sm" onClick={() => setAppealing(true)}><Scale className="h-3.5 w-3.5" />Appeal this decision</button>}
                {can("accept_decision") && <button className="btn-secondary btn-sm" onClick={() => setConfirm("accept")}>Accept and close claim</button>}
                {claim.appeal_deadline && can("appeal") && <span className="text-xs text-ink-500">Appeal by {date(claim.appeal_deadline)}</span>}
              </div>
            )}
          </div>
        )}
      </section>

      <div className="grid gap-6 lg:grid-cols-[1.6fr_1fr]">
        <div className="space-y-6">
          <Panel title="Incident">
            <dl className="dl">
              <dt>Date and time</dt><dd>{date(claim.incident_date)} at {claim.incident_time.slice(0, 5)}</dd>
              <dt>Location</dt><dd>{claim.incident_location}</dd>
              <dt>Vehicle</dt><dd>{claim.vehicle.registration_number}, {claim.vehicle.make} {claim.vehicle.model}</dd>
              <dt>Policy</dt><dd>{claim.policy.policy_number} ({claim.policy.status_display})</dd>
            </dl>
            <p className="mt-4 whitespace-pre-wrap text-sm text-ink-700">{claim.description}</p>
          </Panel>
          <div id="documents">
            <Panel title="Documents">
              <DocumentList claimId={claim.id} documents={claim.documents} canUpload={can("upload_document")} onChanged={reload} />
            </Panel>
          </div>
          {claim.appeals.length > 0 && (
            <Panel title="Appeals">
              <ul className="space-y-4">{claim.appeals.map((a) => (
                <li key={a.id} className="rounded-md border border-line p-4 text-sm">
                  <div className="flex items-center justify-between"><span className="font-medium">Appeal {a.sequence}, {date(a.created_at)}</span>
                    <Badge tone={a.status === "ACCEPTED" ? "ok" : a.status === "DECLINED" ? "bad" : "warn"}>{a.status_display}</Badge></div>
                  <p className="mt-2 text-ink-700">{a.reason}</p>
                  {a.decision_note && <p className="mt-2 text-ink-500">Decision: {a.decision_note}</p>}
                </li>))}
              </ul>
            </Panel>
          )}
        </div>
        <div className="space-y-6">
          <Panel title="Document checklist"><Checklist items={claim.document_checklist} /></Panel>
          <Panel title="History"><Timeline entries={claim.timeline} /></Panel>
        </div>
      </div>

      {editing && <EditClaimModal claim={claim} onClose={() => setEditing(false)} onSaved={(c) => { setEditing(false); setData(c); }} />}
      {appealing && <AppealModal claim={claim} onClose={() => setAppealing(false)} onDone={() => { setAppealing(false); reload(); }} />}
      <ConfirmDialog open={confirm === "withdraw"} title="Withdraw this claim?" danger confirmLabel="Withdraw claim"
        message="The claim will be closed and will not be processed. You can file a new claim for the same incident afterwards."
        onClose={() => setConfirm(null)} onConfirm={() => act("withdraw", "Claim withdrawn")} />
      <ConfirmDialog open={confirm === "accept"} title="Accept the decision?" confirmLabel="Accept and close"
        message="The claim will be closed and you will no longer be able to appeal." onClose={() => setConfirm(null)}
        onConfirm={() => act("accept-decision", "Claim closed")} />
    </div>
  );
}
