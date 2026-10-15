import { AlertTriangle, Inbox, Loader2, X } from "lucide-react";
import { useEffect, useRef, type ReactNode, type SelectHTMLAttributes, type InputHTMLAttributes, type TextareaHTMLAttributes } from "react";
import type { Tone } from "../lib/labels";

const TONES: Record<Tone, string> = {
  neutral: "bg-ink-100 text-ink-700",
  info: "bg-info-light text-info",
  ok: "bg-ok-light text-ok",
  warn: "bg-warn-light text-warn",
  bad: "bg-bad-light text-bad",
  cover: "bg-cover-light text-cover-dark",
};

export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded px-2 py-0.5 text-xs font-medium ${TONES[tone]}`}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden />
      {children}
    </span>
  );
}

export function Spinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-16 text-sm text-ink-500" role="status">
      <Loader2 className="h-4 w-4 animate-spin" /> {label}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center gap-3 py-14 text-center" role="alert">
      <AlertTriangle className="h-6 w-6 text-bad" />
      <p className="max-w-md text-sm text-ink-700">{message}</p>
      {onRetry && <button className="btn-secondary btn-sm" onClick={onRetry}>Try again</button>}
    </div>
  );
}

export function Empty({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 px-6 py-12 text-center">
      <Inbox className="h-6 w-6 text-ink-300" />
      <p className="font-medium">{title}</p>
      {children && <p className="max-w-sm text-sm text-ink-500">{children}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <h1>{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-ink-500">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function Panel({ title, actions, children, className = "", bodyClass = "panel-body" }:
  { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; bodyClass?: string }) {
  return (
    <section className={`panel ${className}`}>
      {(title || actions) && (
        <header className="panel-head">
          <h2 className="text-[0.95rem]">{title}</h2>
          {actions}
        </header>
      )}
      <div className={bodyClass}>{children}</div>
    </section>
  );
}

/** Key figure: number first, label underneath, optional note. */
export function Stat({ label, value, note, tone }: { label: string; value: ReactNode; note?: ReactNode; tone?: Tone }) {
  const color = tone === "bad" ? "text-bad" : tone === "warn" ? "text-warn" : tone === "ok" ? "text-ok" : "text-ink";
  return (
    <div className="min-w-0 px-5 py-4">
      <div className={`text-2xl font-semibold tracking-tight ${color}`}>{value}</div>
      <div className="mt-0.5 text-sm text-ink-500">{label}</div>
      {note && <div className="mt-1 text-xs text-ink-300">{note}</div>}
    </div>
  );
}

export function StatStrip({ children }: { children: ReactNode }) {
  return <div className="panel grid grid-cols-2 divide-line sm:grid-cols-3 lg:grid-cols-6 [&>*]:border-line [&>*]:border-b lg:[&>*]:border-b-0 lg:[&>*:not(:last-child)]:border-r">{children}</div>;
}

interface FieldProps { label: string; error?: string; hint?: ReactNode; children: ReactNode; required?: boolean; id?: string }
export function Field({ label, error, hint, children, required, id }: FieldProps) {
  return (
    <div>
      <label className="label" htmlFor={id}>{label}{required && <span className="text-bad"> *</span>}</label>
      {children}
      {error ? <p className="field-error">{error}</p> : hint ? <p className="hint">{hint}</p> : null}
    </div>
  );
}

export const Input = ({ invalid, className = "", ...p }: InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean }) =>
  <input className={`input ${invalid ? "input-error" : ""} ${className}`} aria-invalid={invalid || undefined} {...p} />;

export const Select = ({ invalid, className = "", children, ...p }: SelectHTMLAttributes<HTMLSelectElement> & { invalid?: boolean }) =>
  <select className={`input ${invalid ? "input-error" : ""} ${className}`} aria-invalid={invalid || undefined} {...p}>{children}</select>;

export const Textarea = ({ invalid, className = "", ...p }: TextareaHTMLAttributes<HTMLTextAreaElement> & { invalid?: boolean }) =>
  <textarea className={`input min-h-[96px] ${invalid ? "input-error" : ""} ${className}`} aria-invalid={invalid || undefined} {...p} />;

export function Modal({ open, title, onClose, children, footer, wide }:
  { open: boolean; title: string; onClose: () => void; children: ReactNode; footer?: ReactNode; wide?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    ref.current?.querySelector<HTMLElement>("input,textarea,select,button")?.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-ink/40 p-0 sm:items-center sm:p-4" onMouseDown={onClose}>
      <div ref={ref} role="dialog" aria-modal="true" aria-label={title} onMouseDown={(e) => e.stopPropagation()}
        className={`max-h-[92vh] w-full overflow-y-auto rounded-t-lg bg-white sm:rounded-lg ${wide ? "sm:max-w-2xl" : "sm:max-w-lg"}`}>
        <div className="flex items-center justify-between border-b border-line px-5 py-4">
          <h2>{title}</h2>
          <button className="btn-ghost btn-sm" onClick={onClose} aria-label="Close"><X className="h-4 w-4" /></button>
        </div>
        <div className="space-y-4 px-5 py-5">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-line bg-paper/60 px-5 py-3">{footer}</div>}
      </div>
    </div>
  );
}

export function ConfirmDialog({ open, title, message, confirmLabel, danger, busy, onConfirm, onClose }: {
  open: boolean; title: string; message: ReactNode; confirmLabel: string; danger?: boolean; busy?: boolean;
  onConfirm: () => void; onClose: () => void;
}) {
  return (
    <Modal open={open} title={title} onClose={onClose} footer={<>
      <button className="btn-secondary" onClick={onClose} disabled={busy}>Cancel</button>
      <button className={danger ? "btn-danger" : "btn-primary"} onClick={onConfirm} disabled={busy}>
        {busy && <Loader2 className="h-4 w-4 animate-spin" />}{confirmLabel}
      </button>
    </>}>
      <div className="text-sm text-ink-700">{message}</div>
    </Modal>
  );
}

export function Pagination({ page, count, pageSize = 20, onPage }: { page: number; count: number; pageSize?: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(count / pageSize));
  if (pages <= 1) return null;
  return (
    <div className="flex items-center justify-between border-t border-line px-4 py-3 text-sm text-ink-500">
      <span>Page {page} of {pages} ({count} records)</span>
      <div className="flex gap-2">
        <button className="btn-secondary btn-sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous</button>
        <button className="btn-secondary btn-sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>Next</button>
      </div>
    </div>
  );
}

export function Banner({ tone = "info", children }: { tone?: Tone; children: ReactNode }) {
  return <div className={`rounded-md border px-4 py-3 text-sm ${TONES[tone]} border-current/20`}>{children}</div>;
}
