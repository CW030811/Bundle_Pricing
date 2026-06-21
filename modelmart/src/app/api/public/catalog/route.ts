import { prisma } from "@/lib/db";
import { ok } from "@/lib/api";

export async function GET() {
  const models = await prisma.modelPrice.findMany({
    where: { status: "active" },
    orderBy: [{ sortOrder: "asc" }, { id: "asc" }],
    select: {
      id: true,
      name: true,
      displayName: true,
      provider: true,
      category: true,
      priceInput: true,
      priceOutput: true,
      tag: true,
      description: true,
    },
  });
  return ok({ models });
}
