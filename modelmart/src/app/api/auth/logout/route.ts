import { ok } from "@/lib/api";
import { clearSession } from "@/lib/auth";

export async function POST() {
  await clearSession();
  return ok();
}
