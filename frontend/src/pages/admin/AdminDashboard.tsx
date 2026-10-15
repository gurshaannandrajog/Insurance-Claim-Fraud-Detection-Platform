import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Bucket } from "../../api/types";
import { ErrorState, PageHeader, Panel, Spinner, Stat } from "../../components/ui";
import { compactMoney, money } from "../../lib/format";
import { useApi } from "../../lib/useApi";

interface AdminDash {
  kpis: Record<string, number>;
  charts: {
    claims_by_status: Bucket[]; claims_by_type: Bucket[]; policy_status: Bucket[]; risk_distribution: Bucket[];
    claim_amount_trend: { month: string; requested: number; approved: number }[];
    claims_trend: { month: string; value: number }[]; customer_registrations: { month: string; value: number }[];
    vehicles_by_type: Bucket[]; vehicles_by_make: Bucket[];
  };
}

const STATUS_COLORS: Record<string, string> = {
  SUBMITTED: "#2457A6", UNDER_REVIEW: "#0E7C7B", DOCUMENTS_PENDING: "#C08A2B", FRAUD_REVIEW: "#D9480F",
  APPROVED: "#2F7D4F", REJECTED: "#B42318", CLOSED: "#8B95AB", PERMANENTLY_REJECTED: "#7A1A12",
  ACTIVE: "#2F7D4F", PARTIALLY_CLAIMED: "#0E7C7B", CLAIMED: "#C08A2B", EXPIRED: "#8B95AB", CANCELLED: "#B42318",
  LOW: "#2F7D4F", MEDIUM: "#C08A2B", HIGH: "#B42318",
};
const SERIES = ["#14213D", "#0E7C7B", "#C08A2B", "#2457A6", "#8B95AB", "#B42318", "#2F7D4F", "#5B4B8A"];
const month = (m: unknown) => new Date(`${String(m)}-01T00:00:00`).toLocaleDateString("en-IN", { month: "short" });
const axis = { tick: { fontSize: 12, fill: "#3B4A6B" }, axisLine: false, tickLine: false };

function Donut({ data }: { data: Bucket[] }) {
  const items = data.filter((d) => d.value > 0);
  if (!items.length) return <p className="py-16 text-center text-sm text-ink-500">No data yet.</p>;
  return (
    <div className="flex flex-col items-center gap-4 sm:flex-row">
      <div className="h-44 w-44 shrink-0"><ResponsiveContainer><PieChart>
        <Pie data={items} dataKey="value" nameKey="label" innerRadius={48} outerRadius={78} paddingAngle={2} stroke="none">
          {items.map((d, i) => <Cell key={d.label} fill={STATUS_COLORS[d.key ?? ""] ?? SERIES[i % SERIES.length]} />)}
        </Pie><Tooltip /></PieChart></ResponsiveContainer></div>
      <ul className="w-full space-y-1.5 text-sm">{items.map((d, i) => (
        <li key={d.label} className="flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: STATUS_COLORS[d.key ?? ""] ?? SERIES[i % SERIES.length] }} />
          <span className="flex-1 text-ink-700">{d.label}</span><span className="font-medium">{d.value}</span></li>))}</ul>
    </div>
  );
}

export default function AdminDashboard() {
  const { data, loading, error, reload } = useApi<AdminDash>("/dashboard/");
  if (loading) return <Spinner />;
  if (error || !data) return <ErrorState message={error ?? "Could not load analytics."} onRetry={reload} />;
  const k = data.kpis, c = data.charts;
  const approvalRate = k.approved_claims + k.rejected_claims ? Math.round((k.approved_claims / (k.approved_claims + k.rejected_claims)) * 100) : 0;
  return (
    <div className="space-y-6">
      <PageHeader title="Analytics" subtitle="Live figures from the claims database."
        actions={<><Link to="/admin/policy-requests" className="btn-secondary">{k.pending_policy_requests} policy request(s) to review</Link><Link to="/admin/reports" className="btn-primary">Reports and export</Link></>} />

      <section className="panel overflow-hidden">
        <div className="grid lg:grid-cols-[1.1fr_2fr]">
          <div className="border-b border-line bg-ink p-6 text-white lg:border-b-0">
            <p className="text-sm text-ink-100/80">Claims paid out</p>
            <p className="mt-1 text-4xl font-semibold tracking-tight">{money(k.total_approved_amount)}</p>
            <p className="mt-2 text-sm text-ink-100/80">of {money(k.total_requested_amount)} requested across {k.total_claims} claims. Average approved claim {money(k.average_approved_amount)}.</p>
            <div className="mt-5 h-2 overflow-hidden rounded-full bg-white/15"><div className="h-full bg-cover" style={{ width: `${k.total_requested_amount ? (k.total_approved_amount / k.total_requested_amount) * 100 : 0}%` }} /></div>
          </div>
          <div className="grid grid-cols-2 divide-x divide-y divide-line sm:grid-cols-3">
            <Stat label="Customers" value={k.total_customers} />
            <Stat label="Vehicles" value={k.total_vehicles} />
            <Stat label="Active policies" value={k.active_policies} />
            <Stat label="Claims in progress" value={k.pending_claims} />
            <Stat label="Approved / rejected" value={`${k.approved_claims} / ${k.rejected_claims}`} note={`${approvalRate}% approval rate`} />
            <Stat label="Fraud review / high risk" value={`${k.fraud_review_claims} / ${k.high_risk_claims}`} tone={k.fraud_review_claims ? "bad" : undefined} />
          </div>
        </div>
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Requested vs approved amounts, last 12 months">
          <div className="h-64"><ResponsiveContainer><BarChart data={c.claim_amount_trend} margin={{ left: 0, right: 8 }}>
            <CartesianGrid vertical={false} stroke="#E3E7EF" /><XAxis dataKey="month" tickFormatter={month} {...axis} />
            <YAxis tickFormatter={(v) => compactMoney(v)} width={70} {...axis} /><Tooltip formatter={(v) => money(Number(v))} labelFormatter={month} /><Legend />
            <Bar dataKey="requested" name="Requested" fill="#14213D" radius={[3, 3, 0, 0]} />
            <Bar dataKey="approved" name="Approved" fill="#0E7C7B" radius={[3, 3, 0, 0]} />
          </BarChart></ResponsiveContainer></div>
        </Panel>
        <Panel title="Claims by status"><Donut data={c.claims_by_status} /></Panel>
        <Panel title="Claims by type">
          <div className="h-56"><ResponsiveContainer><BarChart data={c.claims_by_type} layout="vertical" margin={{ left: 30 }}>
            <XAxis type="number" allowDecimals={false} {...axis} /><YAxis type="category" dataKey="label" width={120} {...axis} /><Tooltip />
            <Bar dataKey="value" name="Claims" fill="#0E7C7B" radius={[0, 4, 4, 0]} barSize={22} /></BarChart></ResponsiveContainer></div>
        </Panel>
        <Panel title="Fraud risk of assessed claims"><Donut data={c.risk_distribution} /></Panel>
        <Panel title="Policy status"><Donut data={c.policy_status} /></Panel>
        <Panel title="New customers and claims per month">
          <div className="h-56"><ResponsiveContainer><LineChart data={c.customer_registrations.map((r, i) => ({ month: r.month, customers: r.value, claims: c.claims_trend[i]?.value ?? 0 }))}>
            <CartesianGrid vertical={false} stroke="#E3E7EF" /><XAxis dataKey="month" tickFormatter={month} {...axis} /><YAxis allowDecimals={false} {...axis} width={30} />
            <Tooltip labelFormatter={month} /><Legend />
            <Line type="monotone" dataKey="customers" name="New customers" stroke="#14213D" strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="claims" name="Claims submitted" stroke="#C08A2B" strokeWidth={2} dot={false} />
          </LineChart></ResponsiveContainer></div>
        </Panel>
        <Panel title="Vehicles by make">
          <div className="h-56"><ResponsiveContainer><BarChart data={c.vehicles_by_make}>
            <CartesianGrid vertical={false} stroke="#E3E7EF" /><XAxis dataKey="label" {...axis} interval={0} tick={{ fontSize: 11 }} /><YAxis allowDecimals={false} width={30} {...axis} /><Tooltip />
            <Bar dataKey="value" name="Vehicles" fill="#14213D" radius={[4, 4, 0, 0]} barSize={28} /></BarChart></ResponsiveContainer></div>
        </Panel>
        <Panel title="Vehicles by type"><Donut data={c.vehicles_by_type} /></Panel>
      </div>
    </div>
  );
}
