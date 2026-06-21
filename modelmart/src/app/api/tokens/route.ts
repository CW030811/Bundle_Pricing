import { z } from "zod";
import { prisma } from "@/lib/db";
import { ok, fail } from "@/lib/api";
import { getCurrentUser, generateApiKey } from "@/lib/auth";
import { QUOTA_PER_CNY } from "@/lib/constants";

export async function GET() {
  const user = await getCurrentUser();
  if (!user) return fail("未登录", 401);
  const tokens = await prisma.token.findMany({
    where: { userId: user.id },
    orderBy: { createdAt: "desc" },
  });
  return ok({ tokens });
}

const schema = z.object({
  name: z.string().min(1).max(40),
  quotaLimitYuan: z.number().nonnegative().optional(),
  expiresAt: z.string().optional(),
});

export async function POST(req: Request) {
  const user = await getCurrentUser();
  if (!user) return fail("未登录", 401);
  let body;
  try {
    body = schema.parse(await req.json());
  } catch {
    return fail("参数不合法");
  }
  const token = await prisma.token.create({
    data: {
      userId: user.id,
      name: body.name,
      key: generateApiKey(),
      quotaLimit: body.quotaLimitYuan ? Math.round(body.quotaLimitYuan * QUOTA_PER_CNY) : null,
      expiresAt: body.expiresAt ? new Date(body.expiresAt) : null,
    },
  });
  return ok({ token });
}
