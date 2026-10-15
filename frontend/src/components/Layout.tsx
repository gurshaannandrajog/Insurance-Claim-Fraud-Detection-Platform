import {
  Bell, BarChart3, Car, ClipboardList, FileSearch, FileText, Gauge, LogOut, Menu, ScrollText, Settings2,
  ShieldCheck, UserCircle, Users, X, FolderKanban, Scale,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { api, type Page } from "../api/client";
import type { Notification, Role } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { relative } from "../lib/format";

interface NavItem { to: string; label: string; icon: ReactNode; end?: boolean }
const ic = "h-[18px] w-[18px]";

const NAV: Record<Role, NavItem[]> = {
  CUSTOMER: [
    { to: "/dashboard", label: "Overview", icon: <Gauge className={ic} /> },
    { to: "/claims", label: "My claims", icon: <FileText className={ic} /> },
    { to: "/vehicles", label: "Vehicles", icon: <Car className={ic} /> },
    { to: "/policies", label: "Policies", icon: <ShieldCheck className={ic} /> },
    { to: "/notifications", label: "Notifications", icon: <Bell className={ic} /> },
    { to: "/profile", label: "Profile", icon: <UserCircle className={ic} /> },
  ],
  ADJUSTER: [
    { to: "/staff", label: "Work queue", icon: <Gauge className={ic} />, end: true },
    { to: "/staff/claims", label: "All claims", icon: <FolderKanban className={ic} /> },
    { to: "/staff/appeals", label: "Appeals", icon: <Scale className={ic} /> },
    { to: "/notifications", label: "Notifications", icon: <Bell className={ic} /> },
    { to: "/account", label: "Account", icon: <UserCircle className={ic} /> },
  ],
  SIU: [
    { to: "/siu", label: "Investigations", icon: <FileSearch className={ic} />, end: true },
    { to: "/staff/claims", label: "Flagged claims", icon: <FolderKanban className={ic} /> },
    { to: "/notifications", label: "Notifications", icon: <Bell className={ic} /> },
    { to: "/account", label: "Account", icon: <UserCircle className={ic} /> },
  ],
  ADMIN: [
    { to: "/admin", label: "Analytics", icon: <BarChart3 className={ic} />, end: true },
    { to: "/admin/policy-requests", label: "Policy requests", icon: <ClipboardList className={ic} /> },
    { to: "/admin/policies", label: "Policies", icon: <ShieldCheck className={ic} /> },
    { to: "/admin/plans", label: "Plans & pricing", icon: <Settings2 className={ic} /> },
    { to: "/staff/claims", label: "Claims oversight", icon: <FolderKanban className={ic} /> },
    { to: "/admin/customers", label: "Customers", icon: <Users className={ic} /> },
    { to: "/admin/users", label: "Staff accounts", icon: <UserCircle className={ic} /> },
    { to: "/admin/reports", label: "Reports", icon: <FileText className={ic} /> },
    { to: "/admin/audit", label: "Audit log", icon: <ScrollText className={ic} /> },
  ],
};

function NotificationBell() {
  const [unread, setUnread] = useState(0);
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<Notification[]>([]);
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    let alive = true;
    const poll = () =>
      api.get<{ unread: number }>("/notifications/unread-count/", { headers: { "X-Background-Poll": "1" } })
        .then((r) => alive && setUnread(r.data.unread)).catch(() => {});
    poll();
    const t = setInterval(poll, 45000);
    return () => { alive = false; clearInterval(t); };
  }, [location.pathname]);

  useEffect(() => setOpen(false), [location.pathname]);

  const toggle = async () => {
    if (!open) {
      const r = await api.get<Page<Notification>>("/notifications/?page_size=6");
      setItems(r.data.results);
    }
    setOpen(!open);
  };

  const openItem = async (n: Notification) => {
    if (!n.is_read) {
      await api.post(`/notifications/${n.id}/read/`);
      setUnread((u) => Math.max(0, u - 1));
    }
    setOpen(false);
    if (n.link) navigate(n.link);
  };

  return (
    <div className="relative">
      <button onClick={toggle} className="btn-ghost relative px-2.5" aria-label={`Notifications, ${unread} unread`} aria-expanded={open}>
        <Bell className="h-5 w-5" />
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 min-w-[18px] rounded-full bg-bad px-1 text-center text-[11px] font-semibold leading-[18px] text-white">
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 z-40 mt-2 w-[min(92vw,380px)] rounded-md border border-line bg-white shadow-xl">
          <div className="flex items-center justify-between border-b border-line px-4 py-3">
            <span className="text-sm font-semibold">Notifications</span>
            {unread > 0 && (
              <button className="text-xs font-medium text-cover hover:underline"
                onClick={async () => { await api.post("/notifications/read-all/"); setUnread(0); setItems((x) => x.map((n) => ({ ...n, is_read: true }))); }}>
                Mark all as read
              </button>
            )}
          </div>
          <ul className="max-h-[60vh] overflow-y-auto">
            {items.length === 0 && <li className="px-4 py-8 text-center text-sm text-ink-500">You're all caught up.</li>}
            {items.map((n) => (
              <li key={n.id}>
                <button onClick={() => openItem(n)} className="flex w-full gap-3 border-b border-line/70 px-4 py-3 text-left hover:bg-paper">
                  <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${n.is_read ? "bg-transparent" : "bg-cover"}`} />
                  <span className="min-w-0">
                    <span className="block text-sm font-medium">{n.title}</span>
                    <span className="line-clamp-2 block text-xs text-ink-500">{n.message}</span>
                    <span className="mt-1 block text-[11px] text-ink-300">{relative(n.created_at)}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
          <Link to="/notifications" className="block px-4 py-2.5 text-center text-sm font-medium text-cover hover:bg-paper">View all notifications</Link>
        </div>
      )}
    </div>
  );
}

export default function Layout() {
  const { user, logout } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();
  useEffect(() => setMobileOpen(false), [location.pathname]);
  if (!user) return null;
  const nav = NAV[user.role];

  const sidebar = (
    <nav className="flex h-full flex-col bg-ink text-ink-100" aria-label="Main">
      <div className="flex items-center gap-2.5 px-5 py-5">
        <svg viewBox="0 0 32 32" className="h-7 w-7" aria-hidden><path d="M16 2 4 7v8c0 7.5 5.1 13.4 12 15 6.9-1.6 12-7.5 12-15V7z" fill="#0E7C7B" /><path d="m10.5 16 4 4 7-8" stroke="#fff" strokeWidth="2.4" fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg>
        <div className="leading-tight">
          <div className="font-semibold text-white">ClaimSure</div>
          <div className="text-xs text-ink-300">Motor claims &amp; fraud</div>
        </div>
      </div>
      <div className="mx-5 mb-3 rounded bg-ink-700 px-3 py-2 text-xs text-ink-100">{user.role_display} workspace</div>
      <ul className="flex-1 space-y-0.5 px-3">
        {nav.map((n) => (
          <li key={n.to}>
            <NavLink to={n.to} end={n.end}
              className={({ isActive }) => `flex items-center gap-3 rounded px-3 py-2 text-sm transition-colors ${isActive ? "bg-white/10 font-medium text-white shadow-[inset_3px_0_0_#0E7C7B]" : "text-ink-100/80 hover:bg-white/5 hover:text-white"}`}>
              {n.icon}{n.label}
            </NavLink>
          </li>
        ))}
      </ul>
      <div className="border-t border-white/10 px-5 py-4">
        <div className="truncate text-sm font-medium text-white">{user.full_name}</div>
        <div className="truncate text-xs text-ink-300">{user.email}</div>
        <button onClick={logout} className="mt-3 flex items-center gap-2 text-sm text-ink-100/80 hover:text-white">
          <LogOut className="h-4 w-4" /> Sign out
        </button>
      </div>
    </nav>
  );

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[248px_1fr]">
      <div className="hidden bg-ink lg:block"><aside className="sticky top-0 h-screen">{sidebar}</aside></div>
      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-ink/50" onClick={() => setMobileOpen(false)} />
          <aside className="relative h-full w-[260px]">{sidebar}</aside>
        </div>
      )}
      <div className="min-w-0">
        <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-line bg-white/95 px-4 backdrop-blur sm:px-6">
          <button className="btn-ghost px-2 lg:hidden" onClick={() => setMobileOpen(true)} aria-label="Open menu">
            {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
          <div className="hidden text-sm text-ink-500 lg:block">Signed in as <span className="font-medium text-ink">{user.full_name}</span></div>
          <NotificationBell />
        </header>
        <main className="mx-auto w-full max-w-[1240px] px-4 py-6 sm:px-6 lg:py-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
