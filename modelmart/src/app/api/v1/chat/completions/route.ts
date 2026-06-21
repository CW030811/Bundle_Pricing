import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { calcQuotaCost } from "@/lib/constants";
import {
  estimateTokens,
  messagesToText,
  selectChannel,
  buildMockReply,
  forwardOpenAICompatible,
} from "@/lib/relay";

export const runtime = "nodejs";

const err = (message: string, type: string, status: number) =>
  NextResponse.json({ error: { message, type } }, { status });

export async function POST(req: Request) {
  // 1) 鉴权: Bearer sk-xxx
  const key = (req.headers.get("authorization") || "").replace(/^Bearer\s+/i, "").trim();
  if (!key.startsWith("sk-")) return err("缺少有效的 API Key", "authentication_error", 401);

  const token = await prisma.token.findUnique({ where: { key }, include: { user: true } });
  if (!token) return err("API Key 无效", "authentication_error", 401);
  if (token.status !== "active") return err("令牌已被禁用", "permission_error", 403);
  if (token.expiresAt && token.expiresAt < new Date())
    return err("令牌已过期", "permission_error", 403);
  const user = token.user;
  if (!user || user.status === "banned") return err("账号不可用", "permission_error", 403);

  // 2) 解析请求
  let body: { model?: string; messages?: { role: string; content: unknown }[]; stream?: boolean };
  try {
    body = await req.json();
  } catch {
    return err("请求体不是合法 JSON", "invalid_request_error", 400);
  }
  const modelName = body.model;
  const messages = body.messages;
  const stream = !!body.stream;
  if (!modelName || !Array.isArray(messages))
    return err("缺少 model 或 messages 字段", "invalid_request_error", 400);

  // 3) 模型/定价
  const model = await prisma.modelPrice.findUnique({ where: { name: modelName } });
  if (!model || model.status !== "active")
    return err(`模型 ${modelName} 不可用`, "invalid_request_error", 404);

  // 4) 余额 / 令牌额度预检
  if (user.balance <= 0) return err("账户余额不足, 请充值", "insufficient_quota", 402);
  if (token.quotaLimit != null && token.usedQuota >= token.quotaLimit)
    return err("当前令牌额度已用尽", "insufficient_quota", 402);

  // 5) 调度选渠道
  const channel = await selectChannel(modelName);
  const channelName = channel?.name ?? "Mock 演示渠道";
  const promptText = messagesToText(messages);
  const promptTokens = estimateTokens(promptText);

  // 是否走真实上游 (已填真实 Key 且为 OpenAI 兼容供应商)
  const useReal =
    !!channel &&
    /openai|deepseek/.test(channel.provider) &&
    !channel.apiKey.includes("填入") &&
    channel.apiKey.startsWith("sk-");

  // 6) 取得回复
  let completionText = "";
  let usage: { prompt_tokens?: number; completion_tokens?: number } | null = null;
  if (useReal && channel) {
    try {
      const upstream = await forwardOpenAICompatible(channel.baseUrl, channel.apiKey, {
        ...body,
        stream: false,
      });
      if (!upstream.ok) {
        const t = await upstream.text();
        return err("上游返回错误: " + t.slice(0, 200), "upstream_error", 502);
      }
      const j = await upstream.json();
      completionText = j?.choices?.[0]?.message?.content ?? "";
      usage = j?.usage ?? null;
    } catch {
      return err("无法连接上游渠道", "upstream_error", 502);
    }
  } else {
    completionText = buildMockReply(model.displayName, promptText);
  }

  // 7) 计费结算
  const pt = usage?.prompt_tokens ?? promptTokens;
  const ct = usage?.completion_tokens ?? estimateTokens(completionText);
  const cost = calcQuotaCost(pt, ct, model.priceInput, model.priceOutput);
  await prisma.$transaction([
    prisma.user.update({
      where: { id: user.id },
      data: { balance: { decrement: cost }, totalConsumed: { increment: cost } },
    }),
    prisma.token.update({
      where: { id: token.id },
      data: { usedQuota: { increment: cost }, lastUsedAt: new Date() },
    }),
    prisma.usageLog.create({
      data: {
        userId: user.id,
        tokenId: token.id,
        modelName,
        promptTokens: pt,
        completionTokens: ct,
        quotaCost: cost,
        channelName,
        ip: req.headers.get("x-forwarded-for") || "127.0.0.1",
      },
    }),
  ]);

  const id = "chatcmpl-" + Math.random().toString(36).slice(2, 12);
  const created = Math.floor(Date.now() / 1000);

  // 8) 返回 (流式 / 非流式)
  if (stream) {
    const encoder = new TextEncoder();
    const chunkSize = 24;
    const pieces: string[] = [];
    for (let i = 0; i < completionText.length; i += chunkSize)
      pieces.push(completionText.slice(i, i + chunkSize));

    const rs = new ReadableStream({
      start(controller) {
        const send = (obj: unknown) =>
          controller.enqueue(encoder.encode(`data: ${JSON.stringify(obj)}\n\n`));
        send({
          id,
          object: "chat.completion.chunk",
          created,
          model: modelName,
          choices: [{ index: 0, delta: { role: "assistant" }, finish_reason: null }],
        });
        for (const p of pieces) {
          send({
            id,
            object: "chat.completion.chunk",
            created,
            model: modelName,
            choices: [{ index: 0, delta: { content: p }, finish_reason: null }],
          });
        }
        send({
          id,
          object: "chat.completion.chunk",
          created,
          model: modelName,
          choices: [{ index: 0, delta: {}, finish_reason: "stop" }],
          usage: { prompt_tokens: pt, completion_tokens: ct, total_tokens: pt + ct },
        });
        controller.enqueue(encoder.encode("data: [DONE]\n\n"));
        controller.close();
      },
    });
    return new Response(rs, {
      headers: {
        "Content-Type": "text/event-stream; charset=utf-8",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      },
    });
  }

  return NextResponse.json({
    id,
    object: "chat.completion",
    created,
    model: modelName,
    choices: [
      { index: 0, message: { role: "assistant", content: completionText }, finish_reason: "stop" },
    ],
    usage: { prompt_tokens: pt, completion_tokens: ct, total_tokens: pt + ct },
    modelmart: { quota_cost: cost, channel: channelName },
  });
}
