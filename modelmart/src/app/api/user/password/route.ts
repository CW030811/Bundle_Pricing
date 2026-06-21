import { z } from "zod";
import { prisma } from "@/lib/db";
import { ok, fail } from "@/lib/api";
import { getCurrentUser, hashPassword, verifyPassword } from "@/lib/auth";

const schema = z.object({
  oldPassword: z.string().min(1),
  newPassword: z.string().min(6).max(64),
});

export async function POST(req: Request) {
  const user = await getCurrentUser();
  if (!user) return fail("未登录", 401);
  let body;
  try {
    body = schema.parse(await req.json());
  } catch {
    return fail("新密码至少 6 位");
  }
  if (!(await verifyPassword(body.oldPassword, user.passwordHash)))
    return fail("原密码错误");
  await prisma.user.update({
    where: { id: user.id },
    data: { passwordHash: await hashPassword(body.newPassword) },
  });
  return ok();
}
