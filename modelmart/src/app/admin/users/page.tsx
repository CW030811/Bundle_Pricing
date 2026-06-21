"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/client";
import { toast } from "@/components/toast";
import { Modal, Badge } from "@/components/ui";
import { fmtYuan, QUOTA_PER_CNY } from "@/lib/constants";
import { Pencil } from "lucide-react";

type U = {
  id: number;
  username: string;
  email: string | null;
  role: string;
  status: string;
  balance: number;
  totalRecharge: number;
  totalConsumed: number;
  createdAt: string;
};

export default function AdminUsers() {
  const [items, setItems] = useState<U[]>([]);
  const [edit, setEdit] = useState<U | null>(null);
  const [form, setForm] = useState({ balanceYuan: "", role: "user", status: "active" });

  const load = () => api<{ items: U[] }>("/api/admin/users").then((d) => setItems(d.items));
  useEffect(() => {
    load();
  }, []);

  const openEdit = (u: U) => {
    setEdit(u);
    setForm({ balanceYuan: (u.balance / QUOTA_PER_CNY).toString(), role: u.role, status: u.status });
  };

  const save = async () => {
    if (!edit) return;
    try {
      await api(`/api/admin/users/${edit.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          balance: Math.round(Number(form.balanceYuan) * QUOTA_PER_CNY),
          role: form.role,
          status: form.status,
        }),
      });
      toast.ok("已保存");
      setEdit(null);
      load();
    } catch (e) {
      toast.err((e as Error).message);
    }
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">用户管理</h1>
      <div className="card overflow-x-auto">
        <table className="w-full min-w-[820px]">
          <thead className="border-b border-white/10">
            <tr>
              <th className="th">ID</th>
              <th className="th">用户名</th>
              <th className="th">邮箱</th>
              <th className="th">角色</th>
              <th className="th">余额</th>
              <th className="th">累计充值</th>
              <th className="th">累计消费</th>
              <th className="th">状态</th>
              <th className="th">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {items.map((u) => (
              <tr key={u.id}>
                <td className="td text-slate-400">{u.id}</td>
                <td className="td font-medium text-white">{u.username}</td>
                <td className="td text-slate-400">{u.email || "—"}</td>
                <td className="td">
                  {u.role === "admin" ? (
                    <span className="badge bg-violet-500/20 text-violet-300">管理员</span>
                  ) : (
                    <span className="text-slate-400">用户</span>
                  )}
                </td>
                <td className="td text-emerald-300">{fmtYuan(u.balance)}</td>
                <td className="td text-slate-400">{fmtYuan(u.totalRecharge)}</td>
                <td className="td text-amber-300">{fmtYuan(u.totalConsumed)}</td>
                <td className="td">
                  <Badge status={u.status} />
                </td>
                <td className="td">
                  <button className="btn btn-ghost btn-sm" onClick={() => openEdit(u)}>
                    <Pencil className="h-3.5 w-3.5" /> 编辑
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Modal open={!!edit} onClose={() => setEdit(null)} title={`编辑用户 · ${edit?.username}`}>
        <div className="space-y-4">
          <div>
            <label className="label">余额 (元)</label>
            <input
              className="input"
              type="number"
              value={form.balanceYuan}
              onChange={(e) => setForm((f) => ({ ...f, balanceYuan: e.target.value }))}
            />
          </div>
          <div>
            <label className="label">角色</label>
            <select className="input" value={form.role} onChange={(e) => setForm((f) => ({ ...f, role: e.target.value }))}>
              <option value="user">用户</option>
              <option value="admin">管理员</option>
            </select>
          </div>
          <div>
            <label className="label">状态</label>
            <select className="input" value={form.status} onChange={(e) => setForm((f) => ({ ...f, status: e.target.value }))}>
              <option value="active">正常</option>
              <option value="banned">封禁</option>
            </select>
          </div>
          <button className="btn btn-primary w-full" onClick={save}>
            保存
          </button>
        </div>
      </Modal>
    </div>
  );
}
