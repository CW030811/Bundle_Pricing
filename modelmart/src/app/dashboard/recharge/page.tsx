"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/client";
import { toast } from "@/components/toast";
import { Modal, Badge } from "@/components/ui";
import { fmtYuan } from "@/lib/constants";
import { QrCode, Gift } from "lucide-react";

const presets = [10, 50, 100, 200, 500, 1000];
type Order = {
  id: number;
  orderNo: string;
  amount: number;
  quota: number;
  payMethod: string;
  status: string;
  createdAt: string;
};
type Pending = { order: Order; bonus: number };

const payText: Record<string, string> = { mock: "模拟支付", redeem: "兑换码", alipay: "支付宝", wechat: "微信" };

export default function RechargePage() {
  const [amount, setAmount] = useState(100);
  const [orders, setOrders] = useState<Order[]>([]);
  const [pending, setPending] = useState<Pending | null>(null);
  const [code, setCode] = useState("");

  const load = () => api<{ orders: Order[] }>("/api/recharge").then((d) => setOrders(d.orders));
  useEffect(() => {
    load();
  }, []);

  const start = async () => {
    if (amount < 1) return toast.err("金额不正确");
    try {
      const d = await api<Pending>("/api/recharge", {
        method: "POST",
        body: JSON.stringify({ amount, payMethod: "mock" }),
      });
      setPending(d);
    } catch (e) {
      toast.err((e as Error).message);
    }
  };

  const pay = async () => {
    if (!pending) return;
    try {
      await api(`/api/recharge/${pending.order.orderNo}`, { method: "POST" });
      toast.ok("充值成功, 额度已到账");
      setPending(null);
      load();
      window.dispatchEvent(new Event("mm:balance"));
    } catch (e) {
      toast.err((e as Error).message);
    }
  };

  const redeem = async () => {
    if (!code.trim()) return toast.err("请输入兑换码");
    try {
      const d = await api<{ quota: number }>("/api/redeem", {
        method: "POST",
        body: JSON.stringify({ code }),
      });
      toast.ok(`兑换成功, 到账 ${fmtYuan(d.quota)}`);
      setCode("");
      load();
      window.dispatchEvent(new Event("mm:balance"));
    } catch (e) {
      toast.err((e as Error).message);
    }
  };

  const bonus = amount >= 100 ? Math.floor(amount * 0.1) : 0;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">充值中心</h1>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="card p-6 lg:col-span-2">
          <h2 className="font-semibold text-white">选择充值金额</h2>
          <div className="mt-4 grid grid-cols-3 gap-3">
            {presets.map((p) => (
              <button
                key={p}
                onClick={() => setAmount(p)}
                className={`rounded-xl border p-4 text-center transition ${
                  amount === p
                    ? "border-indigo-400/60 bg-indigo-500/15"
                    : "border-white/10 hover:bg-white/5"
                }`}
              >
                <div className="text-xl font-bold text-white">¥{p}</div>
                {p >= 100 && <div className="text-xs text-emerald-300">送 {Math.floor(p * 0.1)}</div>}
              </button>
            ))}
          </div>
          <div className="mt-4 flex items-center gap-3">
            <span className="text-sm text-slate-400">自定义</span>
            <input
              type="number"
              className="input max-w-[160px]"
              value={amount}
              onChange={(e) => setAmount(Number(e.target.value))}
            />
            <span className="text-sm text-slate-400">元</span>
          </div>
          <div className="mt-5 flex items-center justify-between border-t border-white/10 pt-4">
            <div className="text-sm text-slate-400">
              实付 <b className="text-white">¥{amount}</b>
              {bonus > 0 && <span className="text-emerald-300"> + 赠 ¥{bonus}</span>}
            </div>
            <button className="btn btn-primary" onClick={start}>
              立即支付
            </button>
          </div>
        </div>

        <div className="card p-6">
          <h2 className="flex items-center gap-2 font-semibold text-white">
            <Gift className="h-4 w-4 text-violet-300" /> 兑换码
          </h2>
          <p className="mt-1 text-sm text-slate-400">输入兑换码直接到账额度</p>
          <input
            className="input mt-4"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="XXXX-XXXX-XXXX"
          />
          <button className="btn btn-ghost mt-3 w-full" onClick={redeem}>
            兑换
          </button>
        </div>
      </div>

      <div className="card overflow-x-auto">
        <div className="px-5 py-4">
          <h2 className="font-semibold text-white">充值记录</h2>
        </div>
        <table className="w-full min-w-[640px]">
          <thead className="border-y border-white/10">
            <tr>
              <th className="th">订单号</th>
              <th className="th">金额</th>
              <th className="th">到账额度</th>
              <th className="th">方式</th>
              <th className="th">状态</th>
              <th className="th">时间</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {orders.map((o) => (
              <tr key={o.id}>
                <td className="td font-mono text-xs text-slate-400">{o.orderNo}</td>
                <td className="td text-white">¥{(o.amount / 100).toFixed(2)}</td>
                <td className="td text-emerald-300">{fmtYuan(o.quota)}</td>
                <td className="td text-slate-400">{payText[o.payMethod] || o.payMethod}</td>
                <td className="td">
                  <Badge status={o.status} />
                </td>
                <td className="td text-slate-400">{new Date(o.createdAt).toLocaleString("zh-CN")}</td>
              </tr>
            ))}
            {orders.length === 0 && (
              <tr>
                <td className="td text-slate-500" colSpan={6}>
                  暂无充值记录
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <Modal open={!!pending} onClose={() => setPending(null)} title="扫码支付 (演示)">
        {pending && (
          <div className="flex flex-col items-center gap-4 text-center">
            <div className="grid h-44 w-44 place-items-center rounded-xl bg-white">
              <QrCode className="h-32 w-32 text-black" />
            </div>
            <div className="text-sm text-slate-400">
              订单 <span className="font-mono">{pending.order.orderNo}</span>
            </div>
            <div className="text-2xl font-bold text-white">
              ¥{(pending.order.amount / 100).toFixed(2)}
              {pending.bonus > 0 && (
                <span className="ml-2 text-sm text-emerald-300">赠 ¥{pending.bonus}</span>
              )}
            </div>
            <p className="text-xs text-slate-500">
              演示环境不接真实支付。点击下方按钮模拟「支付成功」回调。
            </p>
            <button className="btn btn-primary w-full" onClick={pay}>
              我已支付 (模拟成功)
            </button>
          </div>
        )}
      </Modal>
    </div>
  );
}
