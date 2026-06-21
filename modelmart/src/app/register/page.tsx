"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Brand } from "@/components/Brand";
import { api } from "@/lib/client";
import { toast } from "@/components/toast";

export default function RegisterPage() {
  const router = useRouter();
  const [form, setForm] = useState({ username: "", email: "", password: "", inviteCode: "" });
  const [loading, setLoading] = useState(false);
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      await api("/api/auth/register", { method: "POST", body: JSON.stringify(form) });
      toast.ok("注册成功, 已赠送 ¥2 体验额度");
      router.push("/dashboard");
      router.refresh();
    } catch (e) {
      toast.err((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="grid min-h-screen place-items-center px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex justify-center">
          <Brand />
        </div>
        <div className="card p-7">
          <h1 className="text-xl font-bold text-white">创建账户</h1>
          <p className="mt-1 text-sm text-slate-400">注册即送 ¥2 体验额度</p>
          <form onSubmit={submit} className="mt-6 space-y-4">
            <div>
              <label className="label">用户名 *</label>
              <input className="input" value={form.username} onChange={set("username")} placeholder="3-20 位" autoFocus />
            </div>
            <div>
              <label className="label">邮箱 (可选)</label>
              <input className="input" value={form.email} onChange={set("email")} placeholder="you@example.com" />
            </div>
            <div>
              <label className="label">密码 *</label>
              <input className="input" type="password" value={form.password} onChange={set("password")} placeholder="至少 6 位" />
            </div>
            <div>
              <label className="label">邀请码 (可选)</label>
              <input className="input" value={form.inviteCode} onChange={set("inviteCode")} placeholder="填写好友邀请码" />
            </div>
            <button className="btn btn-primary w-full" disabled={loading}>
              {loading ? "注册中…" : "注册并领取额度"}
            </button>
          </form>
          <p className="mt-5 text-center text-sm text-slate-400">
            已有账户?{" "}
            <Link href="/login" className="link">
              去登录
            </Link>
          </p>
        </div>
      </div>
    </main>
  );
}
