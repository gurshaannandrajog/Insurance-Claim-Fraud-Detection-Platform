import { Car, FilePlus2, FileText, ShieldPlus, Upload } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import type { ClaimListItem, Notification } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { ClaimStatusBadge, StatusRail } from "../../components/claim-parts";
import { Empty, ErrorState, Panel, Spinner } from "../../components/ui";
import { date, money, relative } from "../../lib/format";
import { useApi } from "../../lib/useApi";

interface Dash {
  policies: { total: number; active: number; by_status: Record<string, number> };
  vehicles: { total: number; insured: number };
  claims: { total: number; open: number; by_status: Record<string, number> };
  recent_claims: ClaimListItem[];
  notifications: Notification[];
  unread_notifications: number;
}

export default function CustomerDashboard() {
  const { user } = useAuth();
  const { data, loading, error, reload } = useApi<Dash>("/dashboard/");
  const navigate = useNavigate();
  if (loading) return <Spinner />;
  if (error || !data) return <ErrorState message={error ?? "Could not load your overview."} onRetry={reload} />;
  const open = data.recent_claims.filter((c) => !["APPROVED", "CLOSED", "PERMANENTLY_REJECTED"].includes(c.status));
  const firstName = user?.full_name.split(" ")[0];

  const actions = [
    { to: "/claims/new", label: "Submit a claim", icon: <FilePlus2 className="h-5 w-5" />, primary: true },
    { to: "/vehicles?add=1", label: "Add vehicle", icon: <Car className="h-5 w-5" /> },
    { to: "/policies?request=1", label: "Request a policy", icon: <ShieldPlus className="h-5 w-5" /> },
    { to: "/claims", label: "View claims", icon: <FileText className="h-5 w-5" /> },
    { to: open[0] ? `/claims/${open[0].id}#documents` : "/claims", label: "Upload documents", icon: <Upload className="h-5 w-5" /> },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1>Hello, {firstName}</h1>
        <p className="mt-1 text-sm text-ink-500">
          {data.policies.active} active {data.policies.active === 1 ? "policy" : "policies"} covering {data.vehicles.insured} of your {data.vehicles.total} vehicle(s)
          {data.claims.open ? `, ${data.claims.open} claim(s) in progress.` : ". No claims in progress."}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
        {actions.map((a) => (
          <Link key={a.label} to={a.to}
            className={`flex items-center gap-3 rounded-md border px-4 py-3 text-sm font-medium transition-colors ${a.primary ? "border-cover bg-cover text-white hover:bg-cover-dark" : "border-line bg-white hover:border-cover/50"}`}>
            {a.icon}{a.label}
          </Link>
        ))}
      </div>

      {open.length > 0 && (
        <Panel title="Claims in progress">
          <ul className="divide-y divide-line">
            {open.map((c) => (
              <li key={c.id} className="cursor-pointer py-4 first:pt-0 last:pb-0" onClick={() => navigate(`/claims/${c.id}`)}>
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <Link to={`/claims/${c.id}`} className="font-medium hover:underline">{c.claim_number}</Link>
                    <span className="ml-2 text-sm text-ink-500">{c.claim_type_display} on {c.vehicle_registration}, {date(c.incident_date)}</span>
                  </div>
                  <span className="text-sm font-medium">{money(c.requested_amount)}</span>
                </div>
                <StatusRail status={c.status} label={c.status_display} />
              </li>
            ))}
          </ul>
        </Panel>
      )}

      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <Panel title="Recent claims" actions={<Link to="/claims" className="text-sm text-cover hover:underline">All claims</Link>} bodyClass="">
          {data.recent_claims.length === 0 ? <Empty title="No claims yet" action={<Link to="/claims/new" className="btn-primary">Submit a claim</Link>}>When something happens to an insured vehicle, file the claim here.</Empty> : (
            <div className="overflow-x-auto"><table className="table">
              <thead><tr><th>Claim</th><th>Type</th><th>Requested</th><th>Approved</th><th>Status</th></tr></thead>
              <tbody>{data.recent_claims.map((c) => (
                <tr key={c.id} className="clickable" onClick={() => navigate(`/claims/${c.id}`)}>
                  <td className="font-medium">{c.claim_number}</td><td>{c.claim_type_display}</td>
                  <td>{money(c.requested_amount)}</td><td>{money(c.approved_amount)}</td>
                  <td><ClaimStatusBadge status={c.status} label={c.status_display} /></td>
                </tr>))}
              </tbody>
            </table></div>
          )}
        </Panel>
        <Panel title="Latest updates" actions={<Link to="/notifications" className="text-sm text-cover hover:underline">{data.unread_notifications} unread</Link>}>
          {data.notifications.length === 0 ? <p className="text-sm text-ink-500">No notifications yet.</p> : (
            <ul className="space-y-4">{data.notifications.map((n) => (
              <li key={n.id} className="flex gap-3">
                <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${n.is_read ? "bg-line" : "bg-cover"}`} />
                <div className="min-w-0">
                  {n.link ? <Link to={n.link} className="text-sm font-medium hover:underline">{n.title}</Link> : <p className="text-sm font-medium">{n.title}</p>}
                  <p className="line-clamp-2 text-xs text-ink-500">{n.message}</p>
                  <p className="text-[11px] text-ink-300">{relative(n.created_at)}</p>
                </div>
              </li>))}
            </ul>
          )}
        </Panel>
      </div>
    </div>
  );
}
