import { Lock, Pencil, Plus } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ApiError, api, errorMessage, type Page } from "../../api/client";
import type { Vehicle } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { useToast } from "../../components/Toast";
import { Badge, Banner, Empty, ErrorState, Field, Input, Modal, PageHeader, Select, Spinner } from "../../components/ui";
import { date, todayISO } from "../../lib/format";
import { POLICY_STATUS_TONE, VEHICLE_TYPES } from "../../lib/labels";
import { useApi } from "../../lib/useApi";

const EMPTY = { registration_number: "", make: "", model: "", vehicle_type: "CAR", manufacturing_year: "", registration_date: "",
  purchase_date: "", engine_number: "", chassis_number: "", color: "", owner_name: "", owner_phone: "", owner_address: "" };
type Form = typeof EMPTY;

function VehicleForm({ initial, editing, onClose, onSaved }: { initial: Form; editing?: Vehicle; onClose: () => void; onSaved: () => void }) {
  const toast = useToast();
  const [v, setV] = useState<Form>(initial);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const bind = (k: keyof Form) => ({ id: k, value: v[k], invalid: !!errors[k], onChange: (e: { target: { value: string } }) => { setV({ ...v, [k]: e.target.value }); setErrors({ ...errors, [k]: "" }); } });

  const submit = async (e?: FormEvent) => {
    e?.preventDefault();
    const errs: Record<string, string> = {};
    (["registration_number", "make", "model", "manufacturing_year", "registration_date", "purchase_date", "engine_number", "chassis_number", "color", "owner_name"] as const)
      .forEach((k) => { if (!String(v[k]).trim()) errs[k] = "Required"; });
    const year = Number(v.manufacturing_year);
    if (v.manufacturing_year && (year < 1950 || year > new Date().getFullYear())) errs.manufacturing_year = `Between 1950 and ${new Date().getFullYear()}.`;
    if (v.registration_number && !/^[A-Za-z0-9 -]{4,15}$/.test(v.registration_number)) errs.registration_number = "Letters and digits only, e.g. MH02AB1234.";
    setErrors(errs);
    if (Object.keys(errs).length) return;
    setBusy(true); setError("");
    try {
      const body = { ...v, manufacturing_year: year };
      if (editing) await api.patch(`/vehicles/${editing.id}/`, body); else await api.post("/vehicles/", body);
      toast(editing ? "Vehicle updated" : "Vehicle added");
      onSaved();
    } catch (err) {
      if (err instanceof ApiError) setErrors(err.fields);
      setError(errorMessage(err));
    } finally { setBusy(false); }
  };

  return (
    <Modal open wide title={editing ? `Edit ${editing.registration_number}` : "Add a vehicle"} onClose={onClose}
      footer={<><button className="btn-secondary" onClick={onClose}>Cancel</button><button className="btn-primary" disabled={busy} onClick={() => submit()}>{editing ? "Save changes" : "Add vehicle"}</button></>}>
      <form onSubmit={submit} className="space-y-4" noValidate>
        {error && <Banner tone="bad">{error}</Banner>}
        <Banner tone="info">Vehicle details are locked once a policy is issued for the vehicle, so check them carefully.</Banner>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Registration number" required id="registration_number" error={errors.registration_number}><Input {...bind("registration_number")} placeholder="MH02AB1234" /></Field>
          <Field label="Vehicle type" required id="vehicle_type"><Select {...bind("vehicle_type")}>{VEHICLE_TYPES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select></Field>
          <Field label="Make" required id="make" error={errors.make}><Input {...bind("make")} placeholder="Maruti Suzuki" /></Field>
          <Field label="Model" required id="model" error={errors.model}><Input {...bind("model")} placeholder="Swift VXi" /></Field>
          <Field label="Manufacturing year" required id="manufacturing_year" error={errors.manufacturing_year}><Input type="number" {...bind("manufacturing_year")} /></Field>
          <Field label="Colour" required id="color" error={errors.color}><Input {...bind("color")} /></Field>
          <Field label="Registration date" required id="registration_date" error={errors.registration_date}><Input type="date" max={todayISO()} {...bind("registration_date")} /></Field>
          <Field label="Purchase date" required id="purchase_date" error={errors.purchase_date}><Input type="date" max={todayISO()} {...bind("purchase_date")} /></Field>
          <Field label="Engine number" required id="engine_number" error={errors.engine_number}><Input {...bind("engine_number")} /></Field>
          <Field label="Chassis number" required id="chassis_number" error={errors.chassis_number}><Input {...bind("chassis_number")} /></Field>
        </div>
        <fieldset className="rounded-md border border-line p-4">
          <legend className="px-1 text-sm font-medium">Registered owner (as on the RC)</legend>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Owner name" required id="owner_name" error={errors.owner_name}><Input {...bind("owner_name")} /></Field>
            <Field label="Owner phone" id="owner_phone" error={errors.owner_phone}><Input {...bind("owner_phone")} /></Field>
          </div>
          <div className="mt-4"><Field label="Owner address" id="owner_address"><Input {...bind("owner_address")} /></Field></div>
        </fieldset>
      </form>
    </Modal>
  );
}

export default function VehiclesPage() {
  const { user } = useAuth();
  const isCustomer = user?.role === "CUSTOMER";
  const { data, loading, error, reload } = useApi<Page<Vehicle>>("/vehicles/?page_size=100");
  const [params, setParams] = useSearchParams();
  const [form, setForm] = useState<{ initial: Form; editing?: Vehicle } | null>(null);

  useEffect(() => {
    if (params.get("add") === "1" && isCustomer) { setForm({ initial: { ...EMPTY, owner_name: user?.full_name ?? "" } }); setParams({}, { replace: true }); }
  }, [params, setParams, isCustomer, user]);

  return (
    <>
      <PageHeader title="Vehicles" subtitle="Every vehicle you insure with us. Records are kept permanently for policy and claim history."
        actions={isCustomer && <button className="btn-primary" onClick={() => setForm({ initial: { ...EMPTY, owner_name: user?.full_name ?? "" } })}><Plus className="h-4 w-4" />Add vehicle</button>} />
      {loading ? <Spinner /> : error ? <ErrorState message={error} onRetry={reload} /> : !data?.results.length ? (
        <div className="panel"><Empty title="No vehicles registered" action={isCustomer && <button className="btn-primary" onClick={() => setForm({ initial: EMPTY })}>Add your first vehicle</button>}>
          Add a vehicle before requesting a policy for it.</Empty></div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {data.results.map((v) => (
            <article key={v.id} className="panel p-5">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="inline-block rounded border-2 border-ink px-2 py-0.5 text-sm font-semibold tracking-wider">{v.registration_number}</div>
                  <h2 className="mt-2">{v.make} {v.model}</h2>
                  <p className="text-sm text-ink-500">{v.vehicle_type_display}, {v.manufacturing_year}, {v.color}</p>
                </div>
                {v.current_policy ? <Badge tone={POLICY_STATUS_TONE[v.current_policy.status]}>Insured</Badge> : <Badge>Not insured</Badge>}
              </div>
              <dl className="dl mt-4">
                <dt>Registered owner</dt><dd>{v.owner_name}</dd>
                <dt>Engine / chassis</dt><dd className="truncate">{v.engine_number} / {v.chassis_number}</dd>
                <dt>Purchased</dt><dd>{date(v.purchase_date)}</dd>
                <dt>Current policy</dt><dd>{v.current_policy ? <>{v.current_policy.policy_number}, until {date(v.current_policy.end_date)}</> : "None"}</dd>
              </dl>
              <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-line pt-4">
                {isCustomer && !v.current_policy && <Link to={`/policies?request=1&vehicle=${v.id}`} className="btn-primary btn-sm">Request policy</Link>}
                {isCustomer && (v.is_locked
                  ? <span className="flex items-center gap-1.5 text-xs text-ink-500"><Lock className="h-3.5 w-3.5" />Details locked after policy association</span>
                  : <button className="btn-secondary btn-sm" onClick={() => setForm({ editing: v, initial: Object.fromEntries(Object.keys(EMPTY).map((k) => [k, String((v as unknown as Record<string, unknown>)[k] ?? "")])) as Form })}>
                      <Pencil className="h-3.5 w-3.5" />Edit</button>)}
              </div>
            </article>
          ))}
        </div>
      )}
      {form && <VehicleForm initial={form.initial} editing={form.editing} onClose={() => setForm(null)} onSaved={() => { setForm(null); reload(); }} />}
    </>
  );
}
