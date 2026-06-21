// ───────────── 计费单位 ─────────────
// 内部统一使用「额度」整数计费, 避免浮点误差。
// 1 元 = 100000 额度。模型价格以「额度 / 1M tokens」存储。

export const QUOTA_PER_CNY = 100_000;

export const yuanToQuota = (yuan: number) => Math.round(yuan * QUOTA_PER_CNY);
export const quotaToYuan = (quota: number) => quota / QUOTA_PER_CNY;

/** 余额/额度 → 人民币字符串, 如 ¥12.34 */
export const fmtYuan = (quota: number) =>
  "¥" + (quota / QUOTA_PER_CNY).toFixed(2);

/** 额度 → 人民币数字 (不带符号) */
export const toYuan = (quota: number) => Number((quota / QUOTA_PER_CNY).toFixed(4));

/** 价格(额度/1M) → 每百万 tokens 的人民币 */
export const pricePerMillionYuan = (quotaPerM: number) => quotaPerM / QUOTA_PER_CNY;

/** 计算一次调用消耗的额度 */
export function calcQuotaCost(
  promptTokens: number,
  completionTokens: number,
  priceInput: number, // 额度 / 1M
  priceOutput: number
) {
  const cost =
    (promptTokens * priceInput) / 1_000_000 +
    (completionTokens * priceOutput) / 1_000_000;
  return Math.max(1, Math.round(cost)); // 至少计 1 额度, 体现计费
}

export const CATEGORIES: Record<string, string> = {
  chat: "对话模型",
  image: "图像模型",
  embedding: "向量模型",
  agent: "智能体",
  mcp: "MCP 服务",
  skill: "技能 Skill",
};
