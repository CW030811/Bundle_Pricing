import type { Metadata } from "next";
import "./globals.css";
import { Toaster } from "@/components/toast";

export const metadata: Metadata = {
  title: "ModelMart 模型超市 · 低价稳定高速的 AI 能力中转站",
  description:
    "聚合 GPT / Claude / Gemini / DeepSeek / Grok 等模型与智能体、MCP、Skill 的一站式 AI 能力超市。低价、稳定、高速, OpenAI 兼容接口即插即用。",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body className="min-h-screen antialiased">
        {children}
        <Toaster />
      </body>
    </html>
  );
}
