# 加密货币量化交易学习教材大纲与计划

版本日期：2026-06-03

本文件是 `trading-assistant` 域的学习入口。目标不是一次性写完所有教材，而是先建立一套可持续推进的课程大纲：每次完成一个学习单元后，再进入下一单元。学习内容以通用量化交易框架为底座，逐步落到当前仓库的 Crypto/OKX-first 平台实践。

风险提示：本计划用于研究和工程学习，不构成投资建议。任何实盘动作都必须经过 paper、demo、小资金、风控门控和人工确认。

## 0. 学习地图

### 总目标

- 建立宏观量化交易的通用认知：资产、数据、收益来源、策略、组合、风控、执行、复盘。
- 理解个人量化平台从研究到部署需要哪些基座，以及如何自检平台是否具备可研究、可复现、可风控、可审计的最低能力。
- 系统梳理加密货币策略类型，明确每类策略的市场机制、数据需求、回测陷阱、实盘风险和经典资料。
- 将学习过程和本地平台结合：当前仓库已有数据、因子、回测、paper、风控、OKX broker、service、watchdog、kill switch 等模块，应优先围绕这些能力做练习。

### 学习顺序

1. 通用量化框架：先知道一套量化系统如何从 idea 走到交易。
2. 量化平台工程：再知道个人平台需要什么基座，哪些门槛没过不能实盘。
3. Crypto 市场结构：理解现货、永续、资金费率、order book、清算和 24/7 市场。
4. Crypto 策略分类：按低频到高频、方向到中性、研究到执行逐类学习。
5. 平台实践：每学一类策略，都在本仓库补一张 Strategy Card、一个数据需求清单、一个回测/评估练习。

### 每个学习单元的固定产出

- 一页学习笔记：核心概念、公式/逻辑、适用市场、失败条件。
- 一张 Strategy Card：假设、数据、信号、进出场、仓位、风控、成本、失效条件。
- 一个自检清单：数据质量、未来函数、成本、样本外、参数稳定性、容量、执行风险。
- 一个本地实践动作：读报告、跑现有命令、扩展数据字段、补研究脚本或设计后续实现任务。

## 1. 宏观量化交易基本框架

### 1.1 量化交易是什么

量化交易是把交易判断拆成可定义、可测试、可执行、可复盘的规则系统。核心不是“用代码交易”，而是用数据和模型把以下问题明确化：

- 买什么：资产、标的池、过滤条件。
- 什么时候买卖：信号、触发条件、调仓周期。
- 买多少：组合构建、仓位、杠杆、风险预算。
- 如何成交：订单类型、滑点、手续费、冲击成本、延迟。
- 何时停止：止损、熔断、失效条件、人工干预。

### 1.2 资产和市场维度

- 传统资产：股票、债券、商品、外汇、期货、期权、ETF。
- 另类资产：加密货币、DeFi、预测市场、碳资产、私募数据类资产。
- 交易制度：连续竞价、集合竞价、中心化限价订单簿、AMM、RFQ、OTC。
- 时间结构：日频、小时级、分钟级、秒级、tick 级。
- 收益来源：风险溢价、行为偏差、结构性摩擦、流动性补偿、信息优势、执行优势。

### 1.3 标准工作流

1. Idea：从市场机制、论文、研报、交易观察或数据异常提出假设。
2. Hypothesis：把假设写成可证伪命题，例如“过去 N 小时强势币在未来 M 小时继续跑赢”。
3. Data：确认数据来源、字段、频率、幸存者偏差、缺失、延迟、可交易性。
4. Feature/Factor：构造信号，做覆盖率、分布、IC、分组收益、turnover 检查。
5. Strategy：把信号变成交易规则，包括仓位、调仓、费用、风控。
6. Backtest：只用当时可见数据，按可成交价格模拟交易，加入费用、滑点、资金费率、延迟。
7. Robustness：样本外、walk-forward、参数稳定性、成本敏感性、市场状态分解。
8. Paper/Demo：用真实行情和模拟资金验证数据、订单、风控、日志和告警。
9. Small Live：极小资金、低杠杆、强门控，验证真实成交和运行风险。
10. Monitoring：服务健康、PnL attribution、异常成交、数据中断、风控触发。
11. Review：定期复盘策略是否仍符合原假设，是否降级、暂停或扩容。

### 1.4 逻辑框架

- Alpha：预测或解释未来收益的信号。
- Risk：收益波动、回撤、尾部、杠杆、流动性、相关性、模型失效。
- Cost：手续费、滑点、冲击成本、资金费率、借贷费、gas、税费。
- Portfolio：多信号、多标的、多周期如何合成目标仓位。
- Execution：如何把目标仓位变成订单，如何处理撤单、部分成交、重试。
- Operations：服务如何运行，异常如何发现，何时自动停机。

## 2. 常见量化策略分类

### 2.1 方向型策略

- 趋势跟随 / 时间序列动量：资产上涨后继续做多，下跌后减仓或做空。
- 截面动量：同一时点买强卖弱，关注相对强弱排序。
- 均值回归 / 反转：价格偏离短期均衡后回归。
- 宏观择时：用利率、通胀、流动性、美元、风险偏好等解释资产大周期。

### 2.2 相对价值和市场中性

- 统计套利：利用价差、残差、协整关系或因子暴露偏离。
- 配对交易：交易两个高度相关资产的相对偏离。
- 基差 / 期限结构：交易现货、期货、永续、远期之间的价差。
- 多因子组合：用价值、动量、质量、低波、流动性等因子做资产选择。

### 2.3 套利与结构性策略

- 跨交易所套利：同一资产在不同交易所价格不同。
- 三角套利：同一交易所内多币种兑换路径价格不一致。
- 资金费率套利：永续合约 funding 与现货/其他合约对冲。
- ETF/现货/期货套利：利用一篮子资产和衍生品之间的定价关系。
- AMM/DeFi 套利：链上池子和中心化/去中心化市场价格偏离。

### 2.4 流动性与执行策略

- 做市：同时挂买卖单，赚取 spread、rebate 或流动性补偿。
- 高频预测：用 order book、逐笔成交、队列、短期冲击预测几秒内价格。
- 执行算法：TWAP、VWAP、POV、Implementation Shortfall，目标是降低交易成本。
- 库存管理：控制做市或执行过程中的方向暴露。

## 3. 量化交易开发流程

### 3.1 研究前

- 写 Strategy Card，而不是直接写代码。
- 明确策略是否依赖价格、成交、盘口、资金费率、链上、新闻、宏观或多源数据。
- 明确最小可交易频率：日频策略不需要 tick 架构，高频策略不能只用 K 线。
- 明确容量假设：个人小资金可以交易的机会，不一定能扩容。

### 3.2 数据层

最低要求：

- 原始数据可追溯：保留 ODS/raw，避免无法复盘。
- 标准数据可复用：OHLCV、funding、order book、trades、liquidations 等进入统一 DWD。
- 数据质量可检查：缺失、重复、乱序、异常价格、成交量异常、时间戳偏移。
- 数据版本可记录：每次研究报告能说明用的什么数据、什么代码、什么配置。

本仓库对应模块：

- `src/quant_system/data.py`
- `src/quant_system/storage.py`
- `src/quant_system/data_quality.py`
- `DATA_STACK.md`

### 3.3 因子和信号层

最低要求：

- 因子定义清楚：输入字段、窗口、滞后、归一化、缺失处理。
- 因子评估先于策略回测：覆盖率、IC/RankIC、分组收益、turnover、稳定性。
- 避免未来函数：信号只能使用成交前已确认的数据。
- 因子版本化：参数变化、代码变化、数据变化都要可追踪。

本仓库对应模块：

- `src/quant_system/factors.py`
- `src/quant_system/alpha.py`
- `src/quant_system/research.py`
- `knowledge/bitcoin_strategy_knowledge_base.yaml`

### 3.4 回测层

最低要求：

- 使用下一根 bar 或真实可成交价格成交，不能用同一根 K 线收盘价生成并成交。
- 加入手续费、滑点、资金费率、延迟和最小下单量。
- 报告 benchmark，不只看策略自身收益。
- 做参数稳定性、walk-forward、成本敏感性、市场状态拆分。
- 对多重测试做惩罚或至少提示，不把“搜索出来的最好结果”当真实能力。

本仓库对应模块：

- `src/quant_system/backtest.py`
- `src/quant_system/benchmarks.py`
- `src/quant_system/reports.py`
- `PLATFORM_FOUNDATION_TASKS.md`

### 3.5 交易和运行层

最低要求：

- paper 优先，实盘默认关闭。
- broker、risk、strategy 共用同一接口，避免研究和实盘逻辑分裂。
- 每个信号、目标仓位、订单、风控拦截都有审计记录。
- 支持 kill switch、watchdog、heartbeat、连续错误熔断。
- live 必须有显式配置和人工确认，不允许默认自动实盘。

本仓库对应模块：

- `src/quant_system/broker.py`
- `src/quant_system/risk.py`
- `src/quant_system/live.py`
- `src/quant_system/service.py`
- `src/quant_system/notifications.py`

## 4. 个人量化平台基座清单

### 4.1 必须具备的基座

- 数据接入：交易所 API、历史分页、增量更新、限速和重试。
- 数据存储：raw、standardized、features、reports、orders、events 分层。
- 数据质量：缺失、重复、乱序、异常点、stale guard。
- 研究环境：可重复运行、固定配置、固定 universe、报告自动落盘。
- 因子框架：统一 factor id、参数、版本、评估指标。
- 回测引擎：事件驱动、成交模拟、费用模型、持仓和现金账本。
- 组合构建：目标权重、约束、换手、再平衡、风险预算。
- 风控系统：单标的暴露、组合暴露、杠杆、日亏、回撤、订单限制。
- Broker 接口：下单、撤单、查余额、查持仓、精度处理、错误分类。
- 运行服务：循环、heartbeat、PID lock、stop file、watchdog。
- 审计和报告：JSON/SQLite/日志，能回答“为什么下了这笔单”。
- 告警和停机：通知、kill switch、异常熔断。
- 配置和密钥：配置文件、环境变量、demo/prod 分离、无提现权限。

### 4.2 可以后置的能力

- Web 控制台。
- 自动机器学习因子挖掘。
- 多交易所全自动跨市场调度。
- tick 级撮合回放。
- 新闻/链上/社媒多源实时特征。
- 高可用集群部署。

这些能力有价值，但在个人平台早期不应优先于数据质量、回测可信度、风控和审计。

## 5. 平台自检清单

### 5.1 研究可信度自检

- 数据是否存在幸存者偏差、缺失、重复、时间戳错误？
- 信号是否只使用成交前已知信息？
- 回测是否考虑手续费、滑点、资金费率、延迟、最小交易单位？
- 策略是否跑过样本外、walk-forward 和参数稳定性？
- 是否有 benchmark：现金、buy-and-hold、简单趋势、随机入场？
- 是否记录所有参数搜索，避免只保存最好结果？
- 收益是否集中在极少数交易或极少数市场阶段？
- 收益对成本、延迟、滑点、资金费率是否过度敏感？

### 5.2 部署就绪自检

- paper 运行是否稳定超过指定观察期？
- 是否能从服务日志和审计表复盘每次信号和订单？
- API key 是否无提现权限，demo/prod 是否隔离？
- live 是否默认关闭，并需要配置和命令双重确认？
- kill switch 是否能阻断新订单？
- watchdog 是否能发现服务停止、心跳过期、连续失败？
- 告警是否覆盖下单、风控拦截、数据过期、服务异常？
- 小资金上限、单标的暴露、日亏、回撤熔断是否明确？

## 6. 加密货币市场结构

### 6.1 Crypto 与传统市场的主要差异

- 24/7 连续交易，没有统一收盘价。
- 交易所碎片化，同一资产在不同 venue 上流动性和价格不同。
- 永续合约是核心交易品种，资金费率是重要状态变量。
- 杠杆、清算、强平瀑布会造成非线性尾部风险。
- 手续费等级、maker/taker、返佣、VIP 等对策略影响很大。
- 小币种存在更强的流动性、下架、操纵、跳价和数据质量风险。
- 链上交易还要考虑 gas、MEV、区块确认、合约风险和桥风险。

### 6.2 关键数据

- OHLCV：低频和中频策略基础。
- Funding：永续多空拥挤、基差和 carry 收益来源。
- Open Interest：杠杆和拥挤程度。
- Basis：现货与永续/期货价差。
- Long/Short Ratio：交易者持仓倾向，但要警惕口径差异。
- Order Book：深度、价差、队列、盘口不平衡。
- Trades：主动买卖、成交冲击、短期流。
- Liquidations：强平压力和尾部状态。
- Exchange Rules：tick size、lot size、min notional、杠杆、保证金规则。

本仓库已覆盖其中多项 OKX 数据，可优先用 `README.md` 里的 data/research 命令做练习。

## 7. 加密货币策略类型分类

### 7.1 低频趋势 / 时间序列动量

机制：crypto 常有强趋势和高波动，趋势策略试图跟随中期行情。

常用信号：

- N 日/N 小时收益率。
- 均线突破。
- 波动率调整动量。
- 高点/低点突破。

主要风险：

- 震荡市反复止损。
- 高收益集中在少数大行情。
- 参数容易过拟合。
- 小币种滑点和跳价吞噬收益。

本仓库练习：

- 运行 `research adaptive-trend`。
- 检查 `adaptive_trend_*` 报告的参数稳定性、成本敏感性和 walk-forward。

### 7.2 截面动量 / 轮动

机制：在一个币种池中买入相对强势资产，回避或做空弱势资产。

常用信号：

- 过去 N 小时/天收益排序。
- 排除最近短窗口反转后的残差动量。
- 成交额和流动性过滤后的 top-N 组合。

主要风险：

- universe 幸存者偏差。
- 小币种流动性不足。
- 牛市中多头腿贡献很大，空头腿未必稳定。
- 调仓换手高，成本敏感。

本仓库练习：

- 运行 `research xsmom` 和 `research xsmom-grid`。
- 对比 `cross_sectional_momentum_*` 报告里的成本敏感性和参数稳定性。

### 7.3 短期反转 / 均值回归

机制：短期过度反应、流动性冲击或强平后可能回补。

常用信号：

- 短窗口极端收益反向。
- 偏离均线或 VWAP。
- 成交量/清算冲击后的回归。
- order book imbalance 极端后的修复。

主要风险：

- 趋势行情中逆势加仓。
- 真实成交可能接不到理论价格。
- 高频反转强依赖盘口和延迟。

本仓库练习：

- 从现有 trend/mr 策略拆出单独均值回归假设。
- 设计“清算冲击后反转”的 Strategy Card，先不实盘。

### 7.4 配对交易 / 协整 / 残差回归

机制：高度相关资产之间的价差偏离后回归，例如 BTC/ETH 或同生态资产。

常用信号：

- 价差 z-score。
- 回归残差。
- 协整检验。
- beta-hedged spread。

主要风险：

- 关系断裂。
- beta 漂移。
- 两腿成交不同步。
- 极端行情中相关性上升但价差继续扩张。

本仓库练习：

- 运行 `research btc-eth-cointegration`。
- 检查报告是否覆盖 OOS、成本和失效条件。

### 7.5 资金费率 / 基差 / Cash-and-Carry

机制：永续价格相对现货偏离时，通过 funding 机制向多空一方转移现金流；交易者可用现货和永续对冲，尝试赚取 funding 或 basis 收敛。

常用策略：

- 现货多 + 永续空，赚正 funding。
- 跨交易所 funding 差异套利。
- 基差均值回归。
- funding 预测和择时。

主要风险：

- funding 反转。
- 保证金和强平。
- 现货/合约两腿滑点。
- 交易所风险和资金划转延迟。
- 极端行情中 basis 扩大而非收敛。

本仓库练习：

- 运行 `data funding`、`data basis`、`research funding-carry`。
- 用 `funding_carry_*` 报告检查资金费率压力场景。

### 7.6 跨交易所套利 / 三角套利

机制：同一资产或兑换路径在不同交易所/市场出现价格不一致。

常用策略：

- CEX-CEX 价差套利。
- CEX-DEX 价差套利。
- 三角路径套利。
- 跨市场 liquidity mirroring。

主要风险：

- 价差消失速度快。
- 提现/划转慢。
- 手续费、gas、滑点吞噬利润。
- 一腿成交、一腿失败。
- API 限速和风控冻结。

学习重点：

- 先在 paper/dry-run 中验证净利润口径。
- 必须有库存预置和两腿失败处理，不能假设实时搬砖一定可行。

### 7.7 做市

机制：在买卖两边挂限价单，赚取 spread、返佣或流动性补偿，同时管理库存风险。

常用策略：

- 简单对称挂单。
- Avellaneda-Stoikov 库存风险模型。
- 多层报价。
- 波动率和订单流自适应 spread。
- 跨交易所做市：maker venue 挂单，taker venue 对冲。

主要风险：

- 被信息优势交易者打中。
- 单边行情库存失控。
- 撤单延迟和队列劣势。
- 手续费等级不足。
- 高频系统工程复杂。

学习重点：

- 做市不是“低风险套利”，核心是库存、逆向选择、延迟和费用。
- 个人平台如果没有稳定 websocket、订单状态机和风控，不应直接做真实做市。

### 7.8 高频 / 微观结构预测

机制：使用 order book、trades、队列、短期成交冲击等预测秒级或更短窗口的价格变化。

常用特征：

- order book imbalance。
- spread、depth、queue position。
- aggressive buy/sell flow。
- trade sign。
- short-horizon realized volatility。
- cancellation/replenishment pattern。

主要风险：

- 数据量和基础设施要求高。
- 延迟决定收益能否成交。
- 回测必须接近真实撮合，否则结果容易虚高。
- 交易所 API、限速、网络、订单状态异常都会直接影响策略。

学习重点：

- 初学阶段只做微观结构研究和数据探索，不直接部署 HFT。
- 先建立 L2/L3 数据、撮合回放、订单状态机、延迟测量。

### 7.9 链上 / 情绪 / 新闻策略

机制：使用链上资金流、交易所净流入、巨鲸地址、稳定币发行、社媒情绪、新闻事件等信息预测价格或波动。

主要风险：

- 数据供应商口径差异。
- 信号拥挤和延迟。
- 容易做成解释型故事，而非可交易信号。
- 新闻和社媒数据有噪声、操纵和版权/接口限制。

学习重点：

- 先把链上/情绪数据当作 regime filter 或风险提示，而不是直接下单信号。

### 7.10 DeFi / AMM 套利和流动性提供

机制：AMM 池子价格因交易和流动性变化偏离外部市场，套利者或 LP 承担库存和无常损失风险。

常用方向：

- CEX-DEX 套利。
- AMM 池间套利。
- 集中流动性 LP 策略。
- MEV/searcher 策略。

主要风险：

- gas 和拥堵。
- MEV 竞争。
- 合约和桥风险。
- 模拟环境与真实链上执行差异大。

学习重点：

- DeFi 策略应独立成子课程；当前 OKX-first 平台先不作为主线实盘方向。

## 8. 推荐资料库

### 8.1 通用量化与回测可信度

| 优先级 | 资料 | 用途 |
| --- | --- | --- |
| P0 | [A Backtesting Protocol in the Era of Machine Learning](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3275654) | 建立研究协议、避免把数据挖掘当 alpha。 |
| P0 | [The Deflated Sharpe Ratio](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551) | 理解选择偏差、非正态和多重测试对 Sharpe 的影响。 |
| P1 | [Advances in Financial Machine Learning](https://www.wiley.com/en-us/Advances+in+Financial+Machine+Learning-p-9781119482086) | 系统学习金融 ML、purged CV、标签、回测风险。 |
| P1 | [Algorithmic and High-Frequency Trading](https://www.cambridge.org/core/books/algorithmic-and-highfrequency-trading/7B7F26F16D8F2E43C837B7B052C7C06B) | 学习最优执行、做市和 HFT 数学框架。 |

### 8.2 市场微观结构与做市

| 优先级 | 资料 | 用途 |
| --- | --- | --- |
| P0 | [High-frequency Trading in a Limit Order Book](https://people.orie.cornell.edu/sfs33/LimitOrderBook.pdf) | Avellaneda-Stoikov 做市模型经典论文。 |
| P0 | [Hummingbot Avellaneda Market Making Docs](https://hummingbot.org/strategies/v1-strategies/avellaneda-market-making/) | 看经典模型如何被工程化为 crypto 做市策略。 |
| P1 | [Hummingbot Avellaneda Technical Deep Dive](https://hummingbot.org/blog/technical-deep-dive-into-the-avellaneda--stoikov-strategy/) | 理解参数、reservation price、optimal spread、库存控制。 |
| P1 | [Cross-Exchange Market Making - Hummingbot](https://hummingbot.org/strategies/v1-strategies/cross-exchange-market-making/) | 学习跨交易所做市/对冲架构。 |

### 8.3 Crypto 策略综述和因子

| 优先级 | 资料 | 用途 |
| --- | --- | --- |
| P0 | [Quantitative Alpha in Crypto Markets](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5225612) | crypto 因子、套利、机器学习应用综述。 |
| P0 | [Cryptocurrency Momentum and Reversal](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3913263) | 学习 crypto 动量和反转的基本证据。 |
| P0 | [Cross-sectional Momentum in Cryptocurrency Markets](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4322637) | 截面动量和趋势跟随在 crypto 的构造方式。 |
| P1 | [Intraday Return Predictability in the Cryptocurrency Markets](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4080253) | 日内动量/反转、跳跃、流动性、FOMC 等状态条件。 |
| P1 | [Machine Learning and the Cross-Section of Cryptocurrency Returns](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4295427) | crypto 截面收益预测和 ML 特征重要性。 |
| P1 | [Momentum and liquidity in cryptocurrencies](https://arxiv.org/abs/1904.00890) | 动量和流动性的关系。 |

### 8.4 永续、资金费率和基差

| 优先级 | 资料 | 用途 |
| --- | --- | --- |
| P0 | [A Primer on Perpetual Futures - Coinbase](https://www.coinbase.com/en-gb/institutional/research-insights/research/market-intelligence/a-primer-on-perpetual-futures/) | 永续合约、funding 和市场指标入门。 |
| P0 | [Funding Rate Mechanism in Perpetual Futures](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6185958) | 将 funding 视为反馈机制，理解 basis 和 funding tails。 |
| P1 | [The Two-Tiered Structure of Cryptocurrency Funding Rate Markets](https://www.mdpi.com/2227-7390/14/2/346) | CEX/DEX funding 市场结构、套利成本和价差持续性。 |
| P1 | [Perpetual Futures Contracts and Cryptocurrency Market Quality](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4218907) | 永续合约对现货市场质量的影响。 |
| P2 | [Designing funding rates for perpetual futures in cryptocurrency markets](https://arxiv.org/abs/2506.08573) | 更理论化的 funding rate 设计。 |

### 8.5 Crypto 工程框架和教程

| 优先级 | 资料 | 用途 |
| --- | --- | --- |
| P0 | [Hummingbot Documentation](https://hummingbot.org/docs/) | 参考开源 crypto 做市/套利 bot 的模块化设计。 |
| P0 | [CCXT Documentation](https://docs.ccxt.com/) | 学习多交易所 API 抽象、限速、统一接口。 |
| P1 | [AMM Arbitrage - Hummingbot](https://hummingbot.org/strategies/v1-strategies/amm-arbitrage/) | 学习 AMM/CEX 套利的工程口径和成本口径。 |
| P1 | [Hummingbot Strategies V1](https://hummingbot.org/strategies/v1-strategies/) | 对照常见 crypto bot 策略分类。 |

## 9. 分阶段学习计划

### 单元 1：量化交易全局框架

目标：建立“idea -> data -> factor -> strategy -> backtest -> paper -> live -> review”的全流程认知。

阅读：

- 本文第 1-2 章。
- `DOMAIN.md`
- `ARCHITECTURE.md`

实践：

- 画出当前仓库的研究到交易链路。
- 说明当前平台已实现和未实现的边界，避免把 future work 当作现有能力。

检查题：

- Alpha、risk、cost、portfolio、execution 分别解决什么问题？
- 为什么不能只看回测收益率？
- 一个策略进入 paper 前至少要过哪些门？

### 单元 2：研究协议和回测陷阱

目标：理解未来函数、选择偏差、过拟合、多重测试、样本外。

阅读：

- A Backtesting Protocol in the Era of Machine Learning。
- The Deflated Sharpe Ratio。
- 本文第 3.4 和第 5.1 节。

实践：

- 选择一个已有 `reports/*_latest.json`，检查是否有 benchmark、成本、walk-forward、参数稳定性。
- 写一份“这个报告还不能证明什么”的反证清单。

检查题：

- 为什么参数网格的最优点通常不可信？
- walk-forward 和普通 train/test split 有什么不同？
- crypto 回测里 funding 和滑点为什么不能省略？

### 单元 3：个人量化平台基座

目标：明确个人平台从研究到部署必须具备的最小能力。

阅读：

- 本文第 4-5 章。
- `PLATFORM_FOUNDATION_TASKS.md`
- `DATA_STACK.md`

实践：

- 对照第 4.1 节给当前仓库打勾/标注待补。
- 运行或阅读 `service pre-live-check` 相关说明，理解为什么 live 必须门控。

检查题：

- 为什么数据层要分 raw/standardized/features/reports？
- 为什么 paper 和 live 应该复用 broker/risk/strategy 接口？
- kill switch 和 watchdog 分别解决什么问题？

### 单元 4：Crypto 市场结构和核心数据

目标：理解现货、永续、funding、basis、OI、order book、liquidation。

阅读：

- Coinbase perpetual futures primer。
- Funding Rate Mechanism in Perpetual Futures。
- 本文第 6 章。

实践：

- 运行 OKX funding、basis、open interest、orderbook、trades 的数据命令。
- 写一张“每个数据字段对应什么策略用途”的表。

检查题：

- 永续合约为什么需要 funding？
- funding 高是否一定代表应该做空永续？
- OI、funding、basis 同时升高可能说明什么？

### 单元 5：动量、趋势和轮动

目标：掌握 crypto 中低频方向策略和截面策略。

阅读：

- Cryptocurrency Momentum and Reversal。
- Cross-sectional Momentum in Cryptocurrency Markets。
- Momentum and liquidity in cryptocurrencies。
- 本文第 7.1-7.2 节。

实践：

- 运行 `research xsmom`、`research adaptive-trend`。
- 对比趋势策略和截面动量策略在成本、换手、市场状态上的差异。

检查题：

- 时间序列动量和截面动量的核心区别是什么？
- 为什么 crypto 动量策略必须做流动性过滤？
- 为什么只在牛市有效的策略不能直接晋级？

### 单元 6：均值回归、配对和统计套利

目标：理解价格偏离、价差、残差、协整和 beta hedge。

阅读：

- 本文第 7.3-7.4 节。
- 选择一篇统计套利或 pairs trading 教程作为补充读物。

实践：

- 运行 `research btc-eth-cointegration`。
- 写 BTC/ETH 配对策略的 Strategy Card。

检查题：

- 相关性和协整有什么不同？
- 价差继续扩张时如何控制风险？
- 两腿成交不同步会造成什么问题？

### 单元 7：资金费率、基差和套利

目标：理解 delta-neutral carry 的收益、风险和容量限制。

阅读：

- The Two-Tiered Structure of Cryptocurrency Funding Rate Markets。
- Perpetual Futures Contracts and Cryptocurrency Market Quality。
- 本文第 7.5-7.6 节。

实践：

- 运行 `research funding-carry`、`funding-carry-grid`、`funding-carry-costs`。
- 写一份 funding 策略的压力测试清单。

检查题：

- funding carry 为什么不是无风险收益？
- 正 funding 反转会如何影响现货多 + 永续空？
- 跨交易所 funding 套利为什么可能被转账和成交风险吞噬？

### 单元 8：做市和市场微观结构

目标：理解 spread、库存、逆向选择、订单簿、队列和延迟。

阅读：

- High-frequency Trading in a Limit Order Book。
- Hummingbot Avellaneda Market Making Docs。
- Hummingbot Cross-Exchange Market Making Docs。
- 本文第 7.7-7.8 节。

实践：

- 只做设计，不做实盘：写“个人平台要支持做市还缺什么”的基座清单。
- 分析 OKX orderbook/trades 数据能否支持基础盘口研究。

检查题：

- 做市策略赚的是什么，亏的通常是什么？
- Avellaneda-Stoikov 中库存风险如何影响 reservation price？
- 为什么没有订单状态机和低延迟数据就不应做真实 HFT？

### 单元 9：链上、情绪、新闻和 DeFi

目标：理解非价格数据和链上执行策略的边界。

阅读：

- Quantitative Alpha in Crypto Markets 中 on-chain、ML、arbitrage 相关部分。
- AMM Arbitrage - Hummingbot。
- 本文第 7.9-7.10 节。

实践：

- 设计一个链上数据只作为风险过滤器的 Strategy Card。
- 列出 DeFi 策略不能复用当前 OKX-first 架构的部分。

检查题：

- 链上数据为什么容易有解释力但不一定可交易？
- AMM 套利和 CEX 套利的主要工程差异是什么？
- MEV/gas/合约风险如何进入回测？

### 单元 10：阶段复盘和下一步建设

目标：把学习结果转化为平台路线图。

产出：

- 一份策略候选清单：研究型、paper 候选、暂不做、禁止实盘。
- 一份平台缺口清单：数据、回测、风控、执行、监控、文档。
- 一份下一阶段任务：只选 1-3 个最值得实现的改进，不铺太大。

检查题：

- 哪类策略最适合当前平台优先研究？
- 哪些策略必须等数据/执行基座补齐后才能碰？
- 当前平台进入小资金 live 前还有哪些硬门槛？

## 10. 建议的首次学习入口

下一次学习建议从“单元 1：量化交易全局框架”开始。完成后再进入“单元 2：研究协议和回测陷阱”。不要先跳到 HFT 或做市实盘；这些方向对数据、延迟、订单状态机和风控要求最高，适合后置。
