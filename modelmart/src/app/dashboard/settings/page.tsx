"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/client";
import { toast } from "@/components/toast";
import { Copy } from "lucide-react";

type Me = { username: string; email: string | null; inviteCode: string };

export default function SettingsPage() {
  const [me, setMe] = useState<Me | null>(null);
  const [oldPassword, setOld] = useState("");
  const [newPassword, setNew] = useState("");

  useEffect(() => {
    api<Me>("/api/auth/me").then(setMe);
  }, []);

  const changePw = async () => {
    try {
      await api("/api/user/password", {
        method: "POST",
        body: JSON.stringify({ oldPassword, newPassword }),
      });
      toast.ok("密码已修改");
      setOld("");
      setNew("");
    } catch (e) {
      toast.err((e as Error).message);
    }
  };

  const copy = (s: string) => {
    navigator.clipboard.writeText(s);
    toast.ok("已复制");
  };

  return (
    <div className="max-w-2xl space-y-6">
      <h1 className="text-2xl font-bold text-white">账户设置</h1>

      <div className="card p-6">
        <h2 className="font-semibold text-white">账户信息</h2>
        <dl className="mt-4 space-y-3 text-sm">
          <div className="flex justify-between">
            <dt className="text-slate-400">用户名</dt>
            <dd className="text-white">{me?.username}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-slate-400">邮箱</dt>
            <dd className="text-white">{me?.email || "未绑定"}</dd>
          </div>
          <div className="flex items-center justify-between">
            <dt className="text-slate-400">邀请码</dt>
            <dd className="flex items-center gap-2">
              <code className="font-mono text-white">{me?.inviteCode}</code>
              <button onClick={() => me && copy(me.inviteCode)} className="text-slate-400 hover:text-white">
                <Copy className="h-3.5 w-3.5" />
              </button>
            </dd>
          </div>
        </dl>
      </div>

      <div className="card p-6">
        <h2 className="font-semibold text-white">修改密码</h2>
        <div className="mt-4 space-y-4">
          <div>
            <label className="label">原密码</label>
            <input className="input" type="password" value={oldPassword} onChange={(e) => setOld(e.target.value)} />
          </div>
          <div>
            <label className="label">新密码 (至少 6 位)</label>
            <input className="input" type="password" value={newPassword} onChange={(e) => setNew(e.target.value)} />
          </div>
          <button className="btn btn-primary" onClick={changePw}>
            保存修改
          </button>
        </div>
      </div>
    </div>
  );
}
