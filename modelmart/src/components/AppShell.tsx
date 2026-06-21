"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, useCallback } from "react";
import { Brand } from "./Brand";
import { api } from "@/lib/client";
import { fmtYuan } from "@/lib/constants";
import { LogOut, Home } from "lucide-react";

type Icon = React.ComponentType<{ className?: string }>;
export type NavItem = { href: string; label: string; icon: Icon };
type Me = { username: string; role: string; balance: number } | null;

export function AppShell({ nav, children }: { nav: NavItem[]; children: React.ReactNode }) {
  const [me, setMe] = useState<Me>(null);
  const path = usePathname();
  const router = useRouter();

  const load = useCallback(() => {
    api<Me>("/api/auth/me")
      .then(setMe)
      .catch(() => router.push("/login"));
  }, [router]);

  useEffect(() => {
    load();
    const onRefresh = () => load();
    window.addEventListener("mm:balance", onRefresh);
    return () => window.removeEventListener("mm:balance", onRefresh);
  }, [load, path]);

  const logout = async () => {
    await fetch("/api/auth/logout", { method: "POST" });
    router.push("/");
  };

  return (
    <div className="min-h-screen md:flex">
      <aside className="fixed inset-y-0 hidden w-64 flex-col border-r border-white/10 bg-[#0a0a12]/70 p-4 backdrop-blur md:flex">
        <div className="px-2 py-2">
          <Brand href={me?.role === "admin" ? "/admin" : "/dashboard"} />
        </div>
        <nav className="mt-5 flex-1 space-y-1">
          {nav.map((n) => {
            const active = path === n.href;
            return (
              <Link
                key={n.href}
                href={n.href}
                className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition ${
                  active
                    ? "border border-indigo-400/30 bg-gradient-to-r from-indigo-500/20 to-violet-500/20 text-white"
                    : "text-slate-300 hover:bg-white/5"
                }`}
              >
                <n.icon className="h-4 w-4" />
                {n.label}
              </Link>
            );
          })}
        </nav>
        <Link href="/" className="mb-2 flex items-center gap-3 rounded-xl px-3 py-2 text-sm text-slate-400 hover:bg-white/5">
          <Home className="h-4 w-4" /> 返回首页
        </Link>
        <div className="card p-3">
          {me && (
            <>
              <div className="text-xs text-slate-400">当前余额</div>
              <div className="text-lg font-bold text-white">{fmtYuan(me.balance)}</div>
              <div className="mt-2 flex items-center justify-between">
                <span className="truncate text-xs text-slate-400">
                  {me.username}
                  {me.role === "admin" && (
                    <span className="badge ml-1 bg-violet-500/20 text-violet-300">管理员</span>
                  )}
                </span>
                <button onClick={logout} className="text-slate-400 hover:text-white" title="退出">
                  <LogOut className="h-4 w-4" />
                </button>
              </div>
            </>
          )}
        </div>
      </aside>

      <div className="flex-1 md:pl-64">
        <div className="sticky top-0 z-30 flex items-center justify-between border-b border-white/10 bg-[#07070d]/85 px-4 py-3 backdrop-blur md:hidden">
          <Brand />
          {me && <span className="text-sm font-semibold text-white">{fmtYuan(me.balance)}</span>}
        </div>
        <div className="flex gap-1 overflow-x-auto border-b border-white/10 px-2 py-2 md:hidden">
          {nav.map((n) => (
            <Link
              key={n.href}
              href={n.href}
              className={`whitespace-nowrap rounded-lg px-3 py-1.5 text-sm ${
                path === n.href ? "bg-white/10 text-white" : "text-slate-300"
              }`}
            >
              {n.label}
            </Link>
          ))}
        </div>
        <main className="mx-auto max-w-6xl p-4 sm:p-6 lg:p-8">{children}</main>
      </div>
    </div>
  );
}
