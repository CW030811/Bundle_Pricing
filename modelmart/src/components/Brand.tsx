import Link from "next/link";
import { Boxes } from "lucide-react";

export function Brand({ href = "/" }: { href?: string }) {
  return (
    <Link href={href} className="flex items-center gap-2.5">
      <span className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-500 shadow-lg shadow-indigo-500/30">
        <Boxes className="h-5 w-5 text-white" />
      </span>
      <span className="text-lg font-bold tracking-tight">
        Model<span className="text-gradient">Mart</span>
      </span>
    </Link>
  );
}
