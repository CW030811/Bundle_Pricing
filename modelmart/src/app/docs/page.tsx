import { SiteHeader } from "@/components/SiteHeader";
import { SiteFooter } from "@/components/SiteFooter";

export const metadata = { title: "接入文档 · ModelMart" };

function Code({ children }: { children: string }) {
  return (
    <pre className="card overflow-x-auto p-4 text-[13px] leading-relaxed text-slate-300">
      <code>{children}</code>
    </pre>
  );
}

export default function DocsPage() {
  return (
    <>
      <SiteHeader />
      <main className="mx-auto max-w-3xl px-4 py-12 sm:px-6">
        <h1 className="text-3xl font-bold text-white">接入文档</h1>
        <p className="mt-2 text-slate-400">
          ModelMart 提供 OpenAI 完全兼容的接口, 已有项目只需替换 <code>base_url</code> 与{" "}
          <code>api_key</code> 即可无缝接入。
        </p>

        <h2 className="mt-10 text-xl font-semibold text-white">1. 获取令牌</h2>
        <p className="mt-2 text-slate-400">
          注册登录后, 进入「控制台 → 令牌管理」创建一个令牌, 形如 <code>sk-xxxx</code>。
        </p>

        <h2 className="mt-8 text-xl font-semibold text-white">2. 接口地址</h2>
        <Code>{`POST  /api/v1/chat/completions
Header: Authorization: Bearer sk-你的令牌`}</Code>

        <h2 className="mt-8 text-xl font-semibold text-white">3. cURL 调用</h2>
        <Code>{`curl https://your-domain/api/v1/chat/completions \\
  -H "Authorization: Bearer sk-你的令牌" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "claude-sonnet-4-6",
    "messages": [{"role": "user", "content": "用一句话介绍你自己"}]
  }'`}</Code>

        <h2 className="mt-8 text-xl font-semibold text-white">4. Python (openai SDK)</h2>
        <Code>{`from openai import OpenAI

client = OpenAI(
    api_key="sk-你的令牌",
    base_url="https://your-domain/api/v1",
)

resp = client.chat.completions.create(
    model="gpt-5.3",
    messages=[{"role": "user", "content": "你好"}],
    stream=True,
)
for chunk in resp:
    print(chunk.choices[0].delta.content or "", end="")`}</Code>

        <h2 className="mt-8 text-xl font-semibold text-white">5. 计费说明</h2>
        <ul className="mt-2 list-disc space-y-1.5 pl-5 text-slate-400">
          <li>对话模型按 <b className="text-slate-200">输入 + 输出 token</b> 用量计费, 单价见定价页。</li>
          <li>每次调用自动从账户余额扣除对应额度, 并生成账单日志。</li>
          <li>令牌可单独设置额度上限, 超出后该令牌停止计费。</li>
          <li>余额不足将返回 <code>402 insufficient_quota</code>。</li>
        </ul>

        <div className="card mt-8 border-amber-400/30 p-4 text-sm text-amber-200/90">
          演示环境说明: 当前未配置真实上游 Key, 接口将返回「模拟回复」用于演示完整的鉴权 → 调度
          → 计费 → 日志链路。在后台「渠道」中填入真实 Key 并启用后, 即可转发到真实模型。
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
