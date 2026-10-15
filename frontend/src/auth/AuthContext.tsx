import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { api, ensureCsrf, onAuthLost } from "../api/client";
import type { Role, User } from "../api/types";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<User>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const Ctx = createContext<AuthState | null>(null);

export const homeFor = (role: Role) =>
  ({ CUSTOMER: "/dashboard", ADJUSTER: "/staff", SIU: "/siu", ADMIN: "/admin" })[role];

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();
  const userRef = useRef<User | null>(null);
  userRef.current = user;

  const refresh = useCallback(async () => {
    try {
      await ensureCsrf();
      const r = await api.get<User>("/auth/me/");
      setUser(r.data);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // The server is the authority on sessions: when it says the session expired, sign out locally.
  useEffect(
    () =>
      onAuthLost((code) => {
        const wasSignedIn = userRef.current !== null;
        setUser(null);
        if (wasSignedIn) navigate(`/login?reason=${code}`, { replace: true });
      }),
    [navigate],
  );

  const login = async (email: string, password: string) => {
    await ensureCsrf();
    const r = await api.post<User>("/auth/login/", { email, password });
    await ensureCsrf(); // Django rotates the CSRF token on login
    setUser(r.data);
    return r.data;
  };

  const logout = async () => {
    try {
      await api.post("/auth/logout/");
    } finally {
      setUser(null);
      navigate("/login", { replace: true });
    }
  };

  return <Ctx.Provider value={{ user, loading, login, logout, refresh }}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth outside AuthProvider");
  return v;
}
