# ModelMart 模型超市 🛒

> 一个「模型 + 智能体 + MCP/Skill」的 AI 能力超市 / Token API 中转站。
> 对标 [memefast.top](https://memefast.top)（魔因 API）的 MVP（销售 + 国内支付），并按「进货 / 调度 / 销售 / 统计 / 财务」五大板块做了可扩展架构。

本仓库是该平台的 **MVP 自研版本**，采用 Next.js 全栈一体实现，开箱即跑、可一键部署。

---

## ✨ 已实现功能

| 板块 | 能力 | 入口 |
| --- | --- | --- |
| **销售** | 商店首页 / 模型货架 / 定价页 / 注册登录 / 控制台 | `/`、`/pricing`、`/dashboard` |
| **国内支付** | 充值套餐 + 模拟支付（预留易支付）+ 兑换码 | `/dashboard/recharge` |
| **令牌** | API Key 创建 / 限额 / 启停 / 删除 / 复制 | `/dashboard/tokens` |
| **中转** | OpenAI 兼容 `/v1/chat/completions`，鉴权→调度→计费→日志，支持流式 | `/api/v1/chat/completions` |
| **进货 + 调度** | 渠道管理（上游 Key / 模型映射），加权随机 + 优先级路由 | `/admin/channels` |
| **统计** | 用户看板 + 管理员数据看板（营收 / 消费 / 毛利 / Top 模型 / 7 日趋势） | `/dashboard`、`/admin` |
| **财务** | 订单流水 / 充值记录 / 对账 | `/admin/orders` |
| **运营** | 用户管理 / 商品上下架 / 兑换码批量生成 / 公告 | `/admin/*` |

---

## 🧱 技术栈

| 层 | 选型 | 说明 |
| --- | --- | --- |
| 框架 | **Next.js 16**（App Router, Turbopack） | 前后端一体, RSC + Route Handlers |
| 语言 | **TypeScript** | 全量类型, `tsc --noEmit` 通过 |
| UI | **Tailwind CSS v4** + **lucide-react** | 深色科技风设计系统 |
| 数据库 | **SQLite** + **Prisma 6** ORM | 单文件零依赖, 可平滑换 Postgres/MySQL |
| 鉴权 | **jose**（JWT, HttpOnly Cookie）+ **bcryptjs** | Edge 安全的会话校验 |
| 校验 | **zod** | 请求体校验 |
| 路由守卫 | Next 16 **`proxy.ts`**（原 middleware） | `/dashboard`、`/admin` 鉴权与 RBAC |

---

## 🛠 开发能力配置（Claude Code 工具链调研）

本项目在 Claude Code 环境内开发，调研并使用了以下能力，**无需额外安装插件即可复现**：

- **工具链**：Node `v25`、npm `v11`（`npm ping` 验证联网拉包正常）。
- **脚手架**：`create-next-app@latest`（自动生成 Next 16 + Tailwind v4 模板）。
- **实时预览**（交付「可访问 demo 链接」的关键能力）：使用内置 **Claude Preview MCP**
  （`preview_start` / `preview_screenshot` / `preview_logs`），通过 `.claude/launch.json`
  托管 `npm run dev`，在 `http://localhost:3000` 提供可访问预览并截图核对 UI。
- **资料调研**：内置 `WebSearch` / `WebFetch` 做竞品（memefast / one-api / new-api）与行业调研。
- **版本适配**：Next 16 携带离线文档于 `node_modules/next/dist/docs/`，据此适配了两处破坏性变更
  （`middleware → proxy`、Prisma 7 datasource → 回退稳定的 Prisma 6）。

> 可选增强（非必需）：`next-devtools-mcp`（官方升级/迁移助手）。

---

## 🚀 快速开始

```bash
cd modelmart
npm install            # 安装依赖 (postinstall 会自动 prisma generate)
npm run db:push        # 创建 SQLite 表结构
npm run db:seed        # 灌入演示数据 (模型/渠道/兑换码/演示账号)
npm run dev            # 启动: http://localhost:3000
```

### 演示账号

| 角色 | 用户名 | 密码 |
| --- | --- | --- |
| 管理员 | `admin` | `admin1234` |
| 普通用户 | `demo` | `demo1234` |

> `npm run db:seed` 会在控制台打印 3 个可用兑换码与演示令牌 `sk-...`。

### 测试中转接口

```bash
curl http://localhost:3000/api/v1/chat/completions \
  -H "Authorization: Bearer <你的 sk- 令牌>" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-5.3","messages":[{"role":"user","content":"你好"}]}'
```

> 未配置真实上游 Key 时返回「模拟回复」，但**鉴权 / 调度 / 计费 / 日志全部真实生效**。
> 在 `/admin/channels` 填入真实 Key 并启用后，即转发到真实模型。

---

## 📁 目录结构

```
modelmart/
├── prisma/
│   ├── schema.prisma        # 9 张表: User/Token/Channel/ModelPrice/Order/RedeemCode/UsageLog/Announcement/Setting
│   └── seed.mjs             # 演示数据
├── src/
│   ├── app/
│   │   ├── page.tsx         # 商店首页 (RSC)
│   │   ├── pricing,docs,login,register/
│   │   ├── dashboard/       # 用户控制台 (概览/令牌/充值/日志/设置)
│   │   ├── admin/           # 管理后台 (看板/用户/渠道/商品/订单/兑换码/公告)
│   │   └── api/             # 后端接口 (auth / tokens / recharge / redeem / logs / admin / v1 中转)
│   ├── components/          # AppShell / CatalogGrid / ui(StatCard,Bars,Modal,Badge) / toast ...
│   ├── lib/                 # db / auth / session / relay(调度计费) / constants(计费单位) / admin
│   └── proxy.ts             # 路由守卫 (Next 16)
├── Dockerfile / docker-compose.yml
└── README.md
```

---

## 💰 计费模型

- 内部统一用整数「**额度**」计费，避免浮点误差：**1 元 = 100000 额度**。
- 模型价格以「额度 / 1M tokens」存储；单次消费 = `输入tok×入价 + 输出tok×出价`（见 `src/lib/constants.ts`）。
- 每次中转调用：原子事务内 **扣余额 + 累加令牌用量 + 写用量日志**。

---

## ☁️ 部署

**Docker（推荐，自带 SQLite 卷持久化）**

```bash
docker compose up -d        # 访问 http://服务器IP:3000
```

**Vercel**

1. 推送到 GitHub，导入 Vercel。
2. 环境变量：`AUTH_SECRET`（`openssl rand -hex 32`）、`DATABASE_URL`。
3. SQLite 在 Serverless 不可持久化，生产请改用 Postgres：把 `schema.prisma`
   的 `provider` 改为 `postgresql` 并配置 `DATABASE_URL` 即可。

---

## 🔐 生产化清单（上线前）

- [ ] 修改 `AUTH_SECRET` 为随机强密钥
- [ ] SQLite → Postgres/MySQL
- [ ] 接入真实支付（易支付/支付宝当面付）替换 `/api/recharge/[orderNo]` 模拟回调
- [ ] 在 `/admin/channels` 填入真实上游 Key
- [ ] 加上游失败重试 / 限流 / Redis 缓存
- [ ] Nginx 反向代理 + HTTPS（勿直接暴露 3000）

---

## 📚 相关文档

- [产品调研与开发计划手册](docs/产品调研与开发计划.md)
- [开发总结与验收文档](docs/开发总结与验收.md)

> ⚠️ 本项目仅供学习演示。模型回复为模拟数据；API 转售请遵守上游服务条款与当地法规。
