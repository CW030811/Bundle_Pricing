import { getCurrentUser } from "@/lib/auth";

export async function requireAdmin() {
  const user = await getCurrentUser();
  if (!user || user.role !== "admin") return null;
  return user;
}

type EntityCfg = {
  delegate: string;
  create: boolean;
  del: boolean;
  allowed: string[]; // 可写字段白名单
  numeric: string[]; // 需转 int 的字段
  orderBy: unknown;
  include?: unknown;
  stripPassword?: boolean;
};

export const ADMIN_ENTITIES: Record<string, EntityCfg> = {
  users: {
    delegate: "user",
    create: false,
    del: false,
    allowed: ["status", "role", "balance"],
    numeric: ["balance"],
    orderBy: { id: "desc" },
    stripPassword: true,
  },
  channels: {
    delegate: "channel",
    create: true,
    del: true,
    allowed: ["name", "provider", "baseUrl", "apiKey", "models", "weight", "priority", "status", "group"],
    numeric: ["weight", "priority"],
    orderBy: { priority: "desc" },
  },
  models: {
    delegate: "modelPrice",
    create: true,
    del: true,
    allowed: ["name", "displayName", "provider", "category", "priceInput", "priceOutput", "costInput", "costOutput", "description", "tag", "status", "sortOrder"],
    numeric: ["priceInput", "priceOutput", "costInput", "costOutput", "sortOrder"],
    orderBy: { sortOrder: "asc" },
  },
  orders: {
    delegate: "order",
    create: false,
    del: false,
    allowed: ["status"],
    numeric: [],
    orderBy: { createdAt: "desc" },
    include: { user: { select: { username: true } } },
  },
  redeem: {
    delegate: "redeemCode",
    create: true, // 特殊: 批量生成
    del: true,
    allowed: ["status"],
    numeric: [],
    orderBy: { createdAt: "desc" },
    include: { redeemedBy: { select: { username: true } } },
  },
  announcements: {
    delegate: "announcement",
    create: true,
    del: true,
    allowed: ["title", "content", "pinned"],
    numeric: [],
    orderBy: [{ pinned: "desc" }, { createdAt: "desc" }],
  },
};

export function pickAllowed(cfg: EntityCfg, body: Record<string, unknown>) {
  const data: Record<string, unknown> = {};
  for (const f of cfg.allowed) {
    if (body[f] === undefined) continue;
    data[f] = cfg.numeric.includes(f) ? Math.round(Number(body[f])) : body[f];
  }
  return data;
}
