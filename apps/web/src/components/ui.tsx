"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";
import { AlertCircle, CheckCircle2, LoaderCircle, Search, X, Inbox } from "lucide-react";

export function Badge({ value, children }: { value: string; children?: ReactNode }) {
  const good = ["up", "healthy", "operational", "resolved", "success", "successful", "completed", "info"].includes(value.toLowerCase());
  const bad = ["down", "critical", "error", "failed", "failure"].includes(value.toLowerCase());
  const warm = ["high", "warning", "warn", "degraded", "open"].includes(value.toLowerCase());
  const tone = good ? "green" : bad ? "red" : warm ? "orange" : ["investigating", "medium", "running", "pending"].includes(value.toLowerCase()) ? "purple" : "gray";
  return <span className={`badge ${tone}`}><span className="badge-dot" />{children || value.replace(/_/g, " ")}</span>;
}
export function Empty({ title, detail, action }: { title: string; detail: string; action?: ReactNode }) {
  return <div className="empty"><span className="empty-icon"><Inbox size={23} /></span><h3>{title}</h3><p>{detail}</p>{action}</div>;
}
export function ErrorState({ message, retry }: { message: string; retry?: () => void }) {
  return <div className="error-state" role="alert"><AlertCircle size={20} /><div><strong>We couldn’t load this data</strong><p>{message}</p></div>{retry && <button className="button secondary small" onClick={retry}>Try again</button>}</div>;
}
export function Loading({ label = "Loading your workspace" }: { label?: string }) {
  return <div className="loading-state" role="status"><LoaderCircle className="spin" size={21} /><span>{label}…</span></div>;
}
export function SearchInput({ value, onChange, placeholder = "Search…" }: { value: string; onChange: (value: string) => void; placeholder?: string }) {
  return <div className="search-input"><Search size={16} /><input aria-label={placeholder} placeholder={placeholder} value={value} onChange={event => onChange(event.target.value)} />{value && <button className="icon-button" aria-label="Clear search" onClick={() => onChange("")}><X size={14} /></button>}</div>;
}
export function Modal({ title, description, children, onClose }: { title: string; description?: string; children: ReactNode; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const id = useId();
  useEffect(() => {
    const dialog = ref.current;
    dialog?.showModal();
    return () => { dialog?.close(); };
  }, []);
  return <dialog className="modal" ref={ref} aria-labelledby={id} onCancel={event => { event.preventDefault(); onClose(); }} onClick={event => { if (event.target === event.currentTarget) onClose(); }}>
    <div className="modal-inner"><div className="modal-head"><div><h2 id={id}>{title}</h2>{description && <p>{description}</p>}</div><button type="button" className="icon-button" aria-label="Close dialog" onClick={onClose}><X size={20} /></button></div>{children}</div>
  </dialog>;
}
export function Toast({ message, kind, onClose }: { message: string; kind: "success" | "error"; onClose: () => void }) {
  useEffect(() => { const timer = setTimeout(onClose, kind === "error" ? 8500 : 4500); return () => clearTimeout(timer); }, [message, kind, onClose]);
  return <div className={`toast ${kind}`} role={kind === "error" ? "alert" : "status"}>{kind === "success" ? <CheckCircle2 size={19} /> : <AlertCircle size={19} />}<span>{message}</span><button className="icon-button" aria-label="Dismiss notification" onClick={onClose}><X size={16} /></button></div>;
}
export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return <label className="field"><span>{label}</span>{children}{hint && <small>{hint}</small>}</label>;
}
export function Submit({ busy, children }: { busy: boolean; children: ReactNode }) {
  return <button className="button primary" type="submit" disabled={busy}>{busy && <LoaderCircle size={16} className="spin" />}{busy ? "Saving…" : children}</button>;
}
