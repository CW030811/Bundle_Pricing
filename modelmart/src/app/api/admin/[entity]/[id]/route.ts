import { prisma } from "@/lib/db";
import { ok, fail } from "@/lib/api";
import { requireAdmin, ADMIN_ENTITIES, pickAllowed } from "@/lib/admin";

/* eslint-disable @typescript-eslint/no-explicit-any */

export async function PATCH(req: Request, ctx: { params: Promise<{ entity: string; id: string }> }) {
  if (!(await requireAdmin())) return fail("无权限", 403);
  const { entity, id } = await ctx.params;
  const cfg = ADMIN_ENTITIES[entity];
  if (!cfg) return fail("未知实体", 404);

  const body = await req.json().catch(() => ({}));
  const data = pickAllowed(cfg, body);
  if (Object.keys(data).length === 0) return fail("无可更新字段");
  try {
    const item = await (prisma as any)[cfg.delegate].update({
      where: { id: Number(id) },
      data,
    });
    return ok({ item });
  } catch (e: any) {
    return fail("更新失败: " + (e?.message?.slice(0, 120) || "未知错误"));
  }
}

export async function DELETE(_req: Request, ctx: { params: Promise<{ entity: string; id: string }> }) {
  if (!(await requireAdmin())) return fail("无权限", 403);
  const { entity, id } = await ctx.params;
  const cfg = ADMIN_ENTITIES[entity];
  if (!cfg) return fail("未知实体", 404);
  if (!cfg.del) return fail("该实体不支持删除", 405);
  try {
    await (prisma as any)[cfg.delegate].delete({ where: { id: Number(id) } });
    return ok();
  } catch (e: any) {
    return fail("删除失败: " + (e?.message?.slice(0, 120) || "未知错误"));
  }
}
