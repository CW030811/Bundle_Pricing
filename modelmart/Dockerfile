# ── 构建阶段 ──
FROM node:22-slim AS build
WORKDIR /app
# Prisma 在 Debian slim 上需要 openssl
RUN apt-get update -y && apt-get install -y openssl && rm -rf /var/lib/apt/lists/*
COPY package*.json ./
COPY prisma ./prisma
RUN npm ci
COPY . .
RUN npx prisma generate && npm run build

# ── 运行阶段 ──
FROM node:22-slim AS runner
WORKDIR /app
RUN apt-get update -y && apt-get install -y openssl && rm -rf /var/lib/apt/lists/*
ENV NODE_ENV=production
ENV DATABASE_URL="file:/app/data/prod.db"
ENV AUTH_SECRET="please-change-me-with-openssl-rand-hex-32"
COPY --from=build /app ./
RUN mkdir -p /app/data
EXPOSE 3000
# 启动时建表; 若库为空则灌入演示数据, 然后启动
CMD ["sh", "-c", "npx prisma db push --skip-generate && (node prisma/seed.mjs || true) && npm run start"]
