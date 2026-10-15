import type { ReactNode } from "react";
import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import type { Role } from "./api/types";
import { homeFor, useAuth } from "./auth/AuthContext";
import Layout from "./components/Layout";
import { Spinner } from "./components/ui";
import AdminDashboard from "./pages/admin/AdminDashboard";
import { AuditLogPage, CustomersAdmin, PlansAdmin, PoliciesAdmin, PolicyRequestsAdmin, ReportsPage, UsersAdmin } from "./pages/admin/AdminPages";
import { AccountPage, NotificationsPage, ProfilePage } from "./pages/common/AccountPages";
import ClaimsPage from "./pages/customer/ClaimsPage";
import CustomerClaimDetail from "./pages/customer/CustomerClaimDetail";
import CustomerDashboard from "./pages/customer/CustomerDashboard";
import NewClaimPage from "./pages/customer/NewClaimPage";
import PoliciesPage from "./pages/customer/PoliciesPage";
import VehiclesPage from "./pages/customer/VehiclesPage";
import { ForgotPasswordPage, LoginPage, RegisterPage, ResetPasswordPage, VerifyEmailPage } from "./pages/public/AuthPages";
import StaffClaimDetail from "./pages/staff/StaffClaimDetail";
import { AdjusterDashboard, AppealsPage, ClaimsQueuePage, SiuDashboard } from "./pages/staff/StaffPages";

/**
 * Route guards only decide what to *show*. Every permission is enforced again by the API —
 * a user who types a URL for another role gets the "no access" page, and the API would return 403/404 anyway.
 */
function RequireRole({ roles, children }: { roles?: Role[]; children: ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <Spinner label="Checking your session…" />;
  if (!user) return <Navigate to={`/login?next=${encodeURIComponent(location.pathname)}`} replace />;
  if (roles && !roles.includes(user.role)) return <NoAccess />;
  return <>{children}</>;
}

function NoAccess() {
  const { user } = useAuth();
  return (
    <div className="mx-auto max-w-md py-20 text-center">
      <h1>You don't have access to this page</h1>
      <p className="mt-2 text-sm text-ink-500">This area belongs to a different role. Your role is {user?.role_display}.</p>
      {user && <Link to={homeFor(user.role)} className="btn-primary mt-6">Go to your workspace</Link>}
    </div>
  );
}

function NotFound() {
  return (
    <div className="mx-auto max-w-md py-20 text-center">
      <h1>Page not found</h1>
      <p className="mt-2 text-sm text-ink-500">The address may be mistyped, or the record may belong to someone else.</p>
      <Link to="/" className="btn-primary mt-6">Go home</Link>
    </div>
  );
}

function Home() {
  const { user, loading } = useAuth();
  if (loading) return <Spinner />;
  return <Navigate to={user ? homeFor(user.role) : "/login"} replace />;
}

const C: Role[] = ["CUSTOMER"], A: Role[] = ["ADJUSTER"], S: Role[] = ["SIU"], M: Role[] = ["ADMIN"];
const STAFF: Role[] = ["ADJUSTER", "SIU", "ADMIN"];

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/verify-email" element={<VerifyEmailPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />

      <Route element={<RequireRole><Layout /></RequireRole>}>
        <Route path="/dashboard" element={<RequireRole roles={C}><CustomerDashboard /></RequireRole>} />
        <Route path="/claims" element={<RequireRole roles={C}><ClaimsPage /></RequireRole>} />
        <Route path="/claims/new" element={<RequireRole roles={C}><NewClaimPage /></RequireRole>} />
        <Route path="/claims/:id" element={<RequireRole roles={C}><CustomerClaimDetail /></RequireRole>} />
        <Route path="/vehicles" element={<RequireRole roles={C}><VehiclesPage /></RequireRole>} />
        <Route path="/policies" element={<RequireRole roles={C}><PoliciesPage /></RequireRole>} />
        <Route path="/profile" element={<RequireRole roles={C}><ProfilePage /></RequireRole>} />
        <Route path="/notifications" element={<NotificationsPage />} />
        <Route path="/account" element={<RequireRole roles={STAFF}><AccountPage /></RequireRole>} />

        <Route path="/staff" element={<RequireRole roles={A}><AdjusterDashboard /></RequireRole>} />
        <Route path="/staff/appeals" element={<RequireRole roles={A}><AppealsPage /></RequireRole>} />
        <Route path="/staff/claims" element={<RequireRole roles={STAFF}><ClaimsQueuePage /></RequireRole>} />
        <Route path="/staff/claims/:id" element={<RequireRole roles={STAFF}><StaffClaimDetail /></RequireRole>} />
        <Route path="/siu" element={<RequireRole roles={S}><SiuDashboard /></RequireRole>} />

        <Route path="/admin" element={<RequireRole roles={M}><AdminDashboard /></RequireRole>} />
        <Route path="/admin/policy-requests" element={<RequireRole roles={M}><PolicyRequestsAdmin /></RequireRole>} />
        <Route path="/admin/policies" element={<RequireRole roles={M}><PoliciesAdmin /></RequireRole>} />
        <Route path="/admin/plans" element={<RequireRole roles={M}><PlansAdmin /></RequireRole>} />
        <Route path="/admin/users" element={<RequireRole roles={M}><UsersAdmin /></RequireRole>} />
        <Route path="/admin/customers" element={<RequireRole roles={M}><CustomersAdmin /></RequireRole>} />
        <Route path="/admin/reports" element={<RequireRole roles={M}><ReportsPage /></RequireRole>} />
        <Route path="/admin/audit" element={<RequireRole roles={M}><AuditLogPage /></RequireRole>} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
