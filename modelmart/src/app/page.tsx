import Link from "next/link";
import { prisma } from "@/lib/db";
import { SiteHeader } from "@/components/SiteHeader";
import { SiteFooter } from "@/components/SiteFooter";
import { CatalogGrid, CatalogItem } from "@/components/CatalogGrid";
import {
  Sparkles,
  TrendingDown,
  ShieldCheck,
  Zap,
  Boxes,
  Bot,
  Plug,
  ArrowRight,
  Megaphone,
} from "lucide-react";

export const dynamic = "force-dynamic";

async function getData() {
  const [models, modelCount, userCount, callCount, announcements] = await Promise.all([
    prisma.modelPrice.findMany({
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
    }),
    prisma.modelPrice.count({ where: { status: "active" } }),
    prisma.user.count(),
    prisma.usageLog.count(),
    prisma.announcement.findMany({
      orderBy: [{ pinned: "desc" }, { createdAt: "desc" }],
      take: 2,
    }),
  ]);
  return { models, modelCount, userCount, callCount, announcements };
}

const features = [
  { icon: TrendingDown, title: "低价", desc: "聚合议价, 低至官方价 10%, 按量计费不浪费" },
  { icon: ShieldCheck, title: "稳定", desc: "多渠道加权调度 + 失败自动重试, 99.9% 可用" },
  { icon: Zap, title: "高速", desc: "全球节点中转, 毫秒级响应, 原生流式输出" },
  { icon: Boxes, title: "全模型", desc: "GPT / Claude / Gemini / DeepSeek / Grok 一站直达" },
  { icon: Bot, title: "智能体", desc: "编程、深研等开箱即用 Agent, 按次计费" },
  { icon: Plug, title: "MCP / Skill", desc: "工具与技能即插即用, 让模型真正能干活" },
];

export default async function Home() {
  const { models, modelCount, userCount, callCount, announcements } = await getData();
  const stats = [
    { label: "上架模型 / 智能体", value: `${modelCount}+` },
    { label: "累计调用", value: callCount.toLocaleString() },
    { label: "注册用户", value: userCount.toLocaleString() },
    { label: "服务可用性", value: "99.9%" },
  ];

  return (
    <>
      <SiteHeader />
      <main className="mx-auto max-w-7xl px-4 sm:px-6">
        {/* Hero */}
        <section className="grid items-center gap-10 py-16 lg:grid-cols-2 lg:py-24">
          <div>
            <span className="badge border border-white/10 bg-white/5 text-slate-300">
              <Sparkles className="h-3.5 w-3.5 text-violet-300" />
              模型 · 智能体 · MCP · Skill 的 AI 能力超市
            </span>
            <h1 className="mt-5 text-4xl font-bold leading-tight tracking-tight sm:text-5xl">
              一个接口, 直达全球
              <br />
              <span className="text-gradient">最强 AI 能力</span>
            </h1>
            <p className="mt-5 max-w-lg text-lg text-slate-400">
              ModelMart 把 GPT、Claude、Gemini、DeepSeek 等顶级模型与智能体聚合到一个
              OpenAI 兼容接口。低价、稳定、高速, 注册即送体验额度。
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link href="/register" className="btn btn-primary">
                免费注册领额度 <ArrowRight className="h-4 w-4" />
              </Link>
              <Link href="/pricing" className="btn btn-ghost">
                查看模型定价
              </Link>
            </div>
            <div className="mt-8 grid grid-cols-2 gap-4 sm:grid-cols-4">
              {stats.map((s) => (
                <div key={s.label}>
                  <div className="text-2xl font-bold text-white">{s.value}</div>
                  <div className="text-xs text-slate-400">{s.label}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Code preview */}
          <div className="card overflow-hidden">
            <div className="flex items-center gap-1.5 border-b border-white/10 px-4 py-3">
              <span className="h-3 w-3 rounded-full bg-rose-400/80" />
              <span className="h-3 w-3 rounded-full bg-amber-400/80" />
              <span className="h-3 w-3 rounded-full bg-emerald-400/80" />
              <span className="ml-3 text-xs text-slate-400">接入只需改一行 base_url</span>
            </div>
            <pre className="overflow-x-auto p-5 text-[13px] leading-relaxed text-slate-300">
              <code>{`curl https://your-domain/api/v1/chat/completions \\
  -H "Authorization: Bearer sk-你的令牌" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "claude-sonnet-4-6",
    "messages": [
      {"role":"user","content":"你好, 帮我写个快排"}
    ],
    "stream": true
  }'`}</code>
            </pre>
          </div>
        </section>

        {/* 公告 */}
        {announcements.length > 0 && (
          <section className="mb-12 grid gap-3 sm:grid-cols-2">
            {announcements.map((a) => (
              <div key={a.id} className="card flex items-start gap-3 p-4">
                <Megaphone className="mt-0.5 h-5 w-5 shrink-0 text-violet-300" />
                <div>
                  <div className="font-medium text-white">{a.title}</div>
                  <div className="mt-1 text-sm text-slate-400">{a.content}</div>
                </div>
              </div>
            ))}
          </section>
        )}

        {/* 特性 */}
        <section className="mb-16 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {features.map((f) => (
            <div key={f.title} className="card p-5">
              <f.icon className="h-6 w-6 text-indigo-300" />
              <div className="mt-3 text-lg font-semibold text-white">{f.title}</div>
              <div className="mt-1 text-sm text-slate-400">{f.desc}</div>
            </div>
          ))}
        </section>

        {/* 商品目录 */}
        <section className="mb-10">
          <div className="mb-6 flex items-end justify-between">
            <div>
              <h2 className="text-2xl font-bold text-white">能力货架</h2>
              <p className="mt-1 text-sm text-slate-400">
                像逛超市一样选购 AI 能力, 价格透明, 即买即用
              </p>
            </div>
            <Link
              href="/pricing"
              className="hidden text-sm text-indigo-300 hover:text-white sm:block"
            >
              查看完整价目表 →
            </Link>
          </div>
          <CatalogGrid items={models as CatalogItem[]} />
        </section>
      </main>
      <SiteFooter />
    </>
  );
}
