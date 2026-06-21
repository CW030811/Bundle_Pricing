"use client";
import { useEffect, useState } from "react";
import { CheckCircle2, XCircle } from "lucide-react";

type Item = { id: number; msg: string; type: "ok" | "err" };
let pushFn: (t: Omit<Item, "id">) => void = () => {};

export const toast = {
  ok: (msg: string) => pushFn({ msg, type: "ok" }),
  err: (msg: string) => pushFn({ msg, type: "err" }),
};

export function Toaster() {
  const [items, setItems] = useState<Item[]>([]);
  useEffect(() => {
    pushFn = (t) => {
      const id = Date.now() + Math.random();
      setItems((s) => [...s, { ...t, id }]);
      setTimeout(() => setItems((s) => s.filter((x) => x.id !== id)), 3200);
    };
  }, []);
  return (
    <div className="fixed top-4 right-4 z-[100] flex flex-col gap-2">
      {items.map((i) => (
        <div
          key={i.id}
          className="card flex items-center gap-2 px-4 py-3 text-sm shadow-xl"
          style={{
            borderColor:
              i.type === "ok" ? "rgba(34,197,94,.4)" : "rgba(244,63,94,.4)",
          }}
        >
          {i.type === "ok" ? (
            <CheckCircle2 className="h-4 w-4 text-emerald-400" />
          ) : (
            <XCircle className="h-4 w-4 text-rose-400" />
          )}
          <span>{i.msg}</span>
        </div>
      ))}
    </div>
  );
}
