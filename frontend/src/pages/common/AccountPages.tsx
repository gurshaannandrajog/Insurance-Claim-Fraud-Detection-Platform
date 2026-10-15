import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError, api, errorMessage, type Page } from "../../api/client";
import type { Notification, User } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { useToast } from "../../components/Toast";
import { Banner, Empty, ErrorState, Field, Input, Modal, PageHeader, Pagination, Panel, Spinner } from "../../components/ui";
import { date, dateTime } from "../../lib/format";
import { qs, useApi } from "../../lib/useApi";

export function NotificationsPage() {
  const [page, setPage] = useState(1);
  const [unread, setUnread] = useState(false);
  const { data, loading, error, reload } = useApi<Page<Notification>>(`/notifications/${qs({ page, unread: unread ? "true" : "" })}`);
  const navigate = useNavigate();
  const open = async (n: Notification) => {
    if (!n.is_read) await api.post(`/notifications/${n.id}/read/`);
    if (n.link) navigate(n.link); else reload();
  };
  return (
    <>
      <PageHeader title="Notifications" actions={<>
        <button className="btn-secondary" onClick={() => { setUnread(!unread); setPage(1); }}>{unread ? "Show all" : "Show unread only"}</button>
        <button className="btn-secondary" onClick={async () => { await api.post("/notifications/read-all/"); reload(); }}>Mark all as read</button></>} />
      <div className="panel">
        {loading ? <Spinner /> : error ? <ErrorState message={error} onRetry={reload} /> : !data?.results.length ? <Empty title="No notifications">Updates about your claims, documents and policies appear here.</Empty> : (<>
          <ul className="divide-y divide-line">{data.results.map((n) => (
            <li key={n.id}><button onClick={() => open(n)} className="flex w-full gap-4 px-5 py-4 text-left hover:bg-paper">
              <span className={`mt-2 h-2 w-2 shrink-0 rounded-full ${n.is_read ? "bg-line" : "bg-cover"}`} />
              <span className="min-w-0 flex-1">
                <span className="flex flex-wrap items-baseline justify-between gap-2"><span className={n.is_read ? "" : "font-semibold"}>{n.title}</span><span className="text-xs text-ink-500">{dateTime(n.created_at)}</span></span>
                <span className="mt-0.5 block text-sm text-ink-700">{n.message}</span>
                <span className="mt-1 block text-xs text-ink-300">{n.type_display}</span>
              </span>
            </button></li>))}
          </ul>
          <Pagination page={page} count={data.count} onPage={setPage} />
        </>)}
      </div>
    </>
  );
}

function ChangePassword() {
  const toast = useToast();
  const [v, setV] = useState({ current_password: "", new_password: "", confirm: "" });
  const [error, setError] = useState("");
  const submit = async () => {
    if (v.new_password !== v.confirm) return setError("New passwords do not match.");
    try { await api.post("/auth/change-password/", { current_password: v.current_password, new_password: v.new_password }); toast("Password changed"); setV({ current_password: "", new_password: "", confirm: "" }); setError(""); }
    catch (e) { setError(errorMessage(e)); }
  };
  return (
    <Panel title="Change password">
      <div className="max-w-md space-y-4">
        {error && <Banner tone="bad">{error}</Banner>}
        <Field label="Current password"><Input type="password" autoComplete="current-password" value={v.current_password} onChange={(e) => setV({ ...v, current_password: e.target.value })} /></Field>
        <Field label="New password" hint="8+ characters with uppercase, lowercase, a number and a special character."><Input type="password" autoComplete="new-password" value={v.new_password} onChange={(e) => setV({ ...v, new_password: e.target.value })} /></Field>
        <Field label="Confirm new password"><Input type="password" autoComplete="new-password" value={v.confirm} onChange={(e) => setV({ ...v, confirm: e.target.value })} /></Field>
        <button className="btn-primary" onClick={submit} disabled={!v.current_password || !v.new_password}>Change password</button>
      </div>
    </Panel>
  );
}

export function ProfilePage() {
  const toast = useToast();
  const { refresh, logout } = useAuth();
  const { data: u, setData, loading, error, reload } = useApi<User>("/profile/");
  const [form, setForm] = useState<Record<string, string> | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [del, setDel] = useState(false);
  const [pw, setPw] = useState("");
  const [delError, setDelError] = useState("");
  if (loading) return <Spinner />;
  if (error || !u || !u.customer_profile) return <ErrorState message={error ?? "Could not load your profile."} onRetry={reload} />;
  const p = u.customer_profile;
  const v = form ?? { full_name: u.full_name, phone: p.phone, address_line: p.address_line, city: p.city, state: p.state, postal_code: p.postal_code };
  const bind = (k: string) => ({ value: v[k], invalid: !!errors[k], onChange: (e: { target: { value: string } }) => setForm({ ...v, [k]: e.target.value }) });

  const save = async () => {
    try { const r = await api.patch<User>("/profile/", v); setData(r.data); setForm(null); setErrors({}); toast("Profile updated"); refresh(); }
    catch (e) { if (e instanceof ApiError) setErrors(e.fields); toast(errorMessage(e), "error"); }
  };
  const remove = async () => {
    try { await api.post("/profile/delete/", { password: pw }); toast("Your account has been deleted"); await logout(); }
    catch (e) { setDelError(errorMessage(e)); }
  };

  return (
    <>
      <PageHeader title="Profile" />
      <div className="space-y-6">
        <Panel title="Personal details">
          <div className="grid max-w-3xl gap-4 sm:grid-cols-2">
            <Field label="Full name" error={errors.full_name}><Input {...bind("full_name")} /></Field>
            <Field label="Mobile number" error={errors.phone}><Input {...bind("phone")} /></Field>
            <Field label="Email" hint="Your sign-in email cannot be changed."><Input value={u.email} disabled /></Field>
            <Field label="Date of birth" hint="Cannot be changed."><Input value={date(p.date_of_birth)} disabled /></Field>
            <div className="sm:col-span-2"><Field label="Address" error={errors.address_line}><Input {...bind("address_line")} /></Field></div>
            <Field label="City" error={errors.city}><Input {...bind("city")} /></Field>
            <Field label="State" error={errors.state}><Input {...bind("state")} /></Field>
            <Field label="PIN code" error={errors.postal_code}><Input {...bind("postal_code")} /></Field>
          </div>
          <div className="mt-5 flex gap-2"><button className="btn-primary" disabled={!form} onClick={save}>Save changes</button>{form && <button className="btn-secondary" onClick={() => { setForm(null); setErrors({}); }}>Discard</button>}</div>
        </Panel>
        <ChangePassword />
        <Panel title="Delete account">
          <p className="max-w-2xl text-sm text-ink-700">You can delete your account when none of your claims are in progress. Policy and claim records are kept for legal and audit purposes, but you will no longer be able to sign in.</p>
          <button className="btn-secondary mt-4 text-bad" onClick={() => { setDel(true); setDelError(""); }}>Delete my account</button>
        </Panel>
      </div>
      <Modal open={del} title="Delete your account?" onClose={() => setDel(false)}
        footer={<><button className="btn-secondary" onClick={() => setDel(false)}>Cancel</button><button className="btn-danger" disabled={!pw} onClick={remove}>Delete account</button></>}>
        {delError && <Banner tone="bad">{delError} {delError.includes("active claim") && <Link to="/claims" className="underline">View claims</Link>}</Banner>}
        <Field label="Confirm with your password"><Input type="password" value={pw} onChange={(e) => setPw(e.target.value)} /></Field>
      </Modal>
    </>
  );
}

export function AccountPage() {
  const { user } = useAuth();
  if (!user) return null;
  return (
    <>
      <PageHeader title="Account" />
      <div className="space-y-6">
        <Panel title="Your details">
          <dl className="dl max-w-lg">
            <dt>Name</dt><dd>{user.full_name}</dd><dt>Email</dt><dd>{user.email}</dd><dt>Role</dt><dd>{user.role_display}</dd>
            <dt>Employee ID</dt><dd>{user.employee_profile?.employee_id ?? "—"}</dd><dt>Department</dt><dd>{user.employee_profile?.department || "—"}</dd>
          </dl>
          <p className="mt-4 text-xs text-ink-500">Contact an administrator to change these details.</p>
        </Panel>
        <ChangePassword />
      </div>
    </>
  );
}
