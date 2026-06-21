import { Brand } from "./Brand";

export function SiteFooter() {
  return (
    <footer className="mt-24 border-t border-white/10">
      <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6">
        <div className="flex flex-col items-center justify-between gap-4 sm:flex-row">
          <Brand />
          <p className="text-sm text-slate-400">
            © 2026 ModelMart 模型超市 · 仅供学习演示, 模型回复为模拟数据
          </p>
          <div className="flex gap-4 text-sm text-slate-400">
            <span>低价</span>
            <span>·</span>
            <span>稳定</span>
            <span>·</span>
            <span>高速</span>
          </div>
        </div>
      </div>
    </footer>
  );
}
