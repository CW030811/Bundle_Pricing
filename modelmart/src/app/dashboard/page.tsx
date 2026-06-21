"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/client";
import { fmtYuan, quotaToYuan } from "@/lib/constants";
import { StatCard, Bars } from "@/components/ui";
import { Wallet, TrendingUp, Coins, Activity } from "lucide-react";

type Log = {
  id: number;
  modelName: string;
  promptTokens: number;
  completionTokens: number;
  quotaCost: number;
  createdAt: string;
};
type Dash = {
  balance: number;
  totalRecharge: number;
  totalConsumed: number;
  tokenCount: number;
  todayCalls: number;
  todayQuota: number;
  series: { date: string; calls: number; quota: number }[];
  recentLogs: Log[];
};

export default function DashboardHome() {
  const [d, setD] = useState<Dash | null>(null);
  useEffect(() => {
    api<Dash>("/api/dashboard").then(setD).catch(() => {});
  }, []);

  if (!d) return <div className="text-slate-400">加载中…</div>;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">概览</h1>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="账户余额" value={fmtYuan(d.balance)} icon={Wallet} accent="text-emerald-300" />
        <StatCard label="累计充值" value={fmtYuan(d.totalRecharge)} icon={TrendingUp} />
        <StatCard label="累计消费" value={fmtYuan(d.totalConsumed)} icon={Coins} accent="text-amber-300" />
        <StatCard
          label="今日调用"
          value={String(d.todayCalls)}
          sub={`消费 ${fmtYuan(d.todayQuota)}`}
          icon={Activity}
          accent="text-violet-300"
        />
      </div>

      <div className="card p-5">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-semibold text-white">近 7 天消费 (元)</h2>
          <span className="text-xs text-slate-400">令牌 {d.tokenCount} 个</span>
        </div>
        <Bars
          data={d.series.map((s) => ({ label: s.date, value: Number(quotaToYuan(s.quota).toFixed(2)) }))}
          unit="元"
        />
      </div>

      <div className="card overflow-x-auto">
        <div className="px-5 py-4">
          <h2 className="font-semibold text-white">最近调用</h2>
        </div>
        <table className="w-full min-w-[520px]">
          <thead className="border-y border-white/10">
            <tr>
              <th className="th">时间</th>
              <th className="th">模型</th>
              <th className="th">Tokens (入+出)</th>
              <th className="th">消费</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {d.recentLogs.map((l) => (
              <tr key={l.id}>
                <td className="td text-slate-400">{new Date(l.createdAt).toLocaleString("zh-CN")}</td>
                <td className="td text-white">{l.modelName}</td>
                <td className="td text-slate-400">
                  {l.promptTokens} + {l.completionTokens}
                </td>
                <td className="td text-amber-300">{fmtYuan(l.quotaCost)}</td>
              </tr>
            ))}
            {d.recentLogs.length === 0 && (
              <tr>
                <td className="td text-slate-500" colSpan={4}>
                  暂无调用记录 — 去「接入文档」试试中转接口
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
