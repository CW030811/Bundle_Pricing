import { prisma } from "@/lib/db";
import { ok } from "@/lib/api";

export async function GET() {
  const items = await prisma.announcement.findMany({
    orderBy: [{ pinned: "desc" }, { createdAt: "desc" }],
  });
  return ok({ items });
}
