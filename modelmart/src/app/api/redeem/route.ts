import { z } from "zod";
import { prisma } from "@/lib/db";
import { ok, fail } from "@/lib/api";
import { getCurrentUser, generateOrderNo } from "@/lib/auth";

const schema = z.object({ code: z.string().min(1) });

export async function POST(req: Request) {
  const user = await getCurrentUser();
  if (!user) return fail("未登录", 401);
  let body;
  try {
    body = schema.parse(await req.json());
  } catch {
    return fail("请输入兑换码");
  }
  const code = body.code.trim();
  const rc = await prisma.redeemCode.findUnique({ where: { code } });
  if (!rc) return fail("兑换码不存在");
  if (rc.status !== "unused") return fail("兑换码已被使用或失效");

  await prisma.$transaction([
    prisma.redeemCode.update({
      where: { id: rc.id },
      data: { status: "used", redeemedById: user.id, redeemedAt: new Date() },
    }),
    prisma.user.update({
      where: { id: user.id },
      data: {
        balance: { increment: rc.quota },
        totalRecharge: { increment: rc.quota },
      },
    }),
    prisma.order.create({
      data: {
        userId: user.id,
        orderNo: generateOrderNo(),
        amount: 0,
        quota: rc.quota,
        payMethod: "redeem",
        status: "paid",
        paidAt: new Date(),
      },
    }),
  ]);
  return ok({ quota: rc.quota });
}
