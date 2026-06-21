"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/client";
import { toast } from "@/components/toast";
import { Badge } from "@/components/ui";
import { fmtYuan } from "@/lib/constants";
import { Copy, Trash2, Ticket } from "lucide-react";

type Code = {
  id: number;
  code: string;
  quota: number;
  status: string;
  createdAt: string;
  redeemedBy: { username: string } | null;
};

export default function AdminRedeem() {
  const [items, setItems] = useState<Code[]>([]);
  const [count, setCount] = useState(5);
  const [quotaYuan, setQuotaYuan] = useState(10);

  const load = () => api<{ items: Code[] }>("/api/admin/redeem?pageSize=100").then((d) => setItems(d.items));
  useEffect(() => {
    load();
  }, []);

  const gen = async () => {
    try {
      await api("/api/admin/redeem", { method: "POST", body: JSON.stringify({ count, quotaYuan }) });
      toast.ok(`已生成 ${count} 个兑换码`);
      load();
    } catch (e) {
      toast.err((e as Error).message);
    }
  };

  const del = async (c: Code) => {
    if (!confirm("删除该兑换码?")) return;
    await api(`/api/admin/redeem/${c.id}`, { method: "DELETE" });
    load();
  };

  const copy = (s: string) => {
    navigator.clipboard.writeText(s);
    toast.ok("已复制");
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">兑换码管理</h1>

      <div className="card flex flex-wrap items-end gap-4 p-5">
        <div>
          <label className="label">生成数量</label>
          <input className="input w-28" type="number" value={count} onChange={(e) => setCount(Number(e.target.value))} />
        </div>
        <div>
          <label className="label">面值 (元)</label>
          <input className="input w-28" type="number" value={quotaYuan} onChange={(e) => setQuotaYuan(Number(e.target.value))} />
        </div>
        <button className="btn btn-primary" onClick={gen}>
          <Ticket className="h-4 w-4" /> 批量生成
        </button>
      </div>

      <div className="card overflow-x-auto">
        <table className="w-full min-w-[680px]">
          <thead className="border-b border-white/10">
            <tr>
              <th className="th">兑换码</th>
              <th className="th">面值</th>
              <th className="th">状态</th>
              <th className="th">使用者</th>
              <th className="th">生成时间</th>
              <th className="th">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {items.map((c) => (
              <tr key={c.id}>
                <td className="td">
                  <div className="flex items-center gap-2">
                    <code className="font-mono text-xs text-slate-200">{c.code}</code>
                    <button onClick={() => copy(c.code)} className="text-slate-400 hover:text-white">
                      <Copy className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </td>
                <td className="td text-emerald-300">{fmtYuan(c.quota)}</td>
                <td className="td"><Badge status={c.status} /></td>
                <td className="td text-slate-400">{c.redeemedBy?.username || "—"}</td>
                <td className="td text-slate-400">{new Date(c.createdAt).toLocaleString("zh-CN")}</td>
                <td className="td">
                  <button className="btn btn-ghost btn-sm" onClick={() => del(c)}>
                    <Trash2 className="h-3.5 w-3.5 text-rose-300" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
