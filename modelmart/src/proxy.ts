import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { SESSION_COOKIE, verifySession } from "@/lib/session";

// Next.js 16: `middleware` 约定已更名为 `proxy`
export async function proxy(req: NextRequest) {
  const { pathname } = req.nextUrl;
  const tokenVal = req.cookies.get(SESSION_COOKIE)?.value;
  const sess = tokenVal ? await verifySession(tokenVal) : null;

  if (pathname.startsWith("/admin")) {
    if (!sess) return NextResponse.redirect(new URL(`/login?next=${pathname}`, req.url));
    if (sess.role !== "admin") return NextResponse.redirect(new URL("/dashboard", req.url));
  }
  if (pathname.startsWith("/dashboard")) {
    if (!sess) return NextResponse.redirect(new URL(`/login?next=${pathname}`, req.url));
  }
  return NextResponse.next();
}

export const config = { matcher: ["/dashboard/:path*", "/admin/:path*"] };
