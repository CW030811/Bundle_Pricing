"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Brand } from "./Brand";
import { api } from "@/lib/client";
import { LogOut, LayoutDashboard } from "lucide-react";

type Me = { username: string; role: string } | null;
const nav = [
  { href: "/", label: "首页" },
  { href: "/pricing", label: "模型定价" },
  { href: "/docs", label: "接入文档" },
];

export function SiteHeader() {
  const [me, setMe] = useState<Me>(null);
  const [ready, setReady] = useState(false);
  const path = usePathname();
  const router = useRouter();

  useEffect(() => {
    api<Me>("/api/auth/me")
      .then(setMe)
      .catch(() => setMe(null))
      .finally(() => setReady(true));
  }, []);

  const logout = async () => {
    await fetch("/api/auth/logout", { method: "POST" });
    setMe(null);
    router.push("/");
    router.refresh();
  };

  return (
    <header className="sticky top-0 z-40 border-b border-white/10 bg-[#07070d]/70 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6">
        <div className="flex items-center gap-8">
          <Brand />
          <nav className="hidden items-center gap-1 md:flex">
            {nav.map((n) => (
              <Link
                key={n.href}
                href={n.href}
                className={`rounded-lg px-3 py-2 text-sm transition ${
                  path === n.href
                    ? "bg-white/10 text-white"
                    : "text-slate-300 hover:text-white"
                }`}
              >
                {n.label}
              </Link>
            ))}
          </nav>
        </div>
        <div className="flex items-center gap-2">
          {!ready ? (
            <div className="h-8 w-20" />
          ) : me ? (
            <>
              <Link
                href={me.role === "admin" ? "/admin" : "/dashboard"}
                className="btn btn-ghost btn-sm"
              >
                <LayoutDashboard className="h-4 w-4" />
                控制台
              </Link>
              <button onClick={logout} className="btn btn-ghost btn-sm" title="退出登录">
                <LogOut className="h-4 w-4" />
              </button>
            </>
          ) : (
            <>
              <Link href="/login" className="btn btn-ghost btn-sm">
                登录
              </Link>
              <Link href="/register" className="btn btn-primary btn-sm">
                免费注册
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
