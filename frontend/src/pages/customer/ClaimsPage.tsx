import { Plus } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import type { Page } from "../../api/client";
import type { ClaimListItem } from "../../api/types";
import { ClaimStatusBadge } from "../../components/claim-parts";
import { Empty, ErrorState, PageHeader, Pagination, Select, Spinner } from "../../components/ui";
import { date, money } from "../../lib/format";
import { CLAIM_TYPES } from "../../lib/labels";
import { qs, useApi } from "../../lib/useApi";

export default function ClaimsPage() {
  const [page, setPage] = useState(1);
  const [type, setType] = useState("");
  const { data, loading, error, reload } = useApi<Page<ClaimListItem>>(`/claims/${qs({ page, claim_type: type })}`);
  const navigate = useNavigate();
  return (
    <>
      <PageHeader title="My claims" subtitle="Track every claim from submission to settlement."
        actions={<Link to="/claims/new" className="btn-primary"><Plus className="h-4 w-4" />Submit a claim</Link>} />
      <div className="panel">
        <div className="flex flex-wrap gap-3 border-b border-line px-4 py-3">
          <Select className="w-auto" value={type} onChange={(e) => { setType(e.target.value); setPage(1); }} aria-label="Claim type">
            <option value="">All claim types</option>{CLAIM_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
          </Select>
        </div>
        {loading ? <Spinner /> : error ? <ErrorState message={error} onRetry={reload} /> : !data?.results.length ? (
          <Empty title="No claims found" action={<Link to="/claims/new" className="btn-primary">Submit a claim</Link>}>Claims you submit appear here with their current status.</Empty>
        ) : (<>
          <div className="overflow-x-auto"><table className="table">
            <thead><tr><th>Claim</th><th>Vehicle</th><th>Type</th><th>Incident</th><th className="text-right">Requested</th><th className="text-right">Approved</th><th>Status</th></tr></thead>
            <tbody>{data.results.map((c) => (
              <tr key={c.id} className="clickable" onClick={() => navigate(`/claims/${c.id}`)}>
                <td><Link to={`/claims/${c.id}`} className="font-medium hover:underline" onClick={(e) => e.stopPropagation()}>{c.claim_number}</Link><div className="text-xs text-ink-500">Submitted {date(c.submitted_at)}</div></td>
                <td>{c.vehicle_registration}</td><td>{c.claim_type_display}</td><td>{date(c.incident_date)}</td>
                <td className="text-right">{money(c.requested_amount)}</td><td className="text-right">{money(c.approved_amount)}</td>
                <td><ClaimStatusBadge status={c.status} label={c.status_display} /></td>
              </tr>))}
            </tbody>
          </table></div>
          <Pagination page={page} count={data.count} onPage={setPage} />
        </>)}
      </div>
    </>
  );
}
