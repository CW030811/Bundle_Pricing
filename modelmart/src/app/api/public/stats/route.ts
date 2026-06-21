import { prisma } from "@/lib/db";
import { ok } from "@/lib/api";

export async function GET() {
  const [models, users, calls] = await Promise.all([
    prisma.modelPrice.count({ where: { status: "active" } }),
    prisma.user.count(),
    prisma.usageLog.count(),
  ]);
  return ok({ models, users, calls, uptime: "99.9%" });
}
