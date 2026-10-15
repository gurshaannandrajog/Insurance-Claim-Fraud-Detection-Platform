import { Download, Plus, Search } from "lucide-react";
import { useState } from "react";
import { ApiError, api, downloadFile, errorMessage, type Page } from "../../api/client";
import type { Plan, Policy, PolicyRequest, User } from "../../api/types";
import { useToast } from "../../components/Toast";
import { Badge, Banner, ConfirmDialog, Empty, ErrorState, Field, Input, Modal, PageHeader, Pagination, Panel, Select, Spinner, Textarea } from "../../components/ui";
import { date, dateTime, money, todayISO } from "../../lib/format";
import { CLAIM_STATUSES, CLAIM_TYPES, POLICY_STATUSES, POLICY_STATUS_TONE, REQUEST_TONE } from "../../lib/labels";
import { qs, useApi } from "../../lib/useApi";

// ----------------------------------------------------------------------------------- policy requests
export function PolicyRequestsAdmin() {
  const toast = useToast();
  const [status, setStatus] = useState("PENDING");
  const { data, loading, error, reload } = useApi<Page<PolicyRequest>>(`/policy-requests/${qs({ status })}`);
  const [approving, setApproving] = useState<PolicyRequest | null>(null);
  const [rejecting, setRejecting] = useState<PolicyRequest | null>(null);
  const [f, setF] = useState({ start_date: todayISO(), idv: "", decision_note: "", reason: "" });
  const [err, setErr] = useState("");

  const approve = async () => {
    if (!approving) return;
    try {
      const r = await api.post<Policy>(`/policy-requests/${approving.id}/approve/`, { start_date: f.start_date, idv: f.idv, decision_note: f.decision_note });
      toast(`Policy ${r.data.policy_number} issued`); setApproving(null); reload();
    } catch (e) { setErr(errorMessage(e)); }
  };
  const reject = async () => {
    if (!rejecting) return;
    try { await api.post(`/policy-requests/${rejecting.id}/reject/`, { reason: f.reason }); toast("Request declined"); setRejecting(null); reload(); }
    catch (e) { setErr(errorMessage(e)); }
  };

  return (
    <>
      <PageHeader title="Policy requests" subtitle="Approve a request to issue the policy. A vehicle can hold only one live policy." />
      <div className="panel">
        <div className="border-b border-line p-4"><Select className="w-auto" value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status">
          <option value="PENDING">Pending review</option><option value="APPROVED">Approved</option><option value="REJECTED">Rejected</option><option value="WITHDRAWN">Withdrawn</option><option value="">All</option></Select></div>
        {loading ? <Spinner /> : error ? <ErrorState message={error} onRetry={reload} /> : !data?.results.length ? <Empty title="No requests here" /> : (
          <div className="overflow-x-auto"><table className="table">
            <thead><tr><th>Customer</th><th>Vehicle</th><th>Plan</th><th className="text-right">IDV</th><th>Requested</th><th>Status</th><th /></tr></thead>
            <tbody>{data.results.map((r) => (
              <tr key={r.id}>
                <td><div className="font-medium">{r.customer_name}</div><div className="text-xs text-ink-500">{r.customer_email}</div></td>
                <td>{r.vehicle.registration_number}<div className="text-xs text-ink-500">{r.vehicle.make} {r.vehicle.model} ({r.vehicle.manufacturing_year})</div></td>
                <td>{r.plan.name}</td><td className="text-right">{money(r.requested_idv)}</td><td>{date(r.created_at)}</td>
                <td><Badge tone={REQUEST_TONE[r.status]}>{r.status_display}</Badge>{r.policy_number && <div className="text-xs text-ink-500">{r.policy_number}</div>}</td>
                <td className="whitespace-nowrap text-right">{r.status === "PENDING" && <>
                  <button className="btn-primary btn-sm" onClick={() => { setErr(""); setF({ ...f, idv: r.requested_idv, decision_note: "" }); setApproving(r); }}>Approve</button>{" "}
                  <button className="btn-secondary btn-sm" onClick={() => { setErr(""); setF({ ...f, reason: "" }); setRejecting(r); }}>Decline</button></>}</td>
              </tr>))}</tbody>
          </table></div>
        )}
      </div>
      <Modal open={!!approving} title="Issue policy" onClose={() => setApproving(null)}
        footer={<><button className="btn-secondary" onClick={() => setApproving(null)}>Cancel</button><button className="btn-primary" onClick={approve}>Issue policy</button></>}>
        {err && <Banner tone="bad">{err}</Banner>}
        {approving && <p className="text-sm">{approving.plan.name} for {approving.vehicle.registration_number} ({approving.customer_name}). Premium rate {approving.plan.premium_rate_percent}% for {approving.plan.term_months} months.</p>}
        <Field label="Start date" required><Input type="date" min={todayISO()} value={f.start_date} onChange={(e) => setF({ ...f, start_date: e.target.value })} /></Field>
        <Field label="Insured declared value (₹)" required hint={approving ? `Plan limits ${money(approving.plan.min_idv)} to ${money(approving.plan.max_idv)}` : undefined}><Input type="number" value={f.idv} onChange={(e) => setF({ ...f, idv: e.target.value })} /></Field>
        <Field label="Note"><Input value={f.decision_note} onChange={(e) => setF({ ...f, decision_note: e.target.value })} /></Field>
      </Modal>
      <Modal open={!!rejecting} title="Decline request" onClose={() => setRejecting(null)}
        footer={<><button className="btn-secondary" onClick={() => setRejecting(null)}>Cancel</button><button className="btn-danger" disabled={!f.reason.trim()} onClick={reject}>Decline request</button></>}>
        {err && <Banner tone="bad">{err}</Banner>}
        <Field label="Reason shared with the customer" required><Textarea value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} /></Field>
      </Modal>
    </>
  );
}

// ----------------------------------------------------------------------------------- policies
export function PoliciesAdmin() {
  const toast = useToast();
  const [p, setP] = useState({ status: "", search: "", page: 1 });
  const [search, setSearch] = useState("");
  const { data, loading, error, reload } = useApi<Page<Policy>>(`/policies/${qs(p)}`);
  const [cancel, setCancel] = useState<Policy | null>(null);
  const [reason, setReason] = useState("");
  const [err, setErr] = useState("");
  const doCancel = async () => {
    if (!cancel) return;
    try { await api.post(`/policies/${cancel.id}/cancel/`, { reason }); toast(`${cancel.policy_number} cancelled`); setCancel(null); reload(); }
    catch (e) { setErr(errorMessage(e)); }
  };
  return (
    <>
      <PageHeader title="Policies" subtitle="All issued policies. Policy terms cannot be edited after issue; a live policy can be cancelled." />
      <div className="panel">
        <form className="flex flex-wrap gap-3 border-b border-line p-4" onSubmit={(e) => { e.preventDefault(); setP({ ...p, search, page: 1 }); }}>
          <div className="relative min-w-[240px] flex-1"><Search className="absolute left-3 top-2.5 h-4 w-4 text-ink-300" /><Input className="pl-9" placeholder="Policy number, vehicle or customer" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Search" /></div>
          <Select className="w-auto" value={p.status} onChange={(e) => setP({ ...p, status: e.target.value, page: 1 })} aria-label="Status"><option value="">All statuses</option>{POLICY_STATUSES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select>
          <button className="btn-secondary">Search</button>
        </form>
        {loading ? <Spinner /> : error ? <ErrorState message={error} onRetry={reload} /> : !data?.results.length ? <Empty title="No policies found" /> : (<>
          <div className="overflow-x-auto"><table className="table">
            <thead><tr><th>Policy</th><th>Customer</th><th>Vehicle</th><th>Period</th><th className="text-right">IDV</th><th className="text-right">Paid out</th><th>Status</th><th /></tr></thead>
            <tbody>{data.results.map((x) => (
              <tr key={x.id}>
                <td className="font-medium">{x.policy_number}<div className="text-xs font-normal text-ink-500">{x.plan_name}</div></td>
                <td>{x.customer_name}</td><td>{x.vehicle.registration_number}</td>
                <td className="text-sm">{date(x.start_date)} to {date(x.end_date)}</td>
                <td className="text-right">{money(x.idv)}</td><td className="text-right">{money(x.cumulative_approved_amount)}</td>
                <td><Badge tone={POLICY_STATUS_TONE[x.status]}>{x.status_display}</Badge></td>
                <td className="text-right">{["ACTIVE", "PARTIALLY_CLAIMED", "CLAIMED"].includes(x.status) && <button className="btn-ghost btn-sm text-bad" onClick={() => { setErr(""); setReason(""); setCancel(x); }}>Cancel</button>}</td>
              </tr>))}</tbody>
          </table></div>
          <Pagination page={p.page} count={data.count} onPage={(n) => setP({ ...p, page: n })} />
        </>)}
      </div>
      <Modal open={!!cancel} title={`Cancel ${cancel?.policy_number}`} onClose={() => setCancel(null)}
        footer={<><button className="btn-secondary" onClick={() => setCancel(null)}>Keep policy</button><button className="btn-danger" disabled={!reason.trim()} onClick={doCancel}>Cancel policy</button></>}>
        {err && <Banner tone="bad">{err}</Banner>}
        <p className="text-sm text-ink-700">Cancellation is permanent. The customer is notified and the vehicle can then receive a new policy. Policies with claims still in progress cannot be cancelled.</p>
        <Field label="Reason" required><Textarea value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
      </Modal>
    </>
  );
}

// ----------------------------------------------------------------------------------- plans
const EMPTY_PLAN = { code: "", name: "", description: "", premium_rate_percent: "", term_months: "12", min_idv: "", max_idv: "", is_active: true };
export function PlansAdmin() {
  const toast = useToast();
  const { data, loading, error, reload } = useApi<Plan[]>("/policy-plans/");
  const [edit, setEdit] = useState<{ plan?: Plan; v: typeof EMPTY_PLAN } | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const save = async () => {
    if (!edit) return;
    try {
      if (edit.plan) await api.patch(`/policy-plans/${edit.plan.id}/`, edit.v); else await api.post("/policy-plans/", edit.v);
      toast("Plan saved — existing policies keep their original terms"); setEdit(null); reload();
    } catch (e) { setErrors(e instanceof ApiError ? { ...e.fields, _: e.message } : { _: errorMessage(e) }); }
  };
  const bind = (k: keyof typeof EMPTY_PLAN) => ({ value: String(edit?.v[k] ?? ""), invalid: !!errors[k], onChange: (e: { target: { value: string } }) => edit && setEdit({ ...edit, v: { ...edit.v, [k]: e.target.value } }) });
  return (
    <>
      <PageHeader title="Plans and pricing" subtitle="Changes apply to new policies only. Issued policies keep the terms they were sold with."
        actions={<button className="btn-primary" onClick={() => { setErrors({}); setEdit({ v: EMPTY_PLAN }); }}><Plus className="h-4 w-4" />New plan</button>} />
      {loading ? <Spinner /> : error ? <ErrorState message={error} onRetry={reload} /> : (
        <div className="panel overflow-x-auto"><table className="table">
          <thead><tr><th>Plan</th><th>Rate</th><th>Term</th><th>IDV range</th><th>Status</th><th /></tr></thead>
          <tbody>{data?.map((p) => (
            <tr key={p.id}>
              <td><div className="font-medium">{p.name}</div><div className="text-xs text-ink-500">{p.code}: {p.description}</div></td>
              <td>{p.premium_rate_percent}% / year</td><td>{p.term_months} months</td><td>{money(p.min_idv)} to {money(p.max_idv)}</td>
              <td>{p.is_active ? <Badge tone="ok">Offered</Badge> : <Badge>Withdrawn</Badge>}</td>
              <td className="text-right"><button className="btn-secondary btn-sm" onClick={() => { setErrors({}); setEdit({ plan: p, v: { ...p, term_months: String(p.term_months) } as unknown as typeof EMPTY_PLAN }); }}>Edit</button></td>
            </tr>))}</tbody>
        </table></div>
      )}
      <Modal open={!!edit} title={edit?.plan ? `Edit ${edit.plan.name}` : "New plan"} onClose={() => setEdit(null)}
        footer={<><button className="btn-secondary" onClick={() => setEdit(null)}>Cancel</button><button className="btn-primary" onClick={save}>Save plan</button></>}>
        {errors._ && <Banner tone="bad">{errors._}</Banner>}
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Code" required error={errors.code}><Input {...bind("code")} disabled={!!edit?.plan} /></Field>
          <Field label="Name" required error={errors.name}><Input {...bind("name")} /></Field>
          <Field label="Premium rate (% of IDV per year)" required error={errors.premium_rate_percent}><Input type="number" step="0.01" {...bind("premium_rate_percent")} /></Field>
          <Field label="Term (months)" required error={errors.term_months}><Input type="number" {...bind("term_months")} /></Field>
          <Field label="Minimum IDV (₹)" required error={errors.min_idv}><Input type="number" {...bind("min_idv")} /></Field>
          <Field label="Maximum IDV (₹)" required error={errors.max_idv}><Input type="number" {...bind("max_idv")} /></Field>
        </div>
        <Field label="Description"><Textarea {...bind("description")} /></Field>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="accent-[#0E7C7B]" checked={!!edit?.v.is_active} onChange={(e) => edit && setEdit({ ...edit, v: { ...edit.v, is_active: e.target.checked } })} />Offered to customers</label>
      </Modal>
    </>
  );
}

// ----------------------------------------------------------------------------------- staff users
export function UsersAdmin() {
  const toast = useToast();
  const [page, setPage] = useState(1);
  const { data, loading, error, reload } = useApi<Page<User>>(`/admin/users/${qs({ role: "STAFF", page })}`);
  const [creating, setCreating] = useState(false);
  const [v, setV] = useState({ full_name: "", email: "", role: "ADJUSTER", employee_id: "", department: "", phone: "" });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [confirm, setConfirm] = useState<{ user: User; action: string } | null>(null);
  const create = async () => {
    try { await api.post("/admin/users/", v); toast(`Account created — ${v.email} will receive a link to set a password`); setCreating(false); reload(); }
    catch (e) { setErrors(e instanceof ApiError ? { ...e.fields, _: e.message } : { _: errorMessage(e) }); }
  };
  const act = async () => {
    if (!confirm) return;
    try { await api.post(`/admin/users/${confirm.user.id}/${confirm.action}/`); toast("Account updated"); reload(); }
    catch (e) { toast(errorMessage(e), "error"); } finally { setConfirm(null); }
  };
  const bind = (k: keyof typeof v) => ({ value: v[k], invalid: !!errors[k], onChange: (e: { target: { value: string } }) => setV({ ...v, [k]: e.target.value }) });
  return (
    <>
      <PageHeader title="Staff accounts" subtitle="Claim adjusters, SIU investigators and administrators."
        actions={<button className="btn-primary" onClick={() => { setErrors({}); setCreating(true); }}><Plus className="h-4 w-4" />Add staff member</button>} />
      {loading ? <Spinner /> : error ? <ErrorState message={error} onRetry={reload} /> : (
        <div className="panel"><div className="overflow-x-auto"><table className="table">
          <thead><tr><th>Name</th><th>Role</th><th>Employee ID</th><th>Last sign-in</th><th>Status</th><th /></tr></thead>
          <tbody>{data?.results.map((u) => (
            <tr key={u.id}>
              <td><div className="font-medium">{u.full_name}</div><div className="text-xs text-ink-500">{u.email}</div></td>
              <td>{u.role_display}</td><td>{u.employee_profile?.employee_id}</td><td>{dateTime(u.last_login)}</td>
              <td className="space-x-1">{u.is_active ? <Badge tone="ok">Active</Badge> : <Badge>Deactivated</Badge>}{u.is_locked && <Badge tone="warn">Locked</Badge>}{!u.is_email_verified && <Badge tone="info">Password not set</Badge>}</td>
              <td className="whitespace-nowrap text-right space-x-1">
                {u.is_locked && <button className="btn-secondary btn-sm" onClick={() => setConfirm({ user: u, action: "unlock" })}>Unlock</button>}
                <button className="btn-ghost btn-sm" onClick={() => setConfirm({ user: u, action: u.is_active ? "deactivate" : "activate" })}>{u.is_active ? "Deactivate" : "Reactivate"}</button>
              </td>
            </tr>))}</tbody>
        </table></div><Pagination page={page} count={data?.count ?? 0} onPage={setPage} /></div>
      )}
      <Modal open={creating} title="Add staff member" onClose={() => setCreating(false)}
        footer={<><button className="btn-secondary" onClick={() => setCreating(false)}>Cancel</button><button className="btn-primary" onClick={create}>Create account</button></>}>
        {errors._ && <Banner tone="bad">{errors._}</Banner>}
        <Field label="Full name" required error={errors.full_name}><Input {...bind("full_name")} /></Field>
        <Field label="Work email" required error={errors.email}><Input type="email" {...bind("email")} /></Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Role" required><Select {...bind("role")}><option value="ADJUSTER">Claim Adjuster</option><option value="SIU">SIU Investigator</option><option value="ADMIN">Administrator</option></Select></Field>
          <Field label="Employee ID" required error={errors.employee_id} hint="e.g. EMP-2003"><Input {...bind("employee_id")} /></Field>
          <Field label="Department"><Input {...bind("department")} /></Field>
          <Field label="Phone" error={errors.phone}><Input {...bind("phone")} /></Field>
        </div>
        <p className="text-xs text-ink-500">The new staff member sets their own password from an emailed link. You never see or choose it.</p>
      </Modal>
      <ConfirmDialog open={!!confirm} title={`${confirm?.action === "unlock" ? "Unlock" : confirm?.action === "activate" ? "Reactivate" : "Deactivate"} ${confirm?.user.full_name}?`}
        message={confirm?.action === "deactivate" ? "They will no longer be able to sign in. Their history is kept." : "This takes effect immediately."}
        confirmLabel="Confirm" danger={confirm?.action === "deactivate"} onConfirm={act} onClose={() => setConfirm(null)} />
    </>
  );
}

export function CustomersAdmin() {
  const [p, setP] = useState({ search: "", page: 1 });
  const [search, setSearch] = useState("");
  const { data, loading, error, reload } = useApi<Page<User>>(`/admin/customers/${qs(p)}`);
  const toast = useToast();
  const toggle = async (u: User) => {
    try { await api.post(`/admin/users/${u.id}/${u.is_active ? "deactivate" : "activate"}/`); toast("Customer updated"); reload(); } catch (e) { toast(errorMessage(e), "error"); }
  };
  return (
    <>
      <PageHeader title="Customers" subtitle="Registered policyholders." />
      <div className="panel">
        <form className="flex gap-3 border-b border-line p-4" onSubmit={(e) => { e.preventDefault(); setP({ search, page: 1 }); }}>
          <Input placeholder="Name, email or phone" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Search" /><button className="btn-secondary">Search</button>
        </form>
        {loading ? <Spinner /> : error ? <ErrorState message={error} onRetry={reload} /> : !data?.results.length ? <Empty title="No customers found" /> : (<>
          <div className="overflow-x-auto"><table className="table">
            <thead><tr><th>Customer</th><th>Phone</th><th>City</th><th>Joined</th><th className="text-right">Vehicles</th><th className="text-right">Policies</th><th className="text-right">Claims</th><th>Status</th><th /></tr></thead>
            <tbody>{data.results.map((u) => (
              <tr key={u.id}>
                <td><div className="font-medium">{u.full_name}</div><div className="text-xs text-ink-500">{u.email}</div></td>
                <td>{u.customer_profile?.phone}</td><td>{u.customer_profile?.city}</td><td>{date(u.date_joined)}</td>
                <td className="text-right">{u.vehicle_count}</td><td className="text-right">{u.policy_count}</td><td className="text-right">{u.claim_count}</td>
                <td>{!u.is_email_verified ? <Badge tone="info">Unverified</Badge> : u.is_active ? <Badge tone="ok">Active</Badge> : <Badge>Deactivated</Badge>}{u.is_locked && <Badge tone="warn">Locked</Badge>}</td>
                <td className="text-right"><button className="btn-ghost btn-sm" onClick={() => toggle(u)}>{u.is_active ? "Deactivate" : "Reactivate"}</button></td>
              </tr>))}</tbody>
          </table></div>
          <Pagination page={p.page} count={data.count} onPage={(n) => setP({ ...p, page: n })} />
        </>)}
      </div>
    </>
  );
}

// ----------------------------------------------------------------------------------- reports
interface Report { report: string; title: string; columns: string[]; rows: (string | number)[][]; total_rows: number; truncated: boolean; summary: Record<string, unknown> }
const REPORTS = [["claims", "Claims"], ["fraud", "Fraud and risk"], ["policies", "Policies"], ["vehicles", "Vehicles"], ["customers", "Customers"]];

export function ReportsPage() {
  const toast = useToast();
  const [f, setF] = useState({ report: "claims", date_from: "", date_to: "", claim_type: "", claim_status: "", policy_status: "", risk_level: "" });
  const { data, loading, error, reload } = useApi<Report>(`/reports/${qs(f)}`);
  const [busy, setBusy] = useState("");
  const exp = async (format: string) => {
    setBusy(format);
    try { await downloadFile(`/reports/export/${qs({ ...f, format })}`, `${f.report}.${format}`); toast(`${format.toUpperCase()} export downloaded`); }
    catch (e) { toast(errorMessage(e), "error"); } finally { setBusy(""); }
  };
  const set = (k: keyof typeof f, v: string) => setF({ ...f, [k]: v });
  const summary = data?.summary ?? {};
  return (
    <>
      <PageHeader title="Reports" subtitle="Filter, review and export. Exports contain exactly the rows shown by the filters."
        actions={["csv", "xlsx", "pdf"].map((fmt) => <button key={fmt} className="btn-secondary" disabled={!!busy} onClick={() => exp(fmt)}><Download className="h-4 w-4" />{busy === fmt ? "Preparing…" : fmt === "xlsx" ? "Excel" : fmt.toUpperCase()}</button>)} />
      <div className="mb-4 flex flex-wrap gap-1 rounded-md border border-line bg-white p-1" role="tablist">
        {REPORTS.map(([k, l]) => <button key={k} role="tab" aria-selected={f.report === k} onClick={() => set("report", k)}
          className={`rounded px-3 py-1.5 text-sm ${f.report === k ? "bg-ink text-white" : "text-ink-500 hover:bg-paper"}`}>{l}</button>)}
      </div>
      <div className="panel mb-6 grid gap-3 p-4 sm:grid-cols-3 lg:grid-cols-6">
        <Field label="From"><Input type="date" value={f.date_from} onChange={(e) => set("date_from", e.target.value)} /></Field>
        <Field label="To"><Input type="date" value={f.date_to} onChange={(e) => set("date_to", e.target.value)} /></Field>
        <Field label="Claim type"><Select value={f.claim_type} onChange={(e) => set("claim_type", e.target.value)}><option value="">Any</option>{CLAIM_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}</Select></Field>
        <Field label="Claim status"><Select value={f.claim_status} onChange={(e) => set("claim_status", e.target.value)}><option value="">Any</option>{CLAIM_STATUSES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select></Field>
        <Field label="Policy status"><Select value={f.policy_status} onChange={(e) => set("policy_status", e.target.value)}><option value="">Any</option>{POLICY_STATUSES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select></Field>
        <Field label="Fraud risk"><Select value={f.risk_level} onChange={(e) => set("risk_level", e.target.value)}><option value="">Any</option><option value="LOW">Low</option><option value="MEDIUM">Medium</option><option value="HIGH">High</option></Select></Field>
      </div>
      {loading ? <Spinner /> : error ? <ErrorState message={error} onRetry={reload} /> : data && (<>
        <Panel title="Summary" className="mb-6">
          <dl className="grid gap-x-8 gap-y-4 sm:grid-cols-2 lg:grid-cols-3">
            {Object.entries(summary).map(([k, v]) => (
              <div key={k}>
                <dt className="text-sm text-ink-500">{k.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase())}</dt>
                <dd className="mt-0.5 text-sm font-medium">{Array.isArray(v)
                  ? (v as { label?: string; month?: string; value: number }[]).filter((x) => x.value).map((x) => `${x.label ?? x.month}: ${x.value}`).join(", ") || "None"
                  : typeof v === "number" && /amount|idv|premium|claims$/.test(k) && !/^total_claims$|assessed|flagged/.test(k) ? money(v) : String(v)}</dd>
              </div>
            ))}
          </dl>
        </Panel>
        <Panel title={`${data.title}: ${data.total_rows} row(s)${data.truncated ? ", first 500 shown — export for all" : ""}`} bodyClass="">
          {!data.rows.length ? <Empty title="No records match these filters" /> : (
            <div className="max-h-[560px] overflow-auto"><table className="table">
              <thead className="sticky top-0"><tr>{data.columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
              <tbody>{data.rows.map((r, i) => <tr key={i}>{r.map((cell, j) => <td key={j} className={typeof cell === "number" ? "text-right" : ""}>{typeof cell === "number" && data.columns[j].includes("₹") ? money(cell) : String(cell)}</td>)}</tr>)}</tbody>
            </table></div>
          )}
        </Panel>
      </>)}
    </>
  );
}

// ----------------------------------------------------------------------------------- audit log
interface Audit { id: number; actor_email: string; actor_role: string; action: string; action_display: string; entity_type: string; entity_id: string; description: string; metadata: Record<string, unknown>; ip_address: string | null; created_at: string }
export function AuditLogPage() {
  const [f, setF] = useState({ action: "", actor: "", entity_type: "", date_from: "", date_to: "", page: 1 });
  const { data, loading, error, reload } = useApi<Page<Audit>>(`/audit-logs/${qs(f)}`);
  const [open, setOpen] = useState<Audit | null>(null);
  const set = (k: keyof typeof f, v: string) => setF({ ...f, [k]: v, page: 1 });
  return (
    <>
      <PageHeader title="Audit log" subtitle="Append-only record of security and business events. Entries cannot be edited or deleted." />
      <div className="panel">
        <div className="grid gap-3 border-b border-line p-4 sm:grid-cols-5">
          <Input placeholder="Actor email" value={f.actor} onChange={(e) => set("actor", e.target.value)} aria-label="Actor" />
          <Select value={f.entity_type} onChange={(e) => set("entity_type", e.target.value)} aria-label="Entity"><option value="">Any entity</option>{["claim", "user", "policy", "vehicle", "claimdocument", "investigation", "appeal", "policyrequest", "report"].map((x) => <option key={x}>{x}</option>)}</Select>
          <Input placeholder="Action, e.g. CLAIM_APPROVED" value={f.action} onChange={(e) => set("action", e.target.value.toUpperCase())} aria-label="Action" />
          <Input type="date" value={f.date_from} onChange={(e) => set("date_from", e.target.value)} aria-label="From" />
          <Input type="date" value={f.date_to} onChange={(e) => set("date_to", e.target.value)} aria-label="To" />
        </div>
        {loading ? <Spinner /> : error ? <ErrorState message={error} onRetry={reload} /> : !data?.results.length ? <Empty title="No events match" /> : (<>
          <div className="overflow-x-auto"><table className="table">
            <thead><tr><th>When</th><th>Actor</th><th>Event</th><th>Entity</th><th>Details</th></tr></thead>
            <tbody>{data.results.map((a) => (
              <tr key={a.id} className="clickable" onClick={() => setOpen(a)}>
                <td className="whitespace-nowrap text-sm">{dateTime(a.created_at)}</td>
                <td className="text-sm">{a.actor_email || "System"}<div className="text-xs text-ink-500">{a.actor_role}</div></td>
                <td><Badge tone={/FAILED|LOCKED|REJECTED|CANCELLED|FLAGGED/.test(a.action) ? "bad" : /APPROVED|VERIFIED|CREATED/.test(a.action) ? "ok" : "neutral"}>{a.action_display}</Badge></td>
                <td className="text-sm">{a.entity_type} #{a.entity_id}</td>
                <td className="max-w-xs truncate text-xs text-ink-500">{a.description || JSON.stringify(a.metadata)}</td>
              </tr>))}</tbody>
          </table></div>
          <Pagination page={f.page} count={data.count} onPage={(n) => setF({ ...f, page: n })} />
        </>)}
      </div>
      <Modal open={!!open} title={open?.action_display ?? ""} onClose={() => setOpen(null)} wide>
        {open && <><dl className="dl"><dt>When</dt><dd>{dateTime(open.created_at)}</dd><dt>Actor</dt><dd>{open.actor_email || "System"} {open.actor_role && `(${open.actor_role})`}</dd>
          <dt>Entity</dt><dd>{open.entity_type} #{open.entity_id}</dd><dt>IP address</dt><dd>{open.ip_address ?? "—"}</dd></dl>
          <pre className="overflow-x-auto rounded bg-paper p-3 text-xs">{JSON.stringify(open.metadata, null, 2)}</pre></>}
      </Modal>
    </>
  );
}
