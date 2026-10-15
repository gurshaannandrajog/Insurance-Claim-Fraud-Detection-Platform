import { Check, Download, FileText, ImageIcon, RotateCcw, ShieldAlert, Upload, X } from "lucide-react";
import { useRef, useState } from "react";
import { api, downloadFile, errorMessage } from "../api/client";
import type { ChecklistItem, ClaimDocument, TimelineEntry } from "../api/types";
import { dateTime, fileSize } from "../lib/format";
import { ACCEPT_FILES, CLAIM_STATUS_TONE, DOC_STATUS_TONE, DOCUMENT_TYPES, RISK_TONE, checkFile } from "../lib/labels";
import { useToast } from "./Toast";
import { Badge, Field, Modal, Select, Textarea } from "./ui";

export const ClaimStatusBadge = ({ status, label }: { status: string; label: string }) =>
  <Badge tone={CLAIM_STATUS_TONE[status] ?? "neutral"}>{label}</Badge>;

export const RiskBadge = ({ level, score }: { level?: string | null; score?: number | null }) =>
  level ? <Badge tone={RISK_TONE[level]}>{score ?? "–"} · {level === "HIGH" ? "High" : level === "MEDIUM" ? "Medium" : "Low"}</Badge>
    : <span className="text-xs text-ink-300">Not assessed</span>;

/**
 * Where the claim sits in its lifecycle. Each stage is filled once reached; the outcome stage takes the
 * colour of the decision. This is the one visual signature of the product: it reads at a glance on every claim.
 */
export function StatusRail({ status, label }: { status: string; label: string }) {
  const stage =
    status === "SUBMITTED" ? 0 :
    ["UNDER_REVIEW", "DOCUMENTS_PENDING", "FRAUD_REVIEW"].includes(status) ? 1 : 2;
  const outcomeTone = status === "APPROVED" ? "bg-ok" : ["REJECTED", "PERMANENTLY_REJECTED"].includes(status) ? "bg-bad" : status === "CLOSED" ? "bg-ink-500" : "bg-cover";
  const steps = ["Submitted", "In review", stage === 2 ? label : "Decision"];
  return (
    <ol className="grid grid-cols-3 gap-1.5" aria-label={`Claim progress: ${label}`}>
      {steps.map((s, i) => {
        const reached = i <= stage;
        const bar = !reached ? "bg-line" : i === 2 ? outcomeTone : i === stage ? "bg-cover" : "bg-ink-500";
        return (
          <li key={s} className="min-w-0">
            <div className={`h-1.5 rounded-full ${bar}`} />
            <div className={`mt-2 truncate text-xs ${reached ? "font-medium text-ink" : "text-ink-300"}`}>
              {i === 1 && stage === 1 ? label : s}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

/** 0–100 risk scale with the SRS bands (0–29 / 30–59 / 60–100) drawn underneath the marker. */
export function RiskMeter({ score, level }: { score: number; level: string }) {
  return (
    <div>
      <div className="flex items-baseline gap-2">
        <span className={`text-4xl font-semibold tracking-tight ${level === "HIGH" ? "text-bad" : level === "MEDIUM" ? "text-warn" : "text-ok"}`}>{score}</span>
        <span className="text-sm text-ink-500">/ 100 — {level === "HIGH" ? "High" : level === "MEDIUM" ? "Medium" : "Low"} risk</span>
      </div>
      <div className="relative mt-3">
        <div className="flex h-2 overflow-hidden rounded-full">
          <div className="bg-ok/70" style={{ width: "30%" }} />
          <div className="bg-warn/60" style={{ width: "30%" }} />
          <div className="bg-bad/70" style={{ width: "40%" }} />
        </div>
        <div className="absolute -top-1 h-4 w-1 -translate-x-1/2 rounded bg-ink ring-2 ring-white" style={{ left: `${Math.min(100, Math.max(0, score))}%` }} />
        <div className="mt-1.5 flex text-[11px] text-ink-300">
          <span style={{ width: "30%" }}>Low 0–29</span><span style={{ width: "30%" }}>Medium 30–59</span><span>High 60–100</span>
        </div>
      </div>
    </div>
  );
}

export function Timeline({ entries, staff }: { entries: TimelineEntry[]; staff?: boolean }) {
  return (
    <ol className="relative space-y-5 border-l border-line pl-5">
      {[...entries].reverse().map((e) => (
        <li key={e.id} className="relative">
          <span className={`absolute -left-[25px] top-1 h-2.5 w-2.5 rounded-full ring-4 ring-white ${e.is_internal ? "bg-bad" : "bg-cover"}`} />
          <div className="flex flex-wrap items-center gap-2">
            <ClaimStatusBadge status={e.to_status} label={e.to_status_display} />
            {staff && e.is_internal && <span className="text-xs text-bad">Internal — hidden from customer</span>}
          </div>
          {e.reason && <p className="mt-1.5 text-sm text-ink-700">{e.reason}</p>}
          <p className="mt-1 text-xs text-ink-500">{dateTime(e.created_at)}{e.actor ? ` by ${e.actor}` : ""}</p>
        </li>
      ))}
    </ol>
  );
}

export function Checklist({ items }: { items: ChecklistItem[] }) {
  return (
    <ul className="space-y-2">
      {items.map((c) => (
        <li key={c.label} className="flex items-center gap-2.5 text-sm">
          <span className={`flex h-5 w-5 items-center justify-center rounded-full ${c.verified ? "bg-ok text-white" : c.rejected ? "bg-bad text-white" : c.provided ? "bg-warn-light text-warn" : "border border-dashed border-ink-300"}`}>
            {c.verified ? <Check className="h-3 w-3" /> : c.rejected ? <X className="h-3 w-3" /> : null}
          </span>
          <span className={c.provided ? "" : "text-ink-500"}>{c.label}</span>
          <span className="ml-auto text-xs text-ink-500">
            {c.verified ? "Verified" : c.rejected ? "Rejected — replace" : c.provided ? "Awaiting verification" : "Not provided"}
          </span>
        </li>
      ))}
    </ul>
  );
}

interface DocListProps {
  claimId: number;
  documents: ClaimDocument[];
  canReview?: boolean;
  canUpload?: boolean;
  canReplaceAny?: boolean;     // adjuster
  staff?: boolean;
  onChanged: () => void;
}

export function DocumentList({ claimId, documents, canReview, canUpload, canReplaceAny, staff, onChanged }: DocListProps) {
  const toast = useToast();
  const [showHistory, setShowHistory] = useState(false);
  const [rejecting, setRejecting] = useState<ClaimDocument | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState<number | null>(null);
  const [upload, setUpload] = useState<{ replaces?: ClaimDocument } | null>(null);

  const visible = documents.filter((d) => showHistory || d.is_current);
  const replacedCount = documents.filter((d) => !d.is_current).length;

  const verify = async (d: ClaimDocument) => {
    setBusy(d.id);
    try {
      await api.post(`/documents/${d.id}/verify/`);
      toast(`${d.document_type_display} verified`);
      onChanged();
    } catch (e) { toast(errorMessage(e), "error"); } finally { setBusy(null); }
  };

  const reject = async () => {
    if (!rejecting) return;
    if (!reason.trim()) return;
    setBusy(rejecting.id);
    try {
      await api.post(`/documents/${rejecting.id}/reject/`, { reason });
      toast(`${rejecting.document_type_display} rejected — the customer has been notified`);
      setRejecting(null); setReason("");
      onChanged();
    } catch (e) { toast(errorMessage(e), "error"); } finally { setBusy(null); }
  };

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <span className="text-sm text-ink-500">{documents.filter((d) => d.is_current).length} current document(s)</span>
        <div className="flex gap-2">
          {replacedCount > 0 && (
            <button className="btn-ghost btn-sm" onClick={() => setShowHistory(!showHistory)}>
              {showHistory ? "Hide replaced versions" : `Show ${replacedCount} replaced version(s)`}
            </button>
          )}
          {canUpload && <button className="btn-secondary btn-sm" onClick={() => setUpload({})}><Upload className="h-3.5 w-3.5" /> Upload document</button>}
        </div>
      </div>
      {visible.length === 0 ? <p className="py-6 text-center text-sm text-ink-500">No documents yet.</p> : (
        <ul className="divide-y divide-line rounded-md border border-line">
          {visible.map((d) => (
            <li key={d.id} className={`flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center ${d.is_current ? "" : "bg-paper/70 opacity-75"}`}>
              <div className="flex min-w-0 flex-1 items-start gap-3">
                {d.content_type === "application/pdf" ? <FileText className="mt-0.5 h-5 w-5 shrink-0 text-ink-500" /> : <ImageIcon className="mt-0.5 h-5 w-5 shrink-0 text-ink-500" />}
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium">{d.document_type_display}</span>
                    <Badge tone={DOC_STATUS_TONE[d.status]}>{d.status_display}</Badge>
                    {!d.is_current && <Badge>Replaced</Badge>}
                    {d.appeal && <Badge tone="info">Appeal evidence</Badge>}
                  </div>
                  <div className="truncate text-xs text-ink-500">
                    {d.original_filename} ({fileSize(d.size_bytes)}), uploaded {dateTime(d.uploaded_at)}{staff ? ` by ${d.uploaded_by_name}` : ""}
                  </div>
                  {d.rejection_reason && <div className="mt-1 text-xs text-bad">Rejected: {d.rejection_reason}</div>}
                </div>
              </div>
              <div className="flex shrink-0 flex-wrap gap-1.5">
                <button className="btn-ghost btn-sm" onClick={() => downloadFile(d.download_url, d.original_filename).catch((e) => toast(errorMessage(e), "error"))}>
                  <Download className="h-3.5 w-3.5" /> Download
                </button>
                {canReview && d.is_current && d.status === "PENDING" && (<>
                  <button className="btn-secondary btn-sm" disabled={busy === d.id} onClick={() => verify(d)}><Check className="h-3.5 w-3.5" /> Verify</button>
                  <button className="btn-secondary btn-sm text-bad" disabled={busy === d.id} onClick={() => setRejecting(d)}><X className="h-3.5 w-3.5" /> Reject</button>
                </>)}
                {canUpload && d.is_current && (canReplaceAny || d.status === "REJECTED") && (
                  <button className="btn-secondary btn-sm" onClick={() => setUpload({ replaces: d })}><RotateCcw className="h-3.5 w-3.5" /> Replace</button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      <Modal open={!!rejecting} title={`Reject ${rejecting?.document_type_display ?? "document"}`} onClose={() => setRejecting(null)}
        footer={<>
          <button className="btn-secondary" onClick={() => setRejecting(null)}>Cancel</button>
          <button className="btn-danger" disabled={!reason.trim() || busy !== null} onClick={reject}>Reject document</button>
        </>}>
        <Field label="Reason shared with the customer" required hint="The customer receives this by email and in the app.">
          <Textarea value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Scan is blurred; the registration number is not readable." />
        </Field>
      </Modal>

      {upload && (
        <UploadModal claimId={claimId} replaces={upload.replaces} staff={staff} onClose={() => setUpload(null)}
          onDone={() => { setUpload(null); onChanged(); }} />
      )}
    </div>
  );
}

function UploadModal({ claimId, replaces, staff, onClose, onDone }:
  { claimId: number; replaces?: ClaimDocument; staff?: boolean; onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const [type, setType] = useState(replaces?.document_type ?? "");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  const submit = async () => {
    if (!type) return setError("Choose a document type.");
    if (!file) return setError("Choose a file.");
    const problem = checkFile(file);
    if (problem) return setError(problem);
    const fd = new FormData();
    fd.append("document_type", type);
    fd.append("file", file);
    if (replaces) fd.append("replaces", String(replaces.id));
    setBusy(true);
    try {
      await api.post(`/claims/${claimId}/documents/`, fd);
      toast(replaces ? "Document replaced" : "Document uploaded");
      onDone();
    } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  };

  return (
    <Modal open title={replaces ? `Replace ${replaces.document_type_display}` : "Upload document"} onClose={onClose}
      footer={<>
        <button className="btn-secondary" onClick={onClose}>Cancel</button>
        <button className="btn-primary" disabled={busy} onClick={submit}>{busy ? "Uploading…" : replaces ? "Replace document" : "Upload document"}</button>
      </>}>
      {!replaces && (
        <Field label="Document type" required>
          <Select value={type} onChange={(e) => setType(e.target.value)}>
            <option value="">Select…</option>
            {DOCUMENT_TYPES.filter((d) => staff || !d.staffOnly).map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
          </Select>
        </Field>
      )}
      <Field label="File" required hint="PDF, JPG or JPEG, up to 10 MB.">
        <input ref={input} type="file" accept={ACCEPT_FILES} className="input file:mr-3 file:rounded file:border-0 file:bg-cover-light file:px-3 file:py-1 file:text-sm file:text-cover-dark"
          onChange={(e) => { setFile(e.target.files?.[0] ?? null); setError(""); }} />
      </Field>
      {error && <p className="field-error flex items-center gap-1.5"><ShieldAlert className="h-3.5 w-3.5" />{error}</p>}
    </Modal>
  );
}
