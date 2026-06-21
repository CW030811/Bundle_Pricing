import { prisma } from "@/lib/db";
import { ok, fail } from "@/lib/api";
import { requireAdmin } from "@/lib/admin";

export async function GET() {
  const admin = await requireAdmin();
  if (!admin) return fail("无权限", 403);

  const since = new Date(Date.now() - 7 * 86400000);
  const [
    totalUsers,
    activeTokens,
    activeModels,
    activeChannels,
    paidAgg,
    consumeAgg,
    logs,
    topModels,
    recentOrders,
  ] = await Promise.all([
    prisma.user.count(),
    prisma.token.count({ where: { status: "active" } }),
    prisma.modelPrice.count({ where: { status: "active" } }),
    prisma.channel.count({ where: { status: "active" } }),
    prisma.order.aggregate({ where: { status: "paid" }, _sum: { amount: true, quota: true } }),
    prisma.usageLog.aggregate({ _sum: { quotaCost: true }, _count: { _all: true } }),
    prisma.usageLog.findMany({
      where: { createdAt: { gte: since } },
      select: { quotaCost: true, createdAt: true },
    }),
    prisma.usageLog.groupBy({
      by: ["modelName"],
      _sum: { quotaCost: true },
      _count: { _all: true },
      orderBy: { _sum: { quotaCost: "desc" } },
      take: 6,
    }),
    prisma.order.findMany({
      orderBy: { createdAt: "desc" },
      take: 8,
      include: { user: { select: { username: true } } },
    }),
  ]);

  const days: { date: string; calls: number; quota: number }[] = [];
  for (let i = 6; i >= 0; i--) {
    const d = new Date(Date.now() - i * 86400000);
    days.push({ date: `${d.getMonth() + 1}/${d.getDate()}`, calls: 0, quota: 0 });
  }
  for (const l of logs) {
    const diff = Math.floor((Date.now() - new Date(l.createdAt).getTime()) / 86400000);
    const idx = 6 - diff;
    if (idx >= 0 && idx < 7) {
      days[idx].calls += 1;
      days[idx].quota += l.quotaCost;
    }
  }

  const consumedQuota = consumeAgg._sum.quotaCost || 0;
  return ok({
    totalUsers,
    activeTokens,
    activeModels,
    activeChannels,
    revenueCents: paidAgg._sum.amount || 0,
    rechargedQuota: paidAgg._sum.quota || 0,
    consumedQuota,
    estGrossProfitQuota: Math.round(consumedQuota * 0.35),
    totalCalls: consumeAgg._count._all || 0,
    series: days,
    topModels: topModels.map((t) => ({
      modelName: t.modelName,
      quota: t._sum.quotaCost || 0,
      calls: t._count._all,
    })),
    recentOrders,
  });
}
