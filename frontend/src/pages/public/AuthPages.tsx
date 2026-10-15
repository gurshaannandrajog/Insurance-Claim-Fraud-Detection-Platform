import { CheckCircle2, Loader2, MailCheck } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { ApiError, api, ensureCsrf, errorMessage } from "../../api/client";
import { homeFor, useAuth } from "../../auth/AuthContext";
import { Banner, Field, Input } from "../../components/ui";

function AuthShell({ title, subtitle, children }: { title: string; subtitle?: ReactNode; children: ReactNode }) {
  return (
    <div className="grid min-h-screen lg:grid-cols-[minmax(380px,44%)_1fr]">
      <aside className="relative hidden overflow-hidden bg-ink p-12 text-white lg:flex lg:flex-col">
        <div className="flex items-center gap-2.5">
          <svg viewBox="0 0 32 32" className="h-8 w-8" aria-hidden><path d="M16 2 4 7v8c0 7.5 5.1 13.4 12 15 6.9-1.6 12-7.5 12-15V7z" fill="#0E7C7B" /><path d="m10.5 16 4 4 7-8" stroke="#fff" strokeWidth="2.4" fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg>
          <span className="text-lg font-semibold">ClaimSure</span>
        </div>
        <div className="mt-auto max-w-md">
          <p className="text-[2rem] font-semibold leading-tight">From the moment of the incident to the final settlement, every claim is accounted for.</p>
          <p className="mt-4 text-ink-100/70">Vehicle policies, claims, evidence and fraud review for policyholders, claim adjusters and investigators.</p>
        </div>
        <svg className="pointer-events-none absolute -right-24 top-24 h-[420px] w-[420px] opacity-[0.07]" viewBox="0 0 32 32" aria-hidden><path d="M16 2 4 7v8c0 7.5 5.1 13.4 12 15 6.9-1.6 12-7.5 12-15V7z" fill="#fff" /></svg>
      </aside>
      <main className="flex items-center justify-center px-5 py-10">
        <div className="w-full max-w-[440px]">
          <h1>{title}</h1>
          {subtitle && <p className="mt-1.5 text-sm text-ink-500">{subtitle}</p>}
          <div className="mt-7">{children}</div>
        </div>
      </main>
    </div>
  );
}

function useForm<T extends Record<string, string>>(initial: T) {
  const [values, setValues] = useState(initial);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const bind = (k: keyof T) => ({
    id: String(k), value: values[k],
    onChange: (e: { target: { value: string } }) => { setValues((v) => ({ ...v, [k]: e.target.value })); setErrors((x) => ({ ...x, [k as string]: "" })); },
    invalid: Boolean(errors[k as string]),
  });
  return { values, setValues, errors, setErrors, bind };
}

const PASSWORD_RULES: [RegExp, string][] = [[/.{8,}/, "8+ characters"], [/[A-Z]/, "uppercase"], [/[a-z]/, "lowercase"], [/[0-9]/, "number"], [/[^A-Za-z0-9]/, "special character"]];

function PasswordRules({ value }: { value: string }) {
  return (
    <ul className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs">
      {PASSWORD_RULES.map(([re, label]) => (
        <li key={label} className={re.test(value) ? "text-ok" : "text-ink-500"}>{re.test(value) ? "✓" : "○"} {label}</li>
      ))}
    </ul>
  );
}

const passwordOk = (v: string) => PASSWORD_RULES.every(([re]) => re.test(v));

export function LoginPage() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const f = useForm({ email: "", password: "" });
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);
  const [resent, setResent] = useState(false);
  const reason = params.get("reason");

  if (user) return <Navigate to={homeFor(user.role)} replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!f.values.email || !f.values.password) return setError(new ApiError(400, { code: "required", message: "Enter your email and password." }));
    setBusy(true); setError(null);
    try {
      const u = await login(f.values.email, f.values.password);
      navigate(params.get("next") || homeFor(u.role), { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err : new ApiError(0, { code: "error", message: errorMessage(err) }));
    } finally { setBusy(false); }
  };

  const resend = async () => {
    await ensureCsrf();
    await api.post("/auth/resend-verification/", { email: f.values.email });
    setResent(true);
  };

  return (
    <AuthShell title="Sign in" subtitle={<>New policyholder? <Link to="/register" className="font-medium text-cover hover:underline">Create an account</Link></>}>
      <form onSubmit={submit} className="space-y-4" noValidate>
        {reason === "session_expired" && <Banner tone="warn">You were signed out after 30 minutes of inactivity. Sign in again to continue.</Banner>}
        {error && (
          <Banner tone={error.code === "account_locked" ? "warn" : "bad"}>
            {error.message}
            {error.code === "email_not_verified" && (resent ? <span className="block pt-1">A new verification link has been sent.</span> :
              <button type="button" onClick={resend} className="block pt-1 font-medium underline">Resend verification email</button>)}
          </Banner>
        )}
        <Field label="Email" id="email"><Input type="email" autoComplete="email" {...f.bind("email")} /></Field>
        <Field label="Password" id="password"><Input type="password" autoComplete="current-password" {...f.bind("password")} /></Field>
        <div className="flex justify-end"><Link to="/forgot-password" className="text-sm text-cover hover:underline">Forgot password?</Link></div>
        <button className="btn-primary w-full py-2.5" disabled={busy}>{busy && <Loader2 className="h-4 w-4 animate-spin" />}Sign in</button>
        <p className="text-xs text-ink-500">After 4 failed attempts the account is locked for 20 minutes.</p>
      </form>
    </AuthShell>
  );
}

export function RegisterPage() {
  const f = useForm({ full_name: "", email: "", phone: "", date_of_birth: "", address_line: "", city: "", state: "", postal_code: "", password: "", confirm_password: "" });
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const validate = () => {
    const e: Record<string, string> = {};
    const v = f.values;
    (["full_name", "email", "phone", "date_of_birth", "address_line", "city", "state", "postal_code"] as const).forEach((k) => { if (!v[k].trim()) e[k] = "Required"; });
    if (v.email && !/^\S+@\S+\.\S+$/.test(v.email)) e.email = "Enter a valid email address.";
    if (v.phone && !/^\+?[0-9]{10,15}$/.test(v.phone)) e.phone = "10–15 digits, optionally starting with +.";
    if (!passwordOk(v.password)) e.password = "Password does not meet the requirements.";
    if (v.password !== v.confirm_password) e.confirm_password = "Passwords do not match.";
    f.setErrors(e);
    return Object.keys(e).length === 0;
  };

  const submit = async (ev: FormEvent) => {
    ev.preventDefault();
    setError("");
    if (!validate()) return;
    setBusy(true);
    try {
      await ensureCsrf();
      await api.post("/auth/register/", f.values);
      setDone(true);
    } catch (e) {
      if (e instanceof ApiError && Object.keys(e.fields).length) f.setErrors(e.fields);
      setError(errorMessage(e));
    } finally { setBusy(false); }
  };

  if (done) return (
    <AuthShell title="Check your inbox">
      <div className="flex gap-3 rounded-md border border-line bg-white p-5">
        <MailCheck className="h-6 w-6 shrink-0 text-cover" />
        <div className="text-sm text-ink-700">
          We sent a verification link to <strong>{f.values.email}</strong>. Open it to activate your account, then sign in.
          <div className="mt-4"><Link to="/login" className="btn-primary">Go to sign in</Link></div>
        </div>
      </div>
    </AuthShell>
  );

  return (
    <AuthShell title="Create your account" subtitle={<>Already registered? <Link to="/login" className="font-medium text-cover hover:underline">Sign in</Link></>}>
      <form onSubmit={submit} className="space-y-4" noValidate>
        {error && <Banner tone="bad">{error}</Banner>}
        <Field label="Full name" required id="full_name" error={f.errors.full_name}><Input {...f.bind("full_name")} autoComplete="name" /></Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Email" required id="email" error={f.errors.email}><Input type="email" {...f.bind("email")} autoComplete="email" /></Field>
          <Field label="Mobile number" required id="phone" error={f.errors.phone}><Input {...f.bind("phone")} placeholder="+919876543210" autoComplete="tel" /></Field>
        </div>
        <Field label="Date of birth" required id="date_of_birth" error={f.errors.date_of_birth} hint="Cannot be changed later."><Input type="date" {...f.bind("date_of_birth")} /></Field>
        <Field label="Address" required id="address_line" error={f.errors.address_line}><Input {...f.bind("address_line")} autoComplete="street-address" /></Field>
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="City" required id="city" error={f.errors.city}><Input {...f.bind("city")} /></Field>
          <Field label="State" required id="state" error={f.errors.state}><Input {...f.bind("state")} /></Field>
          <Field label="PIN code" required id="postal_code" error={f.errors.postal_code}><Input {...f.bind("postal_code")} /></Field>
        </div>
        <Field label="Password" required id="password" error={f.errors.password}>
          <Input type="password" {...f.bind("password")} autoComplete="new-password" />
          <PasswordRules value={f.values.password} />
        </Field>
        <Field label="Confirm password" required id="confirm_password" error={f.errors.confirm_password}><Input type="password" {...f.bind("confirm_password")} autoComplete="new-password" /></Field>
        <button className="btn-primary w-full py-2.5" disabled={busy}>{busy && <Loader2 className="h-4 w-4 animate-spin" />}Create account</button>
      </form>
    </AuthShell>
  );
}

export function VerifyEmailPage() {
  const [params] = useSearchParams();
  const [state, setState] = useState<"working" | "ok" | "error">("working");
  const [message, setMessage] = useState("");
  const ran = useRef(false);
  useEffect(() => {
    if (ran.current) return;
    ran.current = true;
    (async () => {
      try {
        await ensureCsrf();
        await api.post("/auth/verify-email/", { token: params.get("token") || "" });
        setState("ok");
      } catch (e) { setState("error"); setMessage(errorMessage(e)); }
    })();
  }, [params]);
  return (
    <AuthShell title="Email verification">
      {state === "working" && <p className="flex items-center gap-2 text-sm"><Loader2 className="h-4 w-4 animate-spin" />Verifying your email…</p>}
      {state === "ok" && <div className="space-y-4"><Banner tone="ok"><CheckCircle2 className="mr-1.5 inline h-4 w-4" />Your email is verified.</Banner><Link to="/login" className="btn-primary">Sign in</Link></div>}
      {state === "error" && <div className="space-y-4"><Banner tone="bad">{message}</Banner><Link to="/login" className="btn-secondary">Back to sign in</Link></div>}
    </AuthShell>
  );
}

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!/^\S+@\S+\.\S+$/.test(email)) return setError("Enter a valid email address.");
    try { await ensureCsrf(); await api.post("/auth/password-reset/", { email }); setSent(true); } catch (err) { setError(errorMessage(err)); }
  };
  return (
    <AuthShell title="Reset your password" subtitle="We'll email you a link to choose a new password.">
      {sent ? <div className="space-y-4"><Banner tone="ok">If an account exists for {email}, a reset link is on its way.</Banner><Link to="/login" className="btn-secondary">Back to sign in</Link></div> : (
        <form onSubmit={submit} className="space-y-4" noValidate>
          <Field label="Email" error={error} id="email"><Input type="email" id="email" value={email} invalid={!!error} onChange={(e) => { setEmail(e.target.value); setError(""); }} /></Field>
          <button className="btn-primary w-full py-2.5">Send reset link</button>
          <Link to="/login" className="block text-center text-sm text-cover hover:underline">Back to sign in</Link>
        </form>
      )}
    </AuthShell>
  );
}

export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const [pw, setPw] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!passwordOk(pw)) return setError("Password does not meet the requirements.");
    if (pw !== confirm) return setError("Passwords do not match.");
    try {
      await ensureCsrf();
      await api.post("/auth/password-reset/confirm/", { uid: params.get("uid"), token: params.get("token"), new_password: pw });
      setDone(true);
    } catch (err) { setError(errorMessage(err)); }
  };
  return (
    <AuthShell title="Choose a new password">
      {done ? <div className="space-y-4"><Banner tone="ok">Password saved. You can now sign in.</Banner><Link to="/login" className="btn-primary">Sign in</Link></div> : (
        <form onSubmit={submit} className="space-y-4" noValidate>
          {error && <Banner tone="bad">{error}</Banner>}
          <Field label="New password" id="pw"><Input id="pw" type="password" value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="new-password" /><PasswordRules value={pw} /></Field>
          <Field label="Confirm new password" id="pw2"><Input id="pw2" type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" /></Field>
          <button className="btn-primary w-full py-2.5">Save password</button>
        </form>
      )}
    </AuthShell>
  );
}
