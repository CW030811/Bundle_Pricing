import { PrismaClient } from "@prisma/client";
import bcrypt from "bcryptjs";
import { customAlphabet } from "nanoid";

const prisma = new PrismaClient();
const Q = 100_000; // 1 元 = 100000 额度
const M = (cnyPerMillion) => Math.round(cnyPerMillion * Q); // 额度 / 1M tokens

const keyChars = customAlphabet(
  "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789",
  48
);
const codeChars = customAlphabet("ABCDEFGHJKLMNPQRSTUVWXYZ23456789", 8);
const apiKey = () => "sk-" + keyChars();
const invite = () => codeChars();
const redeem = () => `${codeChars()}-${codeChars()}-${codeChars()}`;

// 模型/商品目录: [name, 显示名, 供应商, 分类, 售价入/M(元), 售价出/M(元), 标签, 描述, 排序]
const CATALOG = [
  ["gpt-5.3", "GPT-5.3", "openai", "chat", 18, 72, "热门", "OpenAI 旗舰多模态模型, 综合能力最强", 1],
  ["gpt-5.3-mini", "GPT-5.3 Mini", "openai", "chat", 1.5, 6, "", "高性价比轻量版, 日常对话首选", 2],
  ["claude-opus-4-6", "Claude Opus 4.6", "anthropic", "chat", 30, 150, "旗舰", "Anthropic 最强推理与编程模型", 3],
  ["claude-sonnet-4-6", "Claude Sonnet 4.6", "anthropic", "chat", 6, 30, "热门", "均衡高速, 编程与 Agent 利器", 4],
  ["gemini-3-pro", "Gemini 3 Pro", "google", "chat", 10, 40, "", "Google 多模态 + 超长上下文", 5],
  ["deepseek-v3.2", "DeepSeek V3.2", "deepseek", "chat", 0.5, 2, "超值", "国产高性价比通用模型", 6],
  ["deepseek-r1", "DeepSeek R1", "deepseek", "chat", 2, 8, "", "国产强推理 (思维链) 模型", 7],
  ["grok-4.1", "Grok 4.1", "xai", "chat", 15, 60, "新品", "xAI 实时联网对话模型", 8],
  ["qwen-max", "通义千问 Max", "alibaba", "chat", 4, 12, "", "阿里通义旗舰中文模型", 9],
  ["gpt-image-1", "GPT Image 1", "openai", "image", 0, 40, "", "文生图 / 图生图, ≈¥0.30/张", 20],
  ["text-embedding-3-large", "Embedding 3 Large", "openai", "embedding", 0.6, 0, "", "高维文本向量, 检索/RAG", 21],
  ["dev-agent", "全栈编程智能体", "modelmart", "agent", 0, 50, "推荐", "自动写码 / 调试 / 提 PR, 按次 ¥0.50", 30],
  ["deep-research-agent", "深度研究智能体", "modelmart", "agent", 0, 100, "", "多源检索 + 交叉验证 + 报告, 按次 ¥1.00", 31],
  ["notion-mcp", "Notion MCP", "mcp-hub", "mcp", 0, 5, "", "读写 Notion 页面/数据库, 按次 ¥0.05", 40],
  ["github-mcp", "GitHub MCP", "mcp-hub", "mcp", 0, 5, "", "管理仓库/PR/Issue, 按次 ¥0.05", 41],
  ["ppt-skill", "PPT 生成 Skill", "skill-hub", "skill", 0, 20, "", "一句话生成专业幻灯片, 按次 ¥0.20", 50],
  ["pdf-skill", "PDF 处理 Skill", "skill-hub", "skill", 0, 10, "", "PDF 解析/合并/OCR, 按次 ¥0.10", 51],
];

async function main() {
  // 幂等: 清库后重建
  await prisma.usageLog.deleteMany();
  await prisma.order.deleteMany();
  await prisma.token.deleteMany();
  await prisma.redeemCode.deleteMany();
  await prisma.channel.deleteMany();
  await prisma.modelPrice.deleteMany();
  await prisma.announcement.deleteMany();
  await prisma.setting.deleteMany();
  await prisma.user.deleteMany();

  // 系统设置
  await prisma.setting.createMany({
    data: [
      { key: "site_name", value: "ModelMart 模型超市" },
      { key: "site_slogan", value: "低价 · 稳定 · 高速 的 AI 能力超市" },
      { key: "exchange_rate", value: "1" }, // 1 元 = 1 元额度
    ],
  });

  // 用户
  const admin = await prisma.user.create({
    data: {
      username: "admin",
      email: "admin@modelmart.dev",
      passwordHash: await bcrypt.hash("admin1234", 10),
      role: "admin",
      balance: 100 * Q,
      totalRecharge: 100 * Q,
      inviteCode: invite(),
    },
  });
  const demo = await prisma.user.create({
    data: {
      username: "demo",
      email: "demo@modelmart.dev",
      passwordHash: await bcrypt.hash("demo1234", 10),
      balance: 50 * Q,
      totalRecharge: 50 * Q,
      inviteCode: invite(),
      invitedById: admin.id,
    },
  });

  // 模型 / 商品
  const priceMap = {};
  for (const [name, displayName, provider, category, cin, cout, tag, desc, sort] of CATALOG) {
    const priceInput = M(cin);
    const priceOutput = M(cout);
    priceMap[name] = { priceInput, priceOutput };
    await prisma.modelPrice.create({
      data: {
        name,
        displayName,
        provider,
        category,
        priceInput,
        priceOutput,
        costInput: Math.round(priceInput * 0.65),
        costOutput: Math.round(priceOutput * 0.65),
        description: desc,
        tag,
        sortOrder: sort,
      },
    });
  }

  // 渠道 (进货 + 调度)
  const chatModels = CATALOG.filter((m) => m[3] === "chat").map((m) => m[0]).join(",");
  await prisma.channel.create({
    data: {
      name: "Mock 演示渠道",
      provider: "mock",
      baseUrl: "mock://echo",
      apiKey: "mock-key",
      models: chatModels,
      weight: 10,
      priority: 10,
      status: "active",
      balance: 0,
    },
  });
  await prisma.channel.create({
    data: {
      name: "OpenAI 官方直连",
      provider: "openai",
      baseUrl: "https://api.openai.com/v1",
      apiKey: "sk-填入真实Key后启用",
      models: "gpt-5.3,gpt-5.3-mini,gpt-image-1,text-embedding-3-large",
      weight: 5,
      priority: 5,
      status: "disabled",
      balance: 200 * Q,
    },
  });
  await prisma.channel.create({
    data: {
      name: "DeepSeek 官方",
      provider: "deepseek",
      baseUrl: "https://api.deepseek.com",
      apiKey: "sk-填入真实Key后启用",
      models: "deepseek-v3.2,deepseek-r1",
      weight: 8,
      priority: 6,
      status: "disabled",
      balance: 500 * Q,
    },
  });
  await prisma.channel.create({
    data: {
      name: "Anthropic 官方",
      provider: "anthropic",
      baseUrl: "https://api.anthropic.com",
      apiKey: "sk-ant-填入真实Key后启用",
      models: "claude-opus-4-6,claude-sonnet-4-6",
      weight: 5,
      priority: 5,
      status: "disabled",
      balance: 300 * Q,
    },
  });

  // 令牌
  const token = await prisma.token.create({
    data: { userId: demo.id, name: "默认令牌", key: apiKey(), group: "default" },
  });
  await prisma.token.create({
    data: {
      userId: demo.id,
      name: "生产环境 (限额)",
      key: apiKey(),
      quotaLimit: 20 * Q,
      group: "default",
    },
  });

  // 兑换码
  const codes = [10, 50, 100].map((y) => ({ code: redeem(), quota: y * Q, yuan: y }));
  for (const c of codes) {
    await prisma.redeemCode.create({ data: { code: c.code, quota: c.quota } });
  }

  // 公告
  await prisma.announcement.createMany({
    data: [
      {
        title: "🎉 ModelMart 模型超市上线公测",
        content:
          "聚合 GPT / Claude / Gemini / DeepSeek / Grok 等 17 款模型与智能体, 全部低至官方价 10%。新用户注册即送体验额度!",
        pinned: true,
      },
      {
        title: "💰 充值满 100 元加赠 10%",
        content: "活动期间充值满 100 元额外赠送 10% 额度, 多充多得, 详见充值页。",
        pinned: false,
      },
    ],
  });

  // 演示订单 (财务)
  await prisma.order.create({
    data: {
      userId: demo.id,
      orderNo: "MM" + Date.now() + "001",
      amount: 5000, // 分 -> ¥50
      quota: 50 * Q,
      payMethod: "mock",
      status: "paid",
      paidAt: new Date(),
    },
  });

  // 用量日志 (统计) — 近 7 天随机分布
  const usageModels = CATALOG.filter((m) => m[3] === "chat").map((m) => m[0]);
  let consumed = 0;
  const now = Date.now();
  const logs = [];
  for (let day = 6; day >= 0; day--) {
    const calls = 4 + Math.floor(Math.random() * 6); // 每天 4~9 次
    for (let i = 0; i < calls; i++) {
      const name = usageModels[Math.floor(Math.random() * usageModels.length)];
      const pIn = 300 + Math.floor(Math.random() * 3000);
      const pOut = 200 + Math.floor(Math.random() * 2000);
      const { priceInput, priceOutput } = priceMap[name];
      const cost = Math.max(
        1,
        Math.round((pIn * priceInput) / 1e6 + (pOut * priceOutput) / 1e6)
      );
      consumed += cost;
      const ts = new Date(
        now - day * 86400000 - Math.floor(Math.random() * 80000000)
      );
      logs.push({
        userId: demo.id,
        tokenId: token.id,
        modelName: name,
        promptTokens: pIn,
        completionTokens: pOut,
        quotaCost: cost,
        channelName: "Mock 演示渠道",
        ip: "127.0.0.1",
        createdAt: ts,
      });
    }
  }
  await prisma.usageLog.createMany({ data: logs });

  // 结算 demo 余额/消费
  await prisma.user.update({
    where: { id: demo.id },
    data: { balance: 50 * Q - consumed, totalConsumed: consumed },
  });
  await prisma.token.update({
    where: { id: token.id },
    data: { usedQuota: consumed, lastUsedAt: new Date() },
  });

  console.log("✅ 种子数据写入完成");
  console.log("   管理员: admin / admin1234");
  console.log("   演示用户: demo / demo1234");
  console.log("   兑换码:");
  codes.forEach((c) => console.log(`     ${c.code}  (¥${c.yuan})`));
  console.log(`   演示令牌: ${token.key}`);
  console.log(`   demo 余额: ¥${((50 * Q - consumed) / Q).toFixed(2)} / 消费: ¥${(consumed / Q).toFixed(2)} / 日志: ${logs.length} 条`);
}

main()
  .catch((e) => {
    console.error(e);
    process.exit(1);
  })
  .finally(() => prisma.$disconnect());
