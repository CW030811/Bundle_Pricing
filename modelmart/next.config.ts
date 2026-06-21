import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 便于 Docker 部署 (产出最小自包含运行时)
  output: "standalone",
  // Prisma / bcrypt 等带原生依赖的包不打进 bundle
  serverExternalPackages: ["@prisma/client", "bcryptjs"],
};

export default nextConfig;
