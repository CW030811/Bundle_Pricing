"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/client";
import { toast } from "@/components/toast";
import { Modal, Badge } from "@/components/ui";
import { pricePerMillionYuan, QUOTA_PER_CNY, CATEGORIES } from "@/lib/constants";
import { Plus, Pencil, Trash2 } from "lucide-react";

type Model = {
  id: number;
  name: string;
  displayName: string;
  provider: string;
  category: string;
  priceInput: number;
  priceOutput: number;
  description: string;
  tag: string;
  status: string;
  sortOrder: number;
};

type Form = {
  id: number;
  name: string;
  displayName: string;
  provider: string;
  category: string;
  priceInYuan: string;
  priceOutYuan: string;
  description: string;
  tag: string;
  status: string;
  sortOrder: number;
};

const empty: Form = {
  id: 0,
  name: "",
  displayName: "",
  provider: "openai",
  category: "chat",
  priceInYuan: "0",
  priceOutYuan: "0",
  description: "",
  tag: "",
  status: "active",
  sortOrder: 100,
};

export default function AdminModels() {
  const [items, setItems] = useState<Model[]>([]);
  const [form, setForm] = useState<Form>(empty);
  const [open, setOpen] = useState(false);

  const load = () => api<{ items: Model[] }>("/api/admin/models?pageSize=100").then((d) => setItems(d.items));
  useEffect(() => {
    load();
  }, []);

  const openEdit = (m: Model) =>
    setForm({
      id: m.id,
      name: m.name,
      displayName: m.displayName,
      provider: m.provider,
      category: m.category,
      priceInYuan: pricePerMillionYuan(m.priceInput).toString(),
      priceOutYuan: pricePerMillionYuan(m.priceOutput).toString(),
      description: m.description,
      tag: m.tag,
      status: m.status,
      sortOrder: m.sortOrder,
    });

  const save = async () => {
    const payload = {
      name: form.name,
      displayName: form.displayName,
      provider: form.provider,
      category: form.category,
      priceInput: Math.round(Number(form.priceInYuan) * QUOTA_PER_CNY),
      priceOutput: Math.round(Number(form.priceOutYuan) * QUOTA_PER_CNY),
      description: form.description,
      tag: form.tag,
      status: form.status,
      sortOrder: Number(form.sortOrder),
    };
    try {
      if (form.id) await api(`/api/admin/models/${form.id}`, { method: "PATCH", body: JSON.stringify(payload) });
      else await api("/api/admin/models", { method: "POST", body: JSON.stringify(payload) });
      toast.ok("已保存");
      setOpen(false);
      load();
    } catch (e) {
      toast.err((e as Error).message);
    }
  };

  const del = async (m: Model) => {
    if (!confirm(`删除商品「${m.displayName}」?`)) return;
    await api(`/api/admin/models/${m.id}`, { method: "DELETE" });
    toast.ok("已删除");
    load();
  };

  const set = (k: keyof Form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">商品管理</h1>
          <p className="mt-1 text-sm text-slate-400">模型 / 智能体 / MCP / Skill 货架与定价</p>
        </div>
        <button className="btn btn-primary" onClick={() => { setForm(empty); setOpen(true); }}>
          <Plus className="h-4 w-4" /> 上架商品
        </button>
      </div>

      <div className="card overflow-x-auto">
        <table className="w-full min-w-[860px]">
          <thead className="border-b border-white/10">
            <tr>
              <th className="th">显示名</th>
              <th className="th">模型 ID</th>
              <th className="th">分类</th>
              <th className="th">输入¥/M</th>
              <th className="th">输出¥/M</th>
              <th className="th">状态</th>
              <th className="th">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {items.map((m) => (
              <tr key={m.id}>
                <td className="td font-medium text-white">
                  {m.displayName}
                  {m.tag && <span className="badge ml-2 bg-violet-500/15 text-violet-300">{m.tag}</span>}
                </td>
                <td className="td font-mono text-xs text-slate-400">{m.name}</td>
                <td className="td text-slate-400">{CATEGORIES[m.category] || m.category}</td>
                <td className="td text-white">¥{pricePerMillionYuan(m.priceInput).toFixed(2)}</td>
                <td className="td text-white">¥{pricePerMillionYuan(m.priceOutput).toFixed(2)}</td>
                <td className="td"><Badge status={m.status} /></td>
                <td className="td">
                  <div className="flex gap-1">
                    <button className="btn btn-ghost btn-sm" onClick={() => { openEdit(m); setOpen(true); }}>
                      <Pencil className="h-3.5 w-3.5" />
                    </button>
                    <button className="btn btn-ghost btn-sm" onClick={() => del(m)}>
                      <Trash2 className="h-3.5 w-3.5 text-rose-300" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Modal open={open} onClose={() => setOpen(false)} title={form.id ? "编辑商品" : "上架商品"}>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">显示名</label>
              <input className="input" value={form.displayName} onChange={set("displayName")} />
            </div>
            <div>
              <label className="label">模型 ID</label>
              <input className="input" value={form.name} onChange={set("name")} placeholder="gpt-5.3" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">供应商</label>
              <input className="input" value={form.provider} onChange={set("provider")} />
            </div>
            <div>
              <label className="label">分类</label>
              <select className="input" value={form.category} onChange={set("category")}>
                {Object.entries(CATEGORIES).map(([k, v]) => (
                  <option key={k} value={k}>{v}</option>
                ))}
              </select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">输入价 (¥/百万 tokens)</label>
              <input className="input" type="number" step="0.01" value={form.priceInYuan} onChange={set("priceInYuan")} />
            </div>
            <div>
              <label className="label">输出价 (¥/百万 / 次)</label>
              <input className="input" type="number" step="0.01" value={form.priceOutYuan} onChange={set("priceOutYuan")} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">标签</label>
              <input className="input" value={form.tag} onChange={set("tag")} placeholder="热门 / 新品" />
            </div>
            <div>
              <label className="label">排序</label>
              <input className="input" type="number" value={form.sortOrder} onChange={set("sortOrder")} />
            </div>
          </div>
          <div>
            <label className="label">描述</label>
            <input className="input" value={form.description} onChange={set("description")} />
          </div>
          <div>
            <label className="label">状态</label>
            <select className="input" value={form.status} onChange={set("status")}>
              <option value="active">上架</option>
              <option value="offline">下架</option>
            </select>
          </div>
          <button className="btn btn-primary w-full" onClick={save}>保存</button>
        </div>
      </Modal>
    </div>
  );
}
