import { z } from "zod";
import { prisma } from "@/lib/db";
import { ok, fail } from "@/lib/api";
import { verifyPassword, setSession } from "@/lib/auth";

const schema = z.object({
  username: z.string().min(1),
  password: z.string().min(1),
});

export async function POST(req: Request) {
  let body;
  try {
    body = schema.parse(await req.json());
  } catch {
    return fail("请输入用户名与密码");
  }

  const user = await prisma.user.findFirst({
    where: { OR: [{ username: body.username }, { email: body.username }] },
  });
  if (!user || !(await verifyPassword(body.password, user.passwordHash)))
    return fail("用户名或密码错误", 401);
  if (user.status === "banned") return fail("账号已被封禁", 403);

  await setSession({ uid: user.id, username: user.username, role: user.role });
  return ok({ id: user.id, username: user.username, role: user.role });
}
