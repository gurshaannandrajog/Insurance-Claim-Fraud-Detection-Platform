import { Search } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Page } from "../../api/client";
import type { Appeal, Bucket, ClaimListItem, Investigation } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { ClaimStatusBadge, RiskBadge } from "../../components/claim-parts";
import { Badge, Empty, ErrorState, Input, PageHeader, Pagination, Panel, Select, Spinner, Stat } from "../../components/ui";
import { date, money, relative } from "../../lib/format";
import { CLAIM_STATUSES, CLAIM_TYPES, INVESTIGATION_TONE } from "../../lib/labels";
import { qs, useApi } from "../../lib/useApi";

export function ClaimTable({ claims, showRisk = true }: { claims: ClaimListItem[]; showRisk?: boolean }) {
  const navigate = useNavigate();
  return (
    <div className="overflow-x-auto"><table className="table">
      <thead><tr><th>Claim</th><th>Customer</th><th>Type</th><th className="text-right">Requested</th>{showRisk && <th>Risk</th>}<th>Status</th><th>Adjuster</th></tr></thead>
      <tbody>{claims.map((c) => (
        <tr key={c.id} className="clickable" onClick={() => navigate(`/staff/claims/${c.id}`)}>
          <td><Link to={`/staff/claims/${c.id}`} className="font-medium hover:underline" onClick={(e) => e.stopPropagation()}>{c.claim_number}</Link>
            <div className="text-xs text-ink-500">{c.vehicle_registration}, submitted {relative(c.submitted_at)}</div></td>
          <td>{c.customer_name}</td><td>{c.claim_type_display}</td><td className="text-right">{money(c.requested_amount)}</td>
          {showRisk && <td><RiskBadge level={c.current_risk_level} score={c.current_risk_score} /></td>}
          <td><ClaimStatusBadge status={c.status} label={c.status_display} /></td>
          <td className="text-sm text-ink-500">{c.assigned_adjuster_name ?? "Unassigned"}</td>
        </tr>))}
      </tbody>
    </table></div>
  );
}

export function ClaimsQueuePage() {
  const { user } = useAuth();
  const [f, setF] = useState({ search: "", status: "", claim_type: "", risk_level: "", assigned: "", date_from: "", date_to: "", page: 1 });
  const [search, setSearch] = useState("");
  const { data, loading, error, reload } = useApi<Page<ClaimListItem>>(`/claims/${qs({ ...f, ordering: "-submitted_at" })}`);
  const set = (k: keyof typeof f, v: string) => setF({ ...f, [k]: v, page: 1 });
  const title = user?.role === "SIU" ? "Flagged claims" : user?.role === "ADMIN" ? "Claims oversight" : "All claims";
  return (
    <>
      <PageHeader title={title} subtitle={user?.role === "SIU" ? "Claims that were sent to the Special Investigation Unit." : "Search and filter every claim on the platform."} />
      <div className="panel">
        <form className="grid gap-3 border-b border-line p-4 md:grid-cols-[1.5fr_repeat(4,1fr)]" onSubmit={(e) => { e.preventDefault(); set("search", search); }}>
          <div className="relative"><Search className="absolute left-3 top-2.5 h-4 w-4 text-ink-300" />
            <Input className="pl-9" placeholder="Claim no., vehicle, policy or customer" value={search} onChange={(e) => setSearch(e.target.value)} onBlur={() => set("search", search)} aria-label="Search" /></div>
          <Select value={f.status} onChange={(e) => set("status", e.target.value)} aria-label="Status"><option value="">All statuses</option>{CLAIM_STATUSES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select>
          <Select value={f.claim_type} onChange={(e) => set("claim_type", e.target.value)} aria-label="Type"><option value="">All types</option>{CLAIM_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}</Select>
          <Select value={f.risk_level} onChange={(e) => set("risk_level", e.target.value)} aria-label="Risk"><option value="">Any risk</option><option value="HIGH">High risk</option><option value="MEDIUM">Medium risk</option><option value="LOW">Low risk</option></Select>
          {user?.role === "ADJUSTER" ? (
            <Select value={f.assigned} onChange={(e) => set("assigned", e.target.value)} aria-label="Assignment"><option value="">Anyone</option><option value="me">Assigned to me</option><option value="none">Unassigned</option></Select>
          ) : <div />}
          <div className="flex items-center gap-2 md:col-span-2"><span className="text-sm text-ink-500">From</span><Input type="date" value={f.date_from} onChange={(e) => set("date_from", e.target.value)} /><span className="text-sm text-ink-500">to</span><Input type="date" value={f.date_to} onChange={(e) => set("date_to", e.target.value)} /></div>
        </form>
        {loading ? <Spinner /> : error ? <ErrorState message={error} onRetry={reload} /> : !data?.results.length ? <Empty title="No claims match these filters" /> : (<>
          <ClaimTable claims={data.results} />
          <Pagination page={f.page} count={data.count} onPage={(p) => setF({ ...f, page: p })} />
        </>)}
      </div>
    </>
  );
}

interface AdjDash {
  counts: Record<string, number>;
  awaiting_review: ClaimListItem[]; my_queue: ClaimListItem[]; documents_pending: ClaimListItem[];
  fraud_review: ClaimListItem[]; pending_appeals: ClaimListItem[]; recently_approved: ClaimListItem[]; recently_rejected: ClaimListItem[];
}

function QueuePanel({ title, claims, empty, link }: { title: string; claims: ClaimListItem[]; empty: string; link?: string }) {
  return (
    <Panel title={<>{title} <span className="ml-1 text-sm font-normal text-ink-500">{claims.length}</span></>} bodyClass=""
      actions={link && <Link to={link} className="text-sm text-cover hover:underline">See all</Link>}>
      {claims.length === 0 ? <p className="px-5 py-6 text-sm text-ink-500">{empty}</p> : <ClaimTable claims={claims} />}
    </Panel>
  );
}

export function AdjusterDashboard() {
  const { data, loading, error, reload } = useApi<AdjDash>("/dashboard/");
  if (loading) return <Spinner />;
  if (error || !data) return <ErrorState message={error ?? "Could not load the queue."} onRetry={reload} />;
  const k = data.counts;
  return (
    <div className="space-y-6">
      <PageHeader title="Work queue" subtitle="Claims waiting on you, oldest first." actions={<Link to="/staff/claims" className="btn-secondary">Search all claims</Link>} />
      <div className="panel grid grid-cols-2 divide-x divide-y divide-line sm:grid-cols-3 lg:grid-cols-6 lg:divide-y-0">
        <Stat label="Awaiting review" value={k.awaiting_review} />
        <Stat label="My open reviews" value={k.my_under_review} />
        <Stat label="Documents pending" value={k.documents_pending} tone={k.documents_pending ? "warn" : undefined} />
        <Stat label="In fraud review" value={k.fraud_review} tone={k.fraud_review ? "bad" : undefined} />
        <Stat label="Pending appeals" value={k.pending_appeals} />
        <Stat label="Open high-risk" value={k.high_risk_open} tone={k.high_risk_open ? "bad" : undefined} />
      </div>
      <QueuePanel title="Awaiting review" claims={data.awaiting_review} empty="Nothing waiting. New claims appear here." link="/staff/claims" />
      <QueuePanel title="My open reviews" claims={data.my_queue} empty="You have no claims under review." />
      <div className="grid gap-6 xl:grid-cols-2">
        <QueuePanel title="Documents pending" claims={data.documents_pending} empty="No claims are waiting for documents." />
        <QueuePanel title="Pending appeals" claims={data.pending_appeals} empty="No appeals to decide." link="/staff/appeals" />
      </div>
      <QueuePanel title="With the SIU (fraud review)" claims={data.fraud_review} empty="No claims are under investigation." />
      <div className="grid gap-6 xl:grid-cols-2">
        <QueuePanel title="Recently approved" claims={data.recently_approved} empty="None yet." />
        <QueuePanel title="Recently rejected" claims={data.recently_rejected} empty="None yet." />
      </div>
    </div>
  );
}

export function AppealsPage() {
  const [status, setStatus] = useState("PENDING");
  const { data, loading, error, reload } = useApi<Page<Appeal>>(`/appeals/${qs({ status })}`);
  const navigate = useNavigate();
  return (
    <>
      <PageHeader title="Appeals" subtitle="Customer appeals against rejected claims." />
      <div className="panel">
        <div className="border-b border-line p-4"><Select className="w-auto" value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status">
          <option value="PENDING">Pending review</option><option value="ACCEPTED">Accepted</option><option value="DECLINED">Declined</option><option value="">All</option></Select></div>
        {loading ? <Spinner /> : error ? <ErrorState message={error} onRetry={reload} /> : !data?.results.length ? <Empty title="No appeals here" /> : (
          <div className="overflow-x-auto"><table className="table">
            <thead><tr><th>Claim</th><th>Appeal</th><th>Grounds</th><th>Filed</th><th>Status</th></tr></thead>
            <tbody>{data.results.map((a) => (
              <tr key={a.id} className="clickable" onClick={() => navigate(`/staff/claims/${a.claim_id}`)}>
                <td className="font-medium">{a.claim_number}</td><td>#{a.sequence}</td><td className="max-w-md truncate">{a.reason}</td><td>{date(a.created_at)}</td>
                <td><Badge tone={a.status === "ACCEPTED" ? "ok" : a.status === "DECLINED" ? "bad" : "warn"}>{a.status_display}</Badge></td>
              </tr>))}</tbody>
          </table></div>
        )}
      </div>
    </>
  );
}

interface SiuDash {
  counts: Record<string, number>;
  queue: Investigation[]; recently_completed: Investigation[];
  risk_distribution: Bucket[]; recommendations: { recommendation: string; value: number }[];
}

const RISK_COLORS: Record<string, string> = { LOW: "#2F7D4F", MEDIUM: "#C08A2B", HIGH: "#B42318" };

export function SiuDashboard() {
  const { data, loading, error, reload } = useApi<SiuDash>("/dashboard/");
  const navigate = useNavigate();
  if (loading) return <Spinner />;
  if (error || !data) return <ErrorState message={error ?? "Could not load investigations."} onRetry={reload} />;
  const k = data.counts;
  const InvTable = ({ items }: { items: Investigation[] }) => (
    <div className="overflow-x-auto"><table className="table">
      <thead><tr><th>Claim</th><th>Risk</th><th>Why it was flagged</th><th>Requested</th><th>Status</th><th>Opened</th></tr></thead>
      <tbody>{items.map((i) => (
        <tr key={i.id} className="clickable" onClick={() => navigate(`/staff/claims/${i.claim_id}`)}>
          <td><span className="font-medium">{i.claim_number}</span><div className="text-xs text-ink-500">{i.customer_name}</div></td>
          <td><RiskBadge level={i.risk_level} score={i.risk_score} /></td>
          <td className="max-w-sm"><div className="text-xs text-ink-500">{i.trigger_display}</div>
            <ul className="text-sm">{(i.top_factors.length ? i.top_factors : [i.trigger_reason]).slice(0, 2).map((f) => <li key={f} className="truncate">{f}</li>)}</ul></td>
          <td>{money(i.requested_amount)}</td>
          <td><Badge tone={INVESTIGATION_TONE[i.status]}>{i.status_display}</Badge>{i.investigator_name && <div className="text-xs text-ink-500">{i.investigator_name}</div>}</td>
          <td className="text-sm text-ink-500">{relative(i.created_at)}</td>
        </tr>))}</tbody>
    </table></div>
  );
  return (
    <div className="space-y-6">
      <PageHeader title="Investigations" subtitle="Claims flagged by the fraud engine or escalated by adjusters." />
      <div className="panel grid grid-cols-2 divide-x divide-y divide-line sm:grid-cols-3 lg:grid-cols-6 lg:divide-y-0">
        <Stat label="Open, unassigned" value={k.open} tone={k.open ? "warn" : undefined} />
        <Stat label="In progress" value={k.in_progress} />
        <Stat label="Assigned to me" value={k.mine} />
        <Stat label="Completed" value={k.completed} tone="ok" />
        <Stat label="Claims in fraud review" value={k.fraud_review_claims} tone={k.fraud_review_claims ? "bad" : undefined} />
        <Stat label="High-risk claims" value={k.high_risk_claims} />
      </div>
      <Panel title="Investigation queue" bodyClass="">
        {data.queue.length === 0 ? <Empty title="No open investigations">Flagged claims appear here automatically.</Empty> : <InvTable items={data.queue} />}
      </Panel>
      <div className="grid gap-6 lg:grid-cols-[1fr_1.4fr]">
        <Panel title="Risk level of investigated claims">
          <div className="h-56"><ResponsiveContainer><BarChart data={data.risk_distribution} margin={{ left: -20 }}>
            <CartesianGrid vertical={false} stroke="#E3E7EF" /><XAxis dataKey="label" tick={{ fontSize: 12 }} /><YAxis allowDecimals={false} tick={{ fontSize: 12 }} /><Tooltip />
            <Bar dataKey="value" name="Claims" radius={[4, 4, 0, 0]}>{data.risk_distribution.map((b) => <Cell key={b.key} fill={RISK_COLORS[b.key ?? "LOW"]} />)}</Bar>
          </BarChart></ResponsiveContainer></div>
        </Panel>
        <Panel title="Recently completed" bodyClass="">
          {data.recently_completed.length === 0 ? <p className="px-5 py-6 text-sm text-ink-500">None yet.</p> : <InvTable items={data.recently_completed} />}
        </Panel>
      </div>
    </div>
  );
}
