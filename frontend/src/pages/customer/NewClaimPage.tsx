import { Check, FileUp, Loader2, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ApiError, api, errorMessage, type Page } from "../../api/client";
import type { CustomerClaim, Policy } from "../../api/types";
import { useToast } from "../../components/Toast";
import { Banner, ConfirmDialog, Empty, Field, Input, PageHeader, Select, Spinner, Textarea } from "../../components/ui";
import { date, fileSize, money, todayISO } from "../../lib/format";
import { ACCEPT_FILES, CLAIM_TYPES, DOCUMENT_TYPES, EVIDENCE_FOR, checkFile } from "../../lib/labels";
import { useApi } from "../../lib/useApi";

const REQUIRED = ["KYC", "ADDRESS_PROOF", "VEHICLE_REGISTRATION"];
const STEPS = ["Policy", "Incident", "Documents", "Review"];
const docLabel = (t: string) => DOCUMENT_TYPES.find((d) => d.value === t)?.label ?? t;

interface Slot { type: string; file: File }

export default function NewClaimPage() {
  const toast = useToast();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const { data, loading } = useApi<Page<Policy>>("/policies/?status=ACTIVE,PARTIALLY_CLAIMED&page_size=100");
  const [step, setStep] = useState(0);
  const [policyId, setPolicyId] = useState(params.get("policy") ?? "");
  const [d, setD] = useState({ claim_type: "ACCIDENT", incident_date: "", incident_time: "", incident_location: "", description: "", requested_amount: "" });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [docs, setDocs] = useState<Slot[]>([]);
  const [extraType, setExtraType] = useState("");
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [serverError, setServerError] = useState("");

  const policy = useMemo(() => data?.results.find((p) => String(p.id) === policyId), [data, policyId]);
  const evidenceType = EVIDENCE_FOR[d.claim_type];
  const bind = (k: keyof typeof d) => ({ id: k, value: d[k], invalid: !!errors[k], onChange: (e: { target: { value: string } }) => { setD({ ...d, [k]: e.target.value }); setErrors({ ...errors, [k]: "" }); } });

  const validateIncident = () => {
    const e: Record<string, string> = {};
    if (!d.incident_date) e.incident_date = "Required";
    else if (policy && (d.incident_date < policy.start_date || d.incident_date > policy.end_date)) e.incident_date = `Must fall within the policy period (${date(policy.start_date)} to ${date(policy.end_date)}).`;
    else if (d.incident_date > todayISO()) e.incident_date = "Cannot be in the future.";
    if (!d.incident_time) e.incident_time = "Required";
    if (d.incident_location.trim().length < 3) e.incident_location = "Describe where it happened.";
    if (d.description.trim().length < 20) e.description = "At least 20 characters — what happened and what was damaged.";
    const amt = Number(d.requested_amount);
    if (!amt || amt <= 0) e.requested_amount = "Enter the amount you are claiming.";
    else if (policy && amt > Number(policy.remaining_idv)) e.requested_amount = `Cannot exceed the remaining cover of ${money(policy.remaining_idv)}.`;
    setErrors(e);
    return !Object.keys(e).length;
  };

  const setSlot = (type: string, file: File | undefined) => {
    if (!file) return;
    const problem = checkFile(file);
    if (problem) { toast(`${file.name}: ${problem}`, "error"); return; }
    setDocs((prev) => {
      const isSingle = REQUIRED.includes(type);
      const rest = isSingle ? prev.filter((x) => x.type !== type) : prev;
      return [...rest, { type, file }];
    });
  };

  const missing = REQUIRED.filter((t) => !docs.some((x) => x.type === t));
  const next = () => {
    if (step === 0 && !policy) return toast("Choose the policy this claim is for.", "error");
    if (step === 1 && !validateIncident()) return;
    if (step === 2 && missing.length) return toast(`Upload: ${missing.map(docLabel).join(", ")}`, "error");
    setStep(step + 1);
  };

  const submit = async () => {
    if (!policy) return;
    const fd = new FormData();
    fd.append("vehicle_id", String(policy.vehicle.id));
    fd.append("policy_id", String(policy.id));
    Object.entries(d).forEach(([k, v]) => fd.append(k, v));
    docs.forEach((x) => { fd.append("document_types", x.type); fd.append("files", x.file); });
    setBusy(true); setServerError("");
    try {
      const r = await api.post<CustomerClaim>("/claims/", fd);
      toast(`Claim ${r.data.claim_number} submitted`);
      navigate(`/claims/${r.data.id}`, { replace: true });
    } catch (e) {
      setConfirm(false);
      if (e instanceof ApiError && Object.keys(e.fields).length) { setErrors(e.fields); }
      setServerError(errorMessage(e));
      if (e instanceof ApiError && ["incident_in_future", "invalid_amount", "exceeds_remaining_idv"].includes(e.code)) setStep(1);
    } finally { setBusy(false); }
  };

  if (loading) return <Spinner />;
  if (!data?.results.length) return (
    <><PageHeader title="Submit a claim" /><div className="panel"><Empty title="No policy can accept a claim" action={<Link to="/policies" className="btn-primary">View policies</Link>}>
      Claims can be filed only against Active or Partially Claimed policies.</Empty></div></>
  );

  return (
    <>
      <PageHeader title="Submit a claim" subtitle="You can edit the claim for 30 minutes after submitting, until an adjuster starts the review." />
      <ol className="mb-6 grid grid-cols-4 gap-2" aria-label="Steps">
        {STEPS.map((s, i) => (
          <li key={s} className={`flex items-center gap-2 border-t-2 pt-2 text-sm ${i <= step ? "border-cover font-medium text-ink" : "border-line text-ink-300"}`}>
            <span className={`flex h-5 w-5 items-center justify-center rounded-full text-[11px] ${i < step ? "bg-cover text-white" : i === step ? "border border-cover text-cover" : "border border-line"}`}>
              {i < step ? <Check className="h-3 w-3" /> : i + 1}
            </span>
            <span className="hidden sm:inline">{s}</span>
          </li>
        ))}
      </ol>
      {serverError && <div className="mb-4"><Banner tone="bad">{serverError}</Banner></div>}

      <div className="panel p-5 sm:p-6">
        {step === 0 && (
          <fieldset className="space-y-3">
            <legend className="mb-3 font-semibold">Which policy is this claim for?</legend>
            {data.results.map((p) => (
              <label key={p.id} className={`flex cursor-pointer items-start gap-3 rounded-md border p-4 ${policyId === String(p.id) ? "border-cover bg-cover-light/50" : "border-line hover:border-ink-300"}`}>
                <input type="radio" name="policy" className="mt-1 accent-[#0E7C7B]" checked={policyId === String(p.id)} onChange={() => setPolicyId(String(p.id))} />
                <span className="flex-1">
                  <span className="font-medium">{p.vehicle.registration_number}, {p.vehicle.make} {p.vehicle.model}</span>
                  <span className="block text-sm text-ink-500">{p.policy_number}, {p.plan_name}, valid until {date(p.end_date)}</span>
                </span>
                <span className="text-right text-sm"><span className="block font-medium">{money(p.remaining_idv)}</span><span className="text-xs text-ink-500">cover remaining</span></span>
              </label>
            ))}
          </fieldset>
        )}

        {step === 1 && (
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Claim type" required id="claim_type"><Select {...bind("claim_type")}>{CLAIM_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}</Select></Field>
            <Field label="Amount claimed (₹)" required id="requested_amount" error={errors.requested_amount} hint={policy && `Remaining cover ${money(policy.remaining_idv)}`}><Input type="number" min={1} {...bind("requested_amount")} /></Field>
            <Field label="Date of incident" required id="incident_date" error={errors.incident_date}><Input type="date" min={policy?.start_date} max={todayISO()} {...bind("incident_date")} /></Field>
            <Field label="Time of incident" required id="incident_time" error={errors.incident_time}><Input type="time" {...bind("incident_time")} /></Field>
            <div className="sm:col-span-2"><Field label="Location" required id="incident_location" error={errors.incident_location}><Input {...bind("incident_location")} placeholder="Road, area, city" /></Field></div>
            <div className="sm:col-span-2"><Field label="What happened?" required id="description" error={errors.description} hint={`${d.description.trim().length} characters`}><Textarea rows={5} {...bind("description")} placeholder="Describe the incident and the damage to the vehicle." /></Field></div>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-5">
            <p className="text-sm text-ink-500">PDF, JPG or JPEG, up to 10 MB each. KYC, address proof and vehicle registration are required to submit.</p>
            <ul className="divide-y divide-line rounded-md border border-line">
              {[...REQUIRED, evidenceType].map((t) => {
                const slot = docs.filter((x) => x.type === t);
                const req = REQUIRED.includes(t);
                return (
                  <li key={t} className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center">
                    <div className="flex-1">
                      <span className="text-sm font-medium">{docLabel(t)}</span>
                      <span className={`ml-2 text-xs ${req ? "text-bad" : "text-ink-500"}`}>{req ? "Required" : "Needed before approval"}</span>
                      {slot.map((s) => <div key={s.file.name} className="text-xs text-ok">{s.file.name} ({fileSize(s.file.size)})</div>)}
                    </div>
                    <label className="btn-secondary btn-sm cursor-pointer">
                      <FileUp className="h-3.5 w-3.5" />{slot.length ? (req ? "Change file" : "Add another") : "Choose file"}
                      <input type="file" accept={ACCEPT_FILES} className="sr-only" onChange={(e) => { setSlot(t, e.target.files?.[0]); e.target.value = ""; }} />
                    </label>
                  </li>
                );
              })}
            </ul>
            <div>
              <p className="label">Other supporting documents</p>
              <div className="flex flex-wrap gap-2">
                <Select className="w-auto" value={extraType} onChange={(e) => setExtraType(e.target.value)} aria-label="Document type">
                  <option value="">Document type…</option>
                  {DOCUMENT_TYPES.filter((x) => !x.staffOnly && !REQUIRED.includes(x.value) && x.value !== evidenceType).map((x) => <option key={x.value} value={x.value}>{x.label}</option>)}
                </Select>
                <label className={`btn-secondary cursor-pointer ${extraType ? "" : "pointer-events-none opacity-50"}`}>
                  <FileUp className="h-4 w-4" />Add file
                  <input type="file" accept={ACCEPT_FILES} className="sr-only" disabled={!extraType} onChange={(e) => { setSlot(extraType, e.target.files?.[0]); e.target.value = ""; }} />
                </label>
              </div>
              <ul className="mt-2 space-y-1">
                {docs.filter((x) => !REQUIRED.includes(x.type) && x.type !== evidenceType).map((x, i) => (
                  <li key={i} className="flex items-center gap-2 text-sm"><span className="text-ink-500">{docLabel(x.type)}:</span>{x.file.name}
                    <button className="btn-ghost btn-sm" aria-label="Remove" onClick={() => setDocs(docs.filter((y) => y !== x))}><Trash2 className="h-3.5 w-3.5" /></button></li>
                ))}
              </ul>
            </div>
          </div>
        )}

        {step === 3 && policy && (
          <div className="grid gap-6 md:grid-cols-2">
            <dl className="dl">
              <dt>Vehicle</dt><dd>{policy.vehicle.registration_number}</dd>
              <dt>Policy</dt><dd>{policy.policy_number}</dd>
              <dt>Claim type</dt><dd>{CLAIM_TYPES.find((t) => t.value === d.claim_type)?.label}</dd>
              <dt>Incident</dt><dd>{date(d.incident_date)} at {d.incident_time}</dd>
              <dt>Location</dt><dd>{d.incident_location}</dd>
              <dt>Amount claimed</dt><dd>{money(d.requested_amount)}</dd>
            </dl>
            <div>
              <p className="mb-1 text-sm text-ink-500">Description</p>
              <p className="whitespace-pre-wrap text-sm">{d.description}</p>
              <p className="mb-1 mt-4 text-sm text-ink-500">Documents ({docs.length})</p>
              <ul className="text-sm">{docs.map((x, i) => <li key={i}>{docLabel(x.type)}: {x.file.name}</li>)}</ul>
            </div>
          </div>
        )}

        <div className="mt-6 flex justify-between border-t border-line pt-5">
          <button className="btn-secondary" disabled={step === 0} onClick={() => setStep(step - 1)}>Back</button>
          {step < 3 ? <button className="btn-primary" onClick={next}>Continue</button>
            : <button className="btn-primary" onClick={() => setConfirm(true)} disabled={busy}>{busy && <Loader2 className="h-4 w-4 animate-spin" />}Submit claim</button>}
        </div>
      </div>

      <ConfirmDialog open={confirm} title="Submit this claim?" busy={busy} confirmLabel="Submit claim" onClose={() => setConfirm(false)} onConfirm={submit}
        message={<>You are claiming <strong>{money(d.requested_amount)}</strong> on policy {policy?.policy_number}. You can still edit it for 30 minutes, or until an adjuster starts the review.</>} />
    </>
  );
}
