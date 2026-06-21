import { prisma } from "@/lib/db";
import { ok, fail } from "@/lib/api";
import { getCurrentUser } from "@/lib/auth";

// 模拟支付回调: 将订单标记为已支付并到账
// 生产环境应替换为易支付/支付宝的异步回调验签逻辑
export async function POST(_req: Request, ctx: { params: Promise<{ orderNo: string }> }) {
  const user = await getCurrentUser();
  if (!user) return fail("未登录", 401);
  const { orderNo } = await ctx.params;

  const order = await prisma.order.findUnique({ where: { orderNo } });
  if (!order || order.userId !== user.id) return fail("订单不存在", 404);
  if (order.status === "paid") return ok({ order, already: true });
  if (order.status !== "pending") return fail("订单状态异常");

  const [updatedOrder] = await prisma.$transaction([
    prisma.order.update({
      where: { id: order.id },
      data: { status: "paid", paidAt: new Date() },
    }),
    prisma.user.update({
      where: { id: user.id },
      data: {
        balance: { increment: order.quota },
        totalRecharge: { increment: order.quota },
      },
    }),
  ]);
  return ok({ order: updatedOrder });
}
