import { Plus } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, errorMessage, type Page } from "../../api/client";
import type { Plan, Policy, PolicyRequest, Vehicle } from "../../api/types";
import { useToast } from "../../components/Toast";
import { Badge, Banner, ConfirmDialog, Empty, ErrorState, Field, Input, Modal, PageHeader, Panel, Select, Spinner, Textarea } from "../../components/ui";
import { date, money } from "../../lib/format";
import { POLICY_STATUS_TONE, REQUEST_TONE } from "../../lib/labels";
import { useApi } from "../../lib/useApi";

function RequestPolicyModal({ vehicles, plans, preselect, onClose, onDone }:
  { vehicles: Vehicle[]; plans: Plan[]; preselect?: string; onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const eligible = vehicles.filter((v) => !v.current_policy);
  const [vehicleId, setVehicleId] = useState(preselect && eligible.some((v) => String(v.id) === preselect) ? preselect : "");
  const [planId, setPlanId] = useState("");
  const [idv, setIdv] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const plan = plans.find((p) => String(p.id) === planId);
  const premium = plan && Number(idv) > 0 ? (Number(idv) * Number(plan.premium_rate_percent) / 100) * plan.term_months / 12 : null;

  const submit = async () => {
    if (!vehicleId || !planId || !idv) return setError("Choose a vehicle, a plan and the insured declared value.");
    if (plan && (Number(idv) < Number(plan.min_idv) || Number(idv) > Number(plan.max_idv)))
      return setError(`IDV for this plan must be between ${money(plan.min_idv)} and ${money(plan.max_idv)}.`);
    setBusy(true); setError("");
    try {
      await api.post("/policy-requests/", { vehicle_id: Number(vehicleId), plan_id: Number(planId), requested_idv: idv, notes });
      toast("Policy request sent for review");
      onDone();
    } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  };

  return (
    <Modal open title="Request a policy" onClose={onClose}
      footer={<><button className="btn-secondary" onClick={onClose}>Cancel</button><button className="btn-primary" disabled={busy || !eligible.length} onClick={submit}>Send request</button></>}>
      {error && <Banner tone="bad">{error}</Banner>}
      {!eligible.length ? <Banner tone="warn">All your vehicles already have a live policy. <Link to="/vehicles?add=1" className="underline">Add a vehicle</Link> first.</Banner> : <>
        <Field label="Vehicle" required hint="A vehicle can have only one live policy at a time.">
          <Select value={vehicleId} onChange={(e) => setVehicleId(e.target.value)}>
            <option value="">Select a vehicle…</option>
            {eligible.map((v) => <option key={v.id} value={v.id}>{v.registration_number}, {v.make} {v.model}</option>)}
          </Select>
        </Field>
        <Field label="Plan" required>
          <Select value={planId} onChange={(e) => setPlanId(e.target.value)}>
            <option value="">Select a plan…</option>
            {plans.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.premium_rate_percent}% of IDV per year)</option>)}
          </Select>
          {plan && <p className="hint">{plan.description}</p>}
        </Field>
        <Field label="Insured declared value (IDV, ₹)" required hint={plan ? `Between ${money(plan.min_idv)} and ${money(plan.max_idv)}.` : "The current market value of the vehicle."}>
          <Input type="number" min={1} value={idv} onChange={(e) => setIdv(e.target.value)} />
        </Field>
        {premium !== null && <p className="rounded bg-cover-light px-3 py-2 text-sm text-cover-dark">Estimated premium: <strong>{money(premium)}</strong> for {plan?.term_months} months. Final terms are set when the administrator approves.</p>}
        <Field label="Notes for the underwriter"><Textarea value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={500} /></Field>
      </>}
    </Modal>
  );
}

export default function PoliciesPage() {
  const toast = useToast();
  const policies = useApi<Page<Policy>>("/policies/?page_size=100");
  const requests = useApi<Page<PolicyRequest>>("/policy-requests/?page_size=100");
  const vehicles = useApi<Page<Vehicle>>("/vehicles/?page_size=100");
  const plans = useApi<Plan[]>("/policy-plans/");
  const [params, setParams] = useSearchParams();
  const [open, setOpen] = useState(false);
  const [withdraw, setWithdraw] = useState<PolicyRequest | null>(null);
  const preselect = useMemo(() => params.get("vehicle") ?? undefined, [params]);

  useEffect(() => { if (params.get("request") === "1") setOpen(true); }, [params]);

  if (policies.loading || requests.loading) return <Spinner />;
  if (policies.error) return <ErrorState message={policies.error} onRetry={policies.reload} />;

  const doWithdraw = async () => {
    if (!withdraw) return;
    try { await api.post(`/policy-requests/${withdraw.id}/withdraw/`); toast("Request withdrawn"); requests.reload(); }
    catch (e) { toast(errorMessage(e), "error"); } finally { setWithdraw(null); }
  };

  const pending = requests.data?.results.filter((r) => r.status !== "APPROVED") ?? [];

  return (
    <>
      <PageHeader title="Policies" subtitle="Your insurance policies and the requests you've made."
        actions={<button className="btn-primary" onClick={() => setOpen(true)}><Plus className="h-4 w-4" />Request a policy</button>} />
      <div className="space-y-6">
        {!policies.data?.results.length ? (
          <div className="panel"><Empty title="No policies yet" action={<button className="btn-primary" onClick={() => setOpen(true)}>Request a policy</button>}>Register a vehicle, then request a policy for it. An administrator reviews every request.</Empty></div>
        ) : (
          <div className="grid gap-4 lg:grid-cols-2">
            {policies.data.results.map((p) => {
              const used = Number(p.cumulative_approved_amount) / Number(p.idv);
              return (
                <article key={p.id} className="panel p-5">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-sm text-ink-500">{p.plan_name}</p>
                      <h2>{p.policy_number}</h2>
                      <p className="text-sm text-ink-500">{p.vehicle.registration_number}, {p.vehicle.make} {p.vehicle.model}</p>
                    </div>
                    <Badge tone={POLICY_STATUS_TONE[p.status]}>{p.status_display}</Badge>
                  </div>
                  <div className="mt-4">
                    <div className="flex justify-between text-xs text-ink-500"><span>Claims paid {money(p.cumulative_approved_amount)}</span><span>IDV {money(p.idv)}</span></div>
                    <div className="mt-1 h-2 overflow-hidden rounded-full bg-paper"><div className={`h-full ${used >= 1 ? "bg-warn" : "bg-cover"}`} style={{ width: `${Math.min(100, used * 100)}%` }} /></div>
                  </div>
                  <dl className="dl mt-4">
                    <dt>Period</dt><dd>{date(p.start_date)} to {date(p.end_date)}</dd>
                    <dt>Premium</dt><dd>{money(p.premium_amount)}</dd>
                    <dt>Remaining cover</dt><dd>{money(p.remaining_idv)}</dd>
                    <dt>Claims filed</dt><dd>{p.claim_count}</dd>
                    {p.cancellation_reason && <><dt>Cancellation</dt><dd>{p.cancellation_reason}</dd></>}
                  </dl>
                  {p.is_claimable && <div className="mt-4 border-t border-line pt-4"><Link to={`/claims/new?policy=${p.id}`} className="btn-secondary btn-sm">File a claim on this policy</Link></div>}
                </article>
              );
            })}
          </div>
        )}

        <Panel title="Policy requests" bodyClass="">
          {!pending.length ? <p className="px-5 py-6 text-sm text-ink-500">No open or declined requests.</p> : (
            <div className="overflow-x-auto"><table className="table">
              <thead><tr><th>Vehicle</th><th>Plan</th><th>IDV</th><th>Requested</th><th>Status</th><th /></tr></thead>
              <tbody>{pending.map((r) => (
                <tr key={r.id}>
                  <td className="font-medium">{r.vehicle.registration_number}</td><td>{r.plan.name}</td><td>{money(r.requested_idv)}</td><td>{date(r.created_at)}</td>
                  <td><Badge tone={REQUEST_TONE[r.status]}>{r.status_display}</Badge>{r.decision_note && <p className="mt-1 text-xs text-ink-500">{r.decision_note}</p>}</td>
                  <td className="text-right">{r.status === "PENDING" && <button className="btn-ghost btn-sm" onClick={() => setWithdraw(r)}>Withdraw</button>}</td>
                </tr>))}
              </tbody>
            </table></div>
          )}
        </Panel>
      </div>
      {open && vehicles.data && plans.data && (
        <RequestPolicyModal vehicles={vehicles.data.results} plans={plans.data} preselect={preselect}
          onClose={() => { setOpen(false); setParams({}, { replace: true }); }}
          onDone={() => { setOpen(false); setParams({}, { replace: true }); requests.reload(); }} />
      )}
      <ConfirmDialog open={!!withdraw} title="Withdraw policy request?" message={`The request for ${withdraw?.vehicle.registration_number} will be cancelled.`}
        confirmLabel="Withdraw request" danger onConfirm={doWithdraw} onClose={() => setWithdraw(null)} />
    </>
  );
}
