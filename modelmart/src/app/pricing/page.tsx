import Link from "next/link";
import { prisma } from "@/lib/db";
import { SiteHeader } from "@/components/SiteHeader";
import { SiteFooter } from "@/components/SiteFooter";
import { pricePerMillionYuan, CATEGORIES } from "@/lib/constants";

export const dynamic = "force-dynamic";

export default async function PricingPage() {
  const models = await prisma.modelPrice.findMany({
    where: { status: "active" },
    orderBy: [{ category: "asc" }, { sortOrder: "asc" }],
  });
  const groups = Object.keys(CATEGORIES)
    .map((cat) => ({ cat, items: models.filter((m) => m.category === cat) }))
    .filter((g) => g.items.length > 0);

  return (
    <>
      <SiteHeader />
      <main className="mx-auto max-w-6xl px-4 py-12 sm:px-6">
        <h1 className="text-3xl font-bold text-white">模型 & 能力定价</h1>
        <p className="mt-2 text-slate-400">
          统一按量计费, 价格透明。对话模型按 token 计费 (¥/百万 tokens), 智能体 / MCP / Skill 按次计费。
        </p>

        <div className="mt-10 space-y-10">
          {groups.map((g) => {
            const perCall = ["agent", "mcp", "skill"].includes(g.cat);
            return (
              <section key={g.cat}>
                <h2 className="mb-3 text-xl font-semibold text-white">{CATEGORIES[g.cat]}</h2>
                <div className="card overflow-x-auto">
                  <table className="w-full min-w-[640px]">
                    <thead className="border-b border-white/10">
                      <tr>
                        <th className="th">名称</th>
                        <th className="th">模型 ID</th>
                        <th className="th">供应商</th>
                        {perCall ? (
                          <th className="th">单价</th>
                        ) : (
                          <>
                            <th className="th">输入 (¥/百万)</th>
                            <th className="th">输出 (¥/百万)</th>
                          </>
                        )}
                        <th className="th">说明</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5">
                      {g.items.map((m) => (
                        <tr key={m.id} className="hover:bg-white/[0.03]">
                          <td className="td font-medium text-white">
                            {m.displayName}
                            {m.tag && (
                              <span className="badge ml-2 bg-violet-500/15 text-violet-300">{m.tag}</span>
                            )}
                          </td>
                          <td className="td font-mono text-xs text-slate-400">{m.name}</td>
                          <td className="td text-slate-400">{m.provider}</td>
                          {perCall ? (
                            <td className="td text-white">
                              ¥{pricePerMillionYuan(m.priceOutput).toFixed(2)} / 次
                            </td>
                          ) : (
                            <>
                              <td className="td text-white">
                                ¥{pricePerMillionYuan(m.priceInput).toFixed(2)}
                              </td>
                              <td className="td text-white">
                                ¥{pricePerMillionYuan(m.priceOutput).toFixed(2)}
                              </td>
                            </>
                          )}
                          <td className="td max-w-xs whitespace-normal text-slate-400">
                            {m.description}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            );
          })}
        </div>

        <div className="card mt-12 flex flex-col items-center gap-4 p-8 text-center">
          <h3 className="text-xl font-semibold text-white">准备好开始了吗?</h3>
          <p className="text-slate-400">注册即送 ¥2 体验额度, 充值满 100 元再赠 10%。</p>
          <Link href="/register" className="btn btn-primary">
            免费注册
          </Link>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
