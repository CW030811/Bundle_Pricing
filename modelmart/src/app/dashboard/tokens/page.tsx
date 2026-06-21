"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/client";
import { toast } from "@/components/toast";
import { Modal, Badge } from "@/components/ui";
import { fmtYuan } from "@/lib/constants";
import { Plus, Copy, Eye, EyeOff, Power, Trash2 } from "lucide-react";

type Token = {
  id: number;
  name: string;
  key: string;
  status: string;
  quotaLimit: number | null;
  usedQuota: number;
  createdAt: string;
};

export default function TokensPage() {
  const [tokens, setTokens] = useState<Token[]>([]);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [limit, setLimit] = useState("");
  const [show, setShow] = useState<Record<number, boolean>>({});

  const load = () => api<{ tokens: Token[] }>("/api/tokens").then((d) => setTokens(d.tokens));
  useEffect(() => {
    load();
  }, []);

  const create = async () => {
    if (!name.trim()) return toast.err("请填写令牌名称");
    try {
      await api("/api/tokens", {
        method: "POST",
        body: JSON.stringify({
          name,
          quotaLimitYuan: limit ? Number(limit) : undefined,
        }),
      });
      toast.ok("令牌已创建");
      setOpen(false);
      setName("");
      setLimit("");
      load();
    } catch (e) {
      toast.err((e as Error).message);
    }
  };

  const toggle = async (t: Token) => {
    await api(`/api/tokens/${t.id}`, {
      method: "PATCH",
      body: JSON.stringify({ status: t.status === "active" ? "disabled" : "active" }),
    });
    load();
  };

  const del = async (t: Token) => {
    if (!confirm(`确认删除令牌「${t.name}」?`)) return;
    await api(`/api/tokens/${t.id}`, { method: "DELETE" });
    toast.ok("已删除");
    load();
  };

  const copy = (k: string) => {
    navigator.clipboard.writeText(k);
    toast.ok("已复制到剪贴板");
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">令牌管理</h1>
        <button className="btn btn-primary" onClick={() => setOpen(true)}>
          <Plus className="h-4 w-4" /> 新建令牌
        </button>
      </div>

      <div className="card overflow-x-auto">
        <table className="w-full min-w-[720px]">
          <thead className="border-b border-white/10">
            <tr>
              <th className="th">名称</th>
              <th className="th">密钥</th>
              <th className="th">已用 / 限额</th>
              <th className="th">状态</th>
              <th className="th">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {tokens.map((t) => (
              <tr key={t.id}>
                <td className="td font-medium text-white">{t.name}</td>
                <td className="td">
                  <div className="flex items-center gap-2">
                    <code className="font-mono text-xs text-slate-300">
                      {show[t.id] ? t.key : t.key.slice(0, 8) + "••••••••" + t.key.slice(-4)}
                    </code>
                    <button onClick={() => setShow((s) => ({ ...s, [t.id]: !s[t.id] }))} className="text-slate-400 hover:text-white">
                      {show[t.id] ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                    </button>
                    <button onClick={() => copy(t.key)} className="text-slate-400 hover:text-white">
                      <Copy className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </td>
                <td className="td text-slate-400">
                  {fmtYuan(t.usedQuota)} / {t.quotaLimit == null ? "不限" : fmtYuan(t.quotaLimit)}
                </td>
                <td className="td">
                  <Badge status={t.status} />
                </td>
                <td className="td">
                  <div className="flex gap-1">
                    <button onClick={() => toggle(t)} className="btn btn-ghost btn-sm" title="启用/禁用">
                      <Power className="h-3.5 w-3.5" />
                    </button>
                    <button onClick={() => del(t)} className="btn btn-ghost btn-sm" title="删除">
                      <Trash2 className="h-3.5 w-3.5 text-rose-300" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {tokens.length === 0 && (
              <tr>
                <td className="td text-slate-500" colSpan={5}>
                  暂无令牌, 点击右上角新建
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <Modal open={open} onClose={() => setOpen(false)} title="新建令牌">
        <div className="space-y-4">
          <div>
            <label className="label">令牌名称</label>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="如: 生产环境" />
          </div>
          <div>
            <label className="label">额度上限 (元, 留空表示不限)</label>
            <input className="input" type="number" value={limit} onChange={(e) => setLimit(e.target.value)} placeholder="不限" />
          </div>
          <button className="btn btn-primary w-full" onClick={create}>
            创建
          </button>
        </div>
      </Modal>
    </div>
  );
}
