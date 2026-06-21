import { ok, fail } from "@/lib/api";
import { getCurrentUser } from "@/lib/auth";

export async function GET() {
  const user = await getCurrentUser();
  if (!user) return fail("未登录", 401);
  return ok({
    id: user.id,
    username: user.username,
    email: user.email,
    role: user.role,
    balance: user.balance,
    totalRecharge: user.totalRecharge,
    totalConsumed: user.totalConsumed,
    inviteCode: user.inviteCode,
  });
}
