// Edge 安全的会话签名/校验 (仅依赖 jose), 供 middleware 与 node 端共用
import { SignJWT, jwtVerify } from "jose";

export const SESSION_COOKIE = "mm_session";

export type SessionPayload = {
  uid: number;
  username: string;
  role: string;
};

const secret = () =>
  new TextEncoder().encode(process.env.AUTH_SECRET || "modelmart-dev-secret");

export async function signSession(payload: SessionPayload) {
  return new SignJWT({ ...payload })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime("7d")
    .sign(secret());
}

export async function verifySession(token: string): Promise<SessionPayload | null> {
  try {
    const { payload } = await jwtVerify(token, secret());
    return {
      uid: payload.uid as number,
      username: payload.username as string,
      role: payload.role as string,
    };
  } catch {
    return null;
  }
}
