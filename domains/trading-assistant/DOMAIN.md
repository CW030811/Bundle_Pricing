# trading-assistant / DOMAIN

## Scope

- 平台定位：通用量化研究与交易平台
- 当前已实现市场：加密货币，OKX `BTC/USDT`、`ETH/USDT` 和可发现 USDT universe
- 当前已实现交易类型：现货 + USDT 永续
- 产出：行情数据、策略信号、回测报告、纸交易订单、风控审计、受控 live 订单接口
- 运行模式：本地 CLI + 本地服务循环

## In-Scope

- Crypto/OKX-first 因子研究、策略研究、回测、paper 和 gated live
- OKX API v5 行情、账户、订单接入
- 历史 K 线抓取与本地存储
- 可解释策略研究
- 事件驱动回测
- 纸交易闭环
- 风控门控
- kill switch
- 本地日志、SQLite 审计和 JSON 报表

## Out-of-Scope

- 将未来多资产/股票能力描述为当前已实现能力
- 默认自动实盘下单
- 提现权限
- 无确认的 live 运行
- 首版 Web 控制台
- 首版机器学习因子或 RD-Agent 自动因子挖掘

## Working Principle

- 纸交易优先
- 实盘受控开启
- 风控优先于收益目标
- 策略、风控和 broker 共用同一套接口
- 每个信号、订单、风控拦截都可追溯、可复盘
