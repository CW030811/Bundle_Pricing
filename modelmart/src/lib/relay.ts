// API 中转 + 调度 + 计费 辅助
import { prisma } from "@/lib/db";

/** 粗略 token 估算 (CJK 友好) */
export function estimateTokens(text: string): number {
  if (!text) return 0;
  let cjk = 0;
  for (const ch of text) if (/[一-鿿]/.test(ch)) cjk++;
  const ascii = text.length - cjk;
  return Math.max(1, Math.ceil(cjk * 0.6 + ascii / 4));
}

export function messagesToText(messages: { role: string; content: unknown }[]): string {
  return (messages || [])
    .map((m) => (typeof m.content === "string" ? m.content : JSON.stringify(m.content)))
    .join("\n");
}

/** 调度: 在可用渠道中按优先级 + 加权随机挑选一个服务该模型的渠道 */
export async function selectChannel(modelName: string) {
  const channels = await prisma.channel.findMany({
    where: { status: "active" },
    orderBy: { priority: "desc" },
  });
  const serving = channels.filter((c) =>
    c.models.split(",").map((s) => s.trim()).includes(modelName)
  );
  if (serving.length === 0) return null;
  // 取最高优先级集合内加权随机
  const topPriority = serving[0].priority;
  const pool = serving.filter((c) => c.priority === topPriority);
  const total = pool.reduce((s, c) => s + Math.max(1, c.weight), 0);
  let r = Math.random() * total;
  for (const c of pool) {
    r -= Math.max(1, c.weight);
    if (r <= 0) return c;
  }
  return pool[0];
}

/** 模拟上游回复 (Mock 渠道 / 无真实 Key 时) */
export function buildMockReply(displayName: string, userText: string): string {
  const last = userText.slice(-120) || "(空消息)";
  return (
    `你好, 我是 ${displayName}, 通过 ModelMart 模型超市中转为你服务。\n\n` +
    `你刚才说: "${last}"。\n\n` +
    `这是一条用于演示「鉴权 → 调度 → 计费 → 日志」完整链路的模拟回复。` +
    `在生产环境中, 只需在后台「渠道」里填入真实上游 API Key 并启用, ` +
    `本接口即可无缝转发至 OpenAI / Anthropic / DeepSeek 等真实模型, ` +
    `并按 token 用量自动从你的余额扣费、记录账单。`
  );
}

/** 转发到 OpenAI 兼容上游 (provider: openai / deepseek 等) */
export async function forwardOpenAICompatible(
  baseUrl: string,
  apiKey: string,
  body: unknown
): Promise<Response> {
  const url = baseUrl.replace(/\/$/, "") + "/chat/completions";
  return fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify(body),
  });
}
