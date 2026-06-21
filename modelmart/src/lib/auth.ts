// Node 端认证: 密码哈希 + 会话 cookie + 当前用户 + 密钥生成
import "server-only";
import { cookies } from "next/headers";
import bcrypt from "bcryptjs";
import { customAlphabet } from "nanoid";
import { prisma } from "@/lib/db";
import {
  SESSION_COOKIE,
  SessionPayload,
  signSession,
  verifySession,
} from "@/lib/session";

const SEVEN_DAYS = 60 * 60 * 24 * 7;

export async function hashPassword(pw: string) {
  return bcrypt.hash(pw, 10);
}
export async function verifyPassword(pw: string, hash: string) {
  return bcrypt.compare(pw, hash);
}

export async function setSession(payload: SessionPayload) {
  const token = await signSession(payload);
  const jar = await cookies();
  jar.set(SESSION_COOKIE, token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: SEVEN_DAYS,
  });
}

export async function clearSession() {
  const jar = await cookies();
  jar.delete(SESSION_COOKIE);
}

export async function getSession(): Promise<SessionPayload | null> {
  const jar = await cookies();
  const token = jar.get(SESSION_COOKIE)?.value;
  if (!token) return null;
  return verifySession(token);
}

/** 读取当前登录用户 (含最新余额) */
export async function getCurrentUser() {
  const sess = await getSession();
  if (!sess) return null;
  const user = await prisma.user.findUnique({ where: { id: sess.uid } });
  if (!user || user.status === "banned") return null;
  return user;
}

// ───────────── 生成器 ─────────────
const keyChars = customAlphabet(
  "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789",
  48
);
const codeChars = customAlphabet("ABCDEFGHJKLMNPQRSTUVWXYZ23456789", 8);
const numChars = customAlphabet("0123456789", 6);

export const generateApiKey = () => "sk-" + keyChars();
export const generateInviteCode = () => codeChars();
export const generateRedeemCode = () =>
  `${codeChars()}-${codeChars()}-${codeChars()}`;
export const generateOrderNo = () =>
  "MM" + Date.now().toString() + numChars();
