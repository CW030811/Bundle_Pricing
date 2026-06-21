import { prisma } from "@/lib/db";
import { ok, fail } from "@/lib/api";
import { getCurrentUser } from "@/lib/auth";

async function owned(userId: number, id: number) {
  const t = await prisma.token.findUnique({ where: { id } });
  return t && t.userId === userId ? t : null;
}

export async function PATCH(req: Request, ctx: { params: Promise<{ id: string }> }) {
  const user = await getCurrentUser();
  if (!user) return fail("未登录", 401);
  const { id } = await ctx.params;
  const token = await owned(user.id, Number(id));
  if (!token) return fail("令牌不存在", 404);
  const body = await req.json().catch(() => ({}));
  const data: Record<string, unknown> = {};
  if (body.status === "active" || body.status === "disabled") data.status = body.status;
  if (typeof body.name === "string" && body.name.trim()) data.name = body.name.trim();
  const updated = await prisma.token.update({ where: { id: token.id }, data });
  return ok({ token: updated });
}

export async function DELETE(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  const user = await getCurrentUser();
  if (!user) return fail("未登录", 401);
  const { id } = await ctx.params;
  const token = await owned(user.id, Number(id));
  if (!token) return fail("令牌不存在", 404);
  await prisma.token.delete({ where: { id: token.id } });
  return ok();
}
