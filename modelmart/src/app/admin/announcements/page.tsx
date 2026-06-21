"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/client";
import { toast } from "@/components/toast";
import { Trash2, Pin } from "lucide-react";

type A = { id: number; title: string; content: string; pinned: boolean; createdAt: string };

export default function AdminAnnouncements() {
  const [items, setItems] = useState<A[]>([]);
  const [form, setForm] = useState({ title: "", content: "", pinned: false });

  const load = () => api<{ items: A[] }>("/api/admin/announcements").then((d) => setItems(d.items));
  useEffect(() => {
    load();
  }, []);

  const create = async () => {
    if (!form.title.trim() || !form.content.trim()) return toast.err("请填写标题和内容");
    try {
      await api("/api/admin/announcements", { method: "POST", body: JSON.stringify(form) });
      toast.ok("已发布");
      setForm({ title: "", content: "", pinned: false });
      load();
    } catch (e) {
      toast.err((e as Error).message);
    }
  };

  const del = async (a: A) => {
    if (!confirm("删除该公告?")) return;
    await api(`/api/admin/announcements/${a.id}`, { method: "DELETE" });
    load();
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">公告管理</h1>

      <div className="card space-y-3 p-5">
        <div>
          <label className="label">标题</label>
          <input className="input" value={form.title} onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} />
        </div>
        <div>
          <label className="label">内容</label>
          <textarea
            className="input min-h-[80px]"
            value={form.content}
            onChange={(e) => setForm((f) => ({ ...f, content: e.target.value }))}
          />
        </div>
        <label className="flex items-center gap-2 text-sm text-slate-300">
          <input
            type="checkbox"
            checked={form.pinned}
            onChange={(e) => setForm((f) => ({ ...f, pinned: e.target.checked }))}
          />
          置顶
        </label>
        <button className="btn btn-primary" onClick={create}>发布公告</button>
      </div>

      <div className="space-y-3">
        {items.map((a) => (
          <div key={a.id} className="card flex items-start justify-between gap-4 p-4">
            <div>
              <div className="flex items-center gap-2 font-medium text-white">
                {a.pinned && <Pin className="h-3.5 w-3.5 text-violet-300" />}
                {a.title}
              </div>
              <div className="mt-1 text-sm text-slate-400">{a.content}</div>
              <div className="mt-1 text-xs text-slate-500">{new Date(a.createdAt).toLocaleString("zh-CN")}</div>
            </div>
            <button className="btn btn-ghost btn-sm" onClick={() => del(a)}>
              <Trash2 className="h-3.5 w-3.5 text-rose-300" />
            </button>
          </div>
        ))}
        {items.length === 0 && <div className="text-sm text-slate-500">暂无公告</div>}
      </div>
    </div>
  );
}
