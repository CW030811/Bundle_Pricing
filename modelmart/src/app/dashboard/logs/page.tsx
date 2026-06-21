"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/client";
import { fmtYuan } from "@/lib/constants";
import { ChevronLeft, ChevronRight } from "lucide-react";

type Log = {
  id: number;
  modelName: string;
  promptTokens: number;
  completionTokens: number;
  quotaCost: number;
  channelName: string;
  createdAt: string;
};
type Data = { items: Log[]; total: number; page: number; pageSize: number };

export default function LogsPage() {
  const [data, setData] = useState<Data | null>(null);
  const [page, setPage] = useState(1);

  useEffect(() => {
    api<Data>(`/api/logs?page=${page}&pageSize=20`).then(setData);
  }, [page]);

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.pageSize)) : 1;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">账单日志</h1>

      <div className="card overflow-x-auto">
        <table className="w-full min-w-[720px]">
          <thead className="border-b border-white/10">
            <tr>
              <th className="th">时间</th>
              <th className="th">模型</th>
              <th className="th">输入</th>
              <th className="th">输出</th>
              <th className="th">渠道</th>
              <th className="th">消费</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {data?.items.map((l) => (
              <tr key={l.id}>
                <td className="td text-slate-400">{new Date(l.createdAt).toLocaleString("zh-CN")}</td>
                <td className="td text-white">{l.modelName}</td>
                <td className="td text-slate-400">{l.promptTokens}</td>
                <td className="td text-slate-400">{l.completionTokens}</td>
                <td className="td text-slate-400">{l.channelName}</td>
                <td className="td text-amber-300">{fmtYuan(l.quotaCost)}</td>
              </tr>
            ))}
            {data && data.items.length === 0 && (
              <tr>
                <td className="td text-slate-500" colSpan={6}>
                  暂无调用记录
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between text-sm text-slate-400">
        <span>共 {data?.total ?? 0} 条</span>
        <div className="flex items-center gap-2">
          <button
            className="btn btn-ghost btn-sm"
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <span>
            {page} / {totalPages}
          </span>
          <button
            className="btn btn-ghost btn-sm"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
