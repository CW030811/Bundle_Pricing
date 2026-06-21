"use client";
import { useEffect } from "react";
import { X } from "lucide-react";

type Icon = React.ComponentType<{ className?: string }>;

export function StatCard({
  label,
  value,
  sub,
  icon: Icon,
  accent = "text-indigo-300",
}: {
  label: string;
  value: string;
  sub?: string;
  icon?: Icon;
  accent?: string;
}) {
  return (
    <div className="card p-5">
      <div className="flex items-center justify-between">
        <span className="text-sm text-slate-400">{label}</span>
        {Icon && <Icon className={`h-5 w-5 ${accent}`} />}
      </div>
      <div className="mt-2 text-2xl font-bold text-white">{value}</div>
      {sub && <div className="mt-1 text-xs text-slate-500">{sub}</div>}
    </div>
  );
}

export function Bars({
  data,
  unit = "",
}: {
  data: { label: string; value: number }[];
  unit?: string;
}) {
  const max = Math.max(1, ...data.map((d) => d.value));
  return (
    <div className="flex h-44 items-end gap-2">
      {data.map((d, i) => (
        <div key={i} className="flex flex-1 flex-col items-center gap-2">
          <div className="flex w-full flex-1 items-end">
            <div
              className="w-full rounded-t-md bg-gradient-to-t from-indigo-500/40 to-violet-400/80 transition-all"
              style={{ height: `${Math.max(3, (d.value / max) * 100)}%` }}
              title={`${d.value}${unit}`}
            />
          </div>
          <span className="text-[11px] text-slate-500">{d.label}</span>
        </div>
      ))}
    </div>
  );
}

export function Modal({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
}) {
  useEffect(() => {
    const onEsc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    if (open) window.addEventListener("keydown", onEsc);
    return () => window.removeEventListener("keydown", onEsc);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 grid place-items-center p-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="card relative z-10 max-h-[85vh] w-full max-w-lg overflow-y-auto p-6">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-white">{title}</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-white">
            <X className="h-5 w-5" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Badge({ status }: { status: string }) {
  const map: Record<string, string> = {
    active: "bg-emerald-500/15 text-emerald-300",
    paid: "bg-emerald-500/15 text-emerald-300",
    unused: "bg-emerald-500/15 text-emerald-300",
    pending: "bg-amber-500/15 text-amber-300",
    disabled: "bg-slate-500/20 text-slate-300",
    banned: "bg-rose-500/15 text-rose-300",
    failed: "bg-rose-500/15 text-rose-300",
    used: "bg-slate-500/20 text-slate-400",
    offline: "bg-slate-500/20 text-slate-400",
  };
  const text: Record<string, string> = {
    active: "正常",
    paid: "已支付",
    unused: "未使用",
    pending: "待支付",
    disabled: "已禁用",
    banned: "已封禁",
    failed: "失败",
    used: "已使用",
    offline: "已下架",
  };
  return <span className={`badge ${map[status] || "bg-white/10 text-slate-300"}`}>{text[status] || status}</span>;
}
