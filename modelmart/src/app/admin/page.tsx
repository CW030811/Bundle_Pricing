"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/client";
import { fmtYuan } from "@/lib/constants";
import { StatCard, Bars, Badge } from "@/components/ui";
import { Users, Wallet, Coins, Activity, KeyRound, Boxes, Server, TrendingUp } from "lucide-react";

type Overview = {
  totalUsers: number;
  activeTokens: number;
  activeModels: number;
  activeChannels: number;
  revenueCents: number;
  rechargedQuota: number;
  consumedQuota: number;
  estGrossProfitQuota: number;
  totalCalls: number;
  series: { date: string; calls: number; quota: number }[];
  topModels: { modelName: string; quota: number; calls: number }[];
  recentOrders: {
    id: number;
    orderNo: string;
    amount: number;
    quota: number;
    status: string;
    payMethod: string;
    createdAt: string;
    user: { username: string };
  }[];
};

export default function AdminHome() {
  const [d, setD] = useState<Overview | null>(null);
  useEffect(() => {
    api<Overview>("/api/admin/overview").then(setD).catch(() => {});
  }, []);
  if (!d) return <div className="text-slate-400">加载中…</div>;

  const maxTop = Math.max(1, ...d.topModels.map((t) => t.quota));

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">数据看板</h1>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="总营收" value={`¥${(d.revenueCents / 100).toFixed(2)}`} icon={Wallet} accent="text-emerald-300" />
        <StatCard label="累计消费 (流水)" value={fmtYuan(d.consumedQuota)} icon={Coins} accent="text-amber-300" />
        <StatCard label="毛利估算" value={fmtYuan(d.estGrossProfitQuota)} sub="约 35% 毛利率" icon={TrendingUp} accent="text-violet-300" />
        <StatCard label="总调用次数" value={d.totalCalls.toLocaleString()} icon={Activity} />
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="注册用户" value={String(d.totalUsers)} icon={Users} />
        <StatCard label="活跃令牌" value={String(d.activeTokens)} icon={KeyRound} />
        <StatCard label="上架商品" value={String(d.activeModels)} icon={Boxes} />
        <StatCard label="活跃渠道" value={String(d.activeChannels)} icon={Server} />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="card p-5 lg:col-span-2">
          <h2 className="mb-4 font-semibold text-white">近 7 天调用量</h2>
          <Bars data={d.series.map((s) => ({ label: s.date, value: s.calls }))} unit=" 次" />
        </div>
        <div className="card p-5">
          <h2 className="mb-4 font-semibold text-white">热销模型 Top</h2>
          <div className="space-y-3">
            {d.topModels.map((t) => (
              <div key={t.modelName}>
                <div className="flex justify-between text-sm">
                  <span className="text-slate-200">{t.modelName}</span>
                  <span className="text-amber-300">{fmtYuan(t.quota)}</span>
                </div>
                <div className="mt-1 h-1.5 w-full rounded-full bg-white/5">
                  <div
                    className="h-1.5 rounded-full bg-gradient-to-r from-indigo-500 to-violet-500"
                    style={{ width: `${(t.quota / maxTop) * 100}%` }}
                  />
                </div>
              </div>
            ))}
            {d.topModels.length === 0 && <div className="text-sm text-slate-500">暂无数据</div>}
          </div>
        </div>
      </div>

      <div className="card overflow-x-auto">
        <div className="px-5 py-4">
          <h2 className="font-semibold text-white">最近订单</h2>
        </div>
        <table className="w-full min-w-[640px]">
          <thead className="border-y border-white/10">
            <tr>
              <th className="th">订单号</th>
              <th className="th">用户</th>
              <th className="th">金额</th>
              <th className="th">到账</th>
              <th className="th">状态</th>
              <th className="th">时间</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {d.recentOrders.map((o) => (
              <tr key={o.id}>
                <td className="td font-mono text-xs text-slate-400">{o.orderNo}</td>
                <td className="td text-white">{o.user?.username}</td>
                <td className="td text-white">¥{(o.amount / 100).toFixed(2)}</td>
                <td className="td text-emerald-300">{fmtYuan(o.quota)}</td>
                <td className="td">
                  <Badge status={o.status} />
                </td>
                <td className="td text-slate-400">{new Date(o.createdAt).toLocaleString("zh-CN")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
