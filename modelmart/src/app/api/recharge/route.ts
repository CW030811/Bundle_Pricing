import { z } from "zod";
import { prisma } from "@/lib/db";
import { ok, fail } from "@/lib/api";
import { getCurrentUser, generateOrderNo } from "@/lib/auth";
import { QUOTA_PER_CNY } from "@/lib/constants";

// 列出当前用户订单 (财务流水)
export async function GET() {
  const user = await getCurrentUser();
  if (!user) return fail("未登录", 401);
  const orders = await prisma.order.findMany({
    where: { userId: user.id },
    orderBy: { createdAt: "desc" },
    take: 50,
  });
  return ok({ orders });
}

const schema = z.object({
  amount: z.number().int().min(1).max(20000), // 充值金额(元)
  payMethod: z.enum(["mock", "alipay", "wechat"]).default("mock"),
});

// 创建充值订单 (模拟支付: 返回订单号, 由 /pay 接口模拟回调到账)
export async function POST(req: Request) {
  const user = await getCurrentUser();
  if (!user) return fail("未登录", 401);
  let body;
  try {
    body = schema.parse(await req.json());
  } catch {
    return fail("充值金额需在 1~20000 元之间");
  }
  // 满 100 赠 10%
  const bonus = body.amount >= 100 ? Math.floor(body.amount * 0.1) : 0;
  const quota = (body.amount + bonus) * QUOTA_PER_CNY;
  const order = await prisma.order.create({
    data: {
      userId: user.id,
      orderNo: generateOrderNo(),
      amount: body.amount * 100, // 分
      quota,
      payMethod: body.payMethod,
      status: "pending",
    },
  });
  return ok({ order, bonus });
}
