import { prisma } from "@/lib/db";
import { ok, fail } from "@/lib/api";
import { getCurrentUser } from "@/lib/auth";

export async function GET() {
  const user = await getCurrentUser();
  if (!user) return fail("未登录", 401);

  const since = new Date(Date.now() - 7 * 86400000);
  const [logs, tokenCount, recentLogs] = await Promise.all([
    prisma.usageLog.findMany({
      where: { userId: user.id, createdAt: { gte: since } },
      select: { quotaCost: true, createdAt: true },
    }),
    prisma.token.count({ where: { userId: user.id } }),
    prisma.usageLog.findMany({
      where: { userId: user.id },
      orderBy: { createdAt: "desc" },
      take: 6,
    }),
  ]);

  // 近 7 天按天聚合
  const days: { date: string; calls: number; quota: number }[] = [];
  for (let i = 6; i >= 0; i--) {
    const d = new Date(Date.now() - i * 86400000);
    const key = `${d.getMonth() + 1}/${d.getDate()}`;
    days.push({ date: key, calls: 0, quota: 0 });
  }
  const idxOf = (d: Date) => {
    const diff = Math.floor((Date.now() - d.getTime()) / 86400000);
    return 6 - diff;
  };
  let todayCalls = 0;
  let todayQuota = 0;
  const todayStart = new Date();
  todayStart.setHours(0, 0, 0, 0);
  for (const l of logs) {
    const idx = idxOf(new Date(l.createdAt));
    if (idx >= 0 && idx < 7) {
      days[idx].calls += 1;
      days[idx].quota += l.quotaCost;
    }
    if (new Date(l.createdAt) >= todayStart) {
      todayCalls += 1;
      todayQuota += l.quotaCost;
    }
  }

  return ok({
    balance: user.balance,
    totalRecharge: user.totalRecharge,
    totalConsumed: user.totalConsumed,
    tokenCount,
    todayCalls,
    todayQuota,
    series: days,
    recentLogs,
  });
}
