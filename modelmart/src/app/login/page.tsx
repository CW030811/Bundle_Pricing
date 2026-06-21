"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Brand } from "@/components/Brand";
import { api } from "@/lib/client";
import { toast } from "@/components/toast";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const me = await api<{ role: string }>("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      toast.ok("登录成功");
      const next = new URLSearchParams(window.location.search).get("next");
      router.push(next || (me.role === "admin" ? "/admin" : "/dashboard"));
      router.refresh();
    } catch (e) {
      toast.err((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="grid min-h-screen place-items-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex justify-center">
          <Brand />
        </div>
        <div className="card p-7">
          <h1 className="text-xl font-bold text-white">欢迎回来</h1>
          <p className="mt-1 text-sm text-slate-400">登录你的 ModelMart 账户</p>
          <form onSubmit={submit} className="mt-6 space-y-4">
            <div>
              <label className="label">用户名 / 邮箱</label>
              <input
                className="input"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="demo"
                autoFocus
              />
            </div>
            <div>
              <label className="label">密码</label>
              <input
                className="input"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
              />
            </div>
            <button className="btn btn-primary w-full" disabled={loading}>
              {loading ? "登录中…" : "登录"}
            </button>
          </form>
          <p className="mt-5 text-center text-sm text-slate-400">
            还没有账户?{" "}
            <Link href="/register" className="link">
              免费注册
            </Link>
          </p>
        </div>
        <div className="card mt-4 p-4 text-center text-xs text-slate-400">
          演示账号 — 用户 <b className="text-slate-200">demo / demo1234</b> · 管理员{" "}
          <b className="text-slate-200">admin / admin1234</b>
        </div>
      </div>
    </main>
  );
}
