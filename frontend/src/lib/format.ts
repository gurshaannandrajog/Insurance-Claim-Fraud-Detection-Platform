const inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });
const inr2 = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", minimumFractionDigits: 2 });

export const money = (v: string | number | null | undefined, exact = false) =>
  v === null || v === undefined || v === "" ? "—" : (exact ? inr2 : inr).format(Number(v));

export const compactMoney = (v: number) =>
  v >= 1e7 ? `₹${(v / 1e7).toFixed(1)} Cr` : v >= 1e5 ? `₹${(v / 1e5).toFixed(1)} L` : inr.format(v);

export const date = (v: string | null | undefined) =>
  v ? new Date(v.length === 10 ? `${v}T00:00:00` : v).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }) : "—";

export const dateTime = (v: string | null | undefined) =>
  v ? new Date(v).toLocaleString("en-IN", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "—";

export const relative = (v: string) => {
  const s = (Date.now() - new Date(v).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  if (s < 86400 * 7) return `${Math.floor(s / 86400)} d ago`;
  return date(v);
};

export const fileSize = (b: number) => (b > 1048576 ? `${(b / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1024))} KB`);

export const todayISO = () => {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
};
