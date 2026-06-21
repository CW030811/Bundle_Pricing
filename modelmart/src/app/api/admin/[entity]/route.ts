import { prisma } from "@/lib/db";
import { ok, fail } from "@/lib/api";
import { requireAdmin, ADMIN_ENTITIES, pickAllowed } from "@/lib/admin";
import { generateRedeemCode } from "@/lib/auth";
import { QUOTA_PER_CNY } from "@/lib/constants";

/* eslint-disable @typescript-eslint/no-explicit-any */

export async function GET(req: Request, ctx: { params: Promise<{ entity: string }> }) {
  if (!(await requireAdmin())) return fail("无权限", 403);
  const { entity } = await ctx.params;
  const cfg = ADMIN_ENTITIES[entity];
  if (!cfg) return fail("未知实体", 404);

  const { searchParams } = new URL(req.url);
  const page = Math.max(1, Number(searchParams.get("page") || 1));
  const pageSize = Math.min(100, Number(searchParams.get("pageSize") || 20));

  const delegate = (prisma as any)[cfg.delegate];
  const [rows, total] = await Promise.all([
    delegate.findMany({
      orderBy: cfg.orderBy,
      include: cfg.include,
      skip: (page - 1) * pageSize,
      take: pageSize,
    }),
    delegate.count(),
  ]);

  const items = cfg.stripPassword
    ? rows.map((r: any) => {
        const { passwordHash, ...rest } = r;
        void passwordHash;
        return rest;
      })
    : rows;

  return ok({ items, total, page, pageSize });
}

export async function POST(req: Request, ctx: { params: Promise<{ entity: string }> }) {
  if (!(await requireAdmin())) return fail("无权限", 403);
  const { entity } = await ctx.params;
  const cfg = ADMIN_ENTITIES[entity];
  if (!cfg) return fail("未知实体", 404);
  if (!cfg.create) return fail("该实体不支持创建", 405);

  const body = await req.json().catch(() => ({}));

  // 兑换码: 批量生成
  if (entity === "redeem") {
    const count = Math.min(100, Math.max(1, Number(body.count) || 1));
    const quota = Math.round((Number(body.quotaYuan) || 0) * QUOTA_PER_CNY);
    if (quota <= 0) return fail("面值必须大于 0");
    const created = [];
    for (let i = 0; i < count; i++) {
      const c = await prisma.redeemCode.create({ data: { code: generateRedeemCode(), quota } });
      created.push(c);
    }
    return ok({ created });
  }

  const data = pickAllowed(cfg, body);
  // 模型创建: 成本字段缺省按售价 65%
  if (entity === "models") {
    if (data.costInput == null) data.costInput = Math.round(Number(data.priceInput || 0) * 0.65);
    if (data.costOutput == null) data.costOutput = Math.round(Number(data.priceOutput || 0) * 0.65);
  }
  try {
    const item = await (prisma as any)[cfg.delegate].create({ data });
    return ok({ item });
  } catch (e: any) {
    return fail("创建失败: " + (e?.message?.slice(0, 120) || "未知错误"));
  }
}
