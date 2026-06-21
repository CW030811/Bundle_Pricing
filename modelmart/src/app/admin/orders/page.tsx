"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/client";
import { Badge } from "@/components/ui";
import { fmtYuan } from "@/lib/constants";

type O = {
  id: number;
  orderNo: string;
  amount: number;
  quota: number;
  payMethod: string;
  status: string;
  createdAt: string;
  user: { username: string };
};
const payText: Record<string, string> = { mock: "模拟支付", redeem: "兑换码", alipay: "支付宝", wechat: "微信" };

export default function AdminOrders() {
  const [items, setItems] = useState<O[]>([]);
  useEffect(() => {
    api<{ items: O[] }>("/api/admin/orders?pageSize=100").then((d) => setItems(d.items));
  }, []);

  const total = items.filter((o) => o.status === "paid").reduce((s, o) => s + o.amount, 0);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">订单 / 财务</h1>
        <span className="text-sm text-slate-400">
          已支付总额 <b className="text-emerald-300">¥{(total / 100).toFixed(2)}</b>
        </span>
      </div>
      <div className="card overflow-x-auto">
        <table className="w-full min-w-[760px]">
          <thead className="border-b border-white/10">
            <tr>
              <th className="th">订单号</th>
              <th className="th">用户</th>
              <th className="th">金额</th>
              <th className="th">到账额度</th>
              <th className="th">方式</th>
              <th className="th">状态</th>
              <th className="th">时间</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {items.map((o) => (
              <tr key={o.id}>
                <td className="td font-mono text-xs text-slate-400">{o.orderNo}</td>
                <td className="td text-white">{o.user?.username}</td>
                <td className="td text-white">¥{(o.amount / 100).toFixed(2)}</td>
                <td className="td text-emerald-300">{fmtYuan(o.quota)}</td>
                <td className="td text-slate-400">{payText[o.payMethod] || o.payMethod}</td>
                <td className="td"><Badge status={o.status} /></td>
                <td className="td text-slate-400">{new Date(o.createdAt).toLocaleString("zh-CN")}</td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr><td className="td text-slate-500" colSpan={7}>暂无订单</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
