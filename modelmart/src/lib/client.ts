// 客户端统一请求封装
export async function api<T = unknown>(
  path: string,
  opts: RequestInit = {}
): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  let json: { success?: boolean; data?: T; message?: string } = {};
  try {
    json = await res.json();
  } catch {
    /* ignore */
  }
  if (!res.ok || json.success === false) {
    throw new Error(json.message || `请求失败 (${res.status})`);
  }
  return json.data as T;
}
