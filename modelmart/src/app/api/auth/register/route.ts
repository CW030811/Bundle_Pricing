import { z } from "zod";
import { prisma } from "@/lib/db";
import { ok, fail } from "@/lib/api";
import {
  hashPassword,
  setSession,
  generateInviteCode,
  generateApiKey,
} from "@/lib/auth";
import { QUOTA_PER_CNY } from "@/lib/constants";

const schema = z.object({
  username: z.string().min(3).max(20),
  password: z.string().min(6).max(64),
  email: z.string().email().optional().or(z.literal("")),
  inviteCode: z.string().optional(),
});

const SIGNUP_BONUS = 2 * QUOTA_PER_CNY; // 注册赠送 2 元体验额度

export async function POST(req: Request) {
  let body;
  try {
    body = schema.parse(await req.json());
  } catch {
    return fail("参数不合法: 用户名 3-20 位, 密码至少 6 位");
  }

  const exists = await prisma.user.findUnique({ where: { username: body.username } });
  if (exists) return fail("用户名已被占用");
  if (body.email) {
    const e = await prisma.user.findUnique({ where: { email: body.email } });
    if (e) return fail("邮箱已被注册");
  }

  let invitedById: number | undefined;
  if (body.inviteCode) {
    const inviter = await prisma.user.findUnique({ where: { inviteCode: body.inviteCode } });
    if (inviter) invitedById = inviter.id;
  }

  const user = await prisma.user.create({
    data: {
      username: body.username,
      email: body.email || null,
      passwordHash: await hashPassword(body.password),
      balance: SIGNUP_BONUS,
      totalRecharge: SIGNUP_BONUS,
      inviteCode: generateInviteCode(),
      invitedById,
    },
  });

  // 默认令牌
  await prisma.token.create({
    data: { userId: user.id, name: "默认令牌", key: generateApiKey() },
  });

  await setSession({ uid: user.id, username: user.username, role: user.role });
  return ok({ id: user.id, username: user.username, role: user.role });
}
