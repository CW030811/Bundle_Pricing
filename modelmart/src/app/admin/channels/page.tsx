"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/client";
import { toast } from "@/components/toast";
import { Modal, Badge } from "@/components/ui";
import { Plus, Pencil, Trash2 } from "lucide-react";

type Channel = {
  id: number;
  name: string;
  provider: string;
  baseUrl: string;
  apiKey: string;
  models: string;
  weight: number;
  priority: number;
  status: string;
  group: string;
};

const empty = {
  id: 0,
  name: "",
  provider: "openai",
  baseUrl: "https://api.openai.com/v1",
  apiKey: "",
  models: "",
  weight: 1,
  priority: 0,
  status: "active",
  group: "default",
};

export default function AdminChannels() {
  const [items, setItems] = useState<Channel[]>([]);
  const [form, setForm] = useState<Channel>(empty);
  const [open, setOpen] = useState(false);

  const load = () => api<{ items: Channel[] }>("/api/admin/channels").then((d) => setItems(d.items));
  useEffect(() => {
    load();
  }, []);

  const save = async () => {
    try {
      if (form.id) {
        await api(`/api/admin/channels/${form.id}`, { method: "PATCH", body: JSON.stringify(form) });
      } else {
        await api("/api/admin/channels", { method: "POST", body: JSON.stringify(form) });
      }
      toast.ok("已保存");
      setOpen(false);
      load();
    } catch (e) {
      toast.err((e as Error).message);
    }
  };

  const del = async (c: Channel) => {
    if (!confirm(`删除渠道「${c.name}」?`)) return;
    await api(`/api/admin/channels/${c.id}`, { method: "DELETE" });
    toast.ok("已删除");
    load();
  };

  const set = (k: keyof Channel) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">渠道管理</h1>
          <p className="mt-1 text-sm text-slate-400">上游供应商「进货」与「调度」来源, 加权随机 + 优先级路由</p>
        </div>
        <button className="btn btn-primary" onClick={() => { setForm(empty); setOpen(true); }}>
          <Plus className="h-4 w-4" /> 新增渠道
        </button>
      </div>

      <div className="card overflow-x-auto">
        <table className="w-full min-w-[860px]">
          <thead className="border-b border-white/10">
            <tr>
              <th className="th">名称</th>
              <th className="th">供应商</th>
              <th className="th">地址</th>
              <th className="th">模型</th>
              <th className="th">权重/优先级</th>
              <th className="th">状态</th>
              <th className="th">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {items.map((c) => (
              <tr key={c.id}>
                <td className="td font-medium text-white">{c.name}</td>
                <td className="td text-slate-400">{c.provider}</td>
                <td className="td max-w-[180px] truncate text-slate-400">{c.baseUrl}</td>
                <td className="td max-w-[200px] truncate text-slate-400">{c.models}</td>
                <td className="td text-slate-400">{c.weight} / {c.priority}</td>
                <td className="td"><Badge status={c.status} /></td>
                <td className="td">
                  <div className="flex gap-1">
                    <button className="btn btn-ghost btn-sm" onClick={() => { setForm(c); setOpen(true); }}>
                      <Pencil className="h-3.5 w-3.5" />
                    </button>
                    <button className="btn btn-ghost btn-sm" onClick={() => del(c)}>
                      <Trash2 className="h-3.5 w-3.5 text-rose-300" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Modal open={open} onClose={() => setOpen(false)} title={form.id ? "编辑渠道" : "新增渠道"}>
        <div className="space-y-3">
          <div>
            <label className="label">名称</label>
            <input className="input" value={form.name} onChange={set("name")} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">供应商</label>
              <select className="input" value={form.provider} onChange={set("provider")}>
                {["openai", "anthropic", "deepseek", "google", "xai", "alibaba", "mock"].map((p) => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="label">分组</label>
              <input className="input" value={form.group} onChange={set("group")} />
            </div>
          </div>
          <div>
            <label className="label">Base URL</label>
            <input className="input" value={form.baseUrl} onChange={set("baseUrl")} />
          </div>
          <div>
            <label className="label">API Key</label>
            <input className="input" value={form.apiKey} onChange={set("apiKey")} placeholder="sk-..." />
          </div>
          <div>
            <label className="label">支持模型 (逗号分隔)</label>
            <input className="input" value={form.models} onChange={set("models")} placeholder="gpt-5.3,gpt-5.3-mini" />
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="label">权重</label>
              <input className="input" type="number" value={form.weight} onChange={set("weight")} />
            </div>
            <div>
              <label className="label">优先级</label>
              <input className="input" type="number" value={form.priority} onChange={set("priority")} />
            </div>
            <div>
              <label className="label">状态</label>
              <select className="input" value={form.status} onChange={set("status")}>
                <option value="active">启用</option>
                <option value="disabled">禁用</option>
              </select>
            </div>
          </div>
          <button className="btn btn-primary w-full" onClick={save}>保存</button>
        </div>
      </Modal>
    </div>
  );
}
