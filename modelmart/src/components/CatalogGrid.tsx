"use client";
import { useState } from "react";
import Link from "next/link";
import { pricePerMillionYuan, CATEGORIES } from "@/lib/constants";
import { ArrowRight } from "lucide-react";

export type CatalogItem = {
  id: number;
  name: string;
  displayName: string;
  provider: string;
  category: string;
  priceInput: number;
  priceOutput: number;
  tag: string;
  description: string;
};

const providerColor: Record<string, string> = {
  openai: "from-emerald-400 to-teal-500",
  anthropic: "from-orange-400 to-amber-500",
  google: "from-blue-400 to-sky-500",
  deepseek: "from-indigo-400 to-blue-500",
  xai: "from-slate-300 to-slate-500",
  alibaba: "from-purple-400 to-fuchsia-500",
  "modelmart": "from-violet-400 to-indigo-500",
  "mcp-hub": "from-cyan-400 to-teal-500",
  "skill-hub": "from-pink-400 to-rose-500",
};
const tagColor: Record<string, string> = {
  热门: "bg-rose-500/15 text-rose-300",
  旗舰: "bg-amber-500/15 text-amber-300",
  新品: "bg-emerald-500/15 text-emerald-300",
  超值: "bg-cyan-500/15 text-cyan-300",
  推荐: "bg-violet-500/15 text-violet-300",
};

function priceLabel(it: CatalogItem) {
  if (it.priceInput === 0 && it.priceOutput > 0) {
    return (
      <span>
        <span className="text-base font-semibold text-white">
          ¥{pricePerMillionYuan(it.priceOutput).toFixed(2)}
        </span>
        <span className="text-xs text-slate-400"> / 次</span>
      </span>
    );
  }
  return (
    <span className="text-xs text-slate-300">
      入 <b className="text-white">¥{pricePerMillionYuan(it.priceInput).toFixed(2)}</b> / 出{" "}
      <b className="text-white">¥{pricePerMillionYuan(it.priceOutput).toFixed(2)}</b>
      <span className="text-slate-500"> /百万tk</span>
    </span>
  );
}

export function CatalogGrid({ items }: { items: CatalogItem[] }) {
  const cats = ["all", ...Object.keys(CATEGORIES)];
  const [active, setActive] = useState("all");
  const filtered = active === "all" ? items : items.filter((i) => i.category === active);

  return (
    <div>
      <div className="mb-6 flex flex-wrap gap-2">
        {cats.map((c) => {
          const count = c === "all" ? items.length : items.filter((i) => i.category === c).length;
          if (c !== "all" && count === 0) return null;
          return (
            <button
              key={c}
              onClick={() => setActive(c)}
              className={`rounded-full px-4 py-1.5 text-sm transition ${
                active === c
                  ? "bg-gradient-to-r from-indigo-500 to-violet-500 text-white"
                  : "border border-white/10 text-slate-300 hover:bg-white/5"
              }`}
            >
              {c === "all" ? "全部" : CATEGORIES[c]}
              <span className="ml-1.5 opacity-70">{count}</span>
            </button>
          );
        })}
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {filtered.map((it) => (
          <div
            key={it.id}
            className="card group p-5 transition hover:border-indigo-400/40 hover:bg-white/[0.05]"
          >
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <span
                  className={`grid h-10 w-10 place-items-center rounded-xl bg-gradient-to-br ${
                    providerColor[it.provider] || "from-slate-400 to-slate-600"
                  } text-sm font-bold text-white`}
                >
                  {it.displayName.slice(0, 1)}
                </span>
                <div>
                  <div className="font-semibold text-white">{it.displayName}</div>
                  <div className="text-xs text-slate-400">{it.provider}</div>
                </div>
              </div>
              {it.tag && (
                <span className={`badge ${tagColor[it.tag] || "bg-white/10 text-slate-300"}`}>
                  {it.tag}
                </span>
              )}
            </div>
            <p className="mt-3 line-clamp-2 min-h-[2.5rem] text-sm text-slate-400">
              {it.description}
            </p>
            <div className="mt-4 flex items-center justify-between border-t border-white/10 pt-3">
              {priceLabel(it)}
              <Link
                href="/register"
                className="flex items-center gap-1 text-sm text-indigo-300 opacity-0 transition group-hover:opacity-100"
              >
                接入 <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
