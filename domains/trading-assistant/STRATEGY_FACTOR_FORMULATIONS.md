# 现有策略与因子数学表达汇总

版本日期：2026-06-03

本文件汇总当前 `trading-assistant` 域已经实现、研究中或登记为候选的策略/因子。公式以本仓库代码和知识库为准，主要来源：

- `src/quant_system/strategies.py`
- `src/quant_system/factors.py`
- `src/quant_system/alpha.py`
- `src/quant_system/research.py`
- `knowledge/bitcoin_strategy_knowledge_base.yaml`
- `config/default.yaml`

默认技术指标参数：`fast_ema=12`、`slow_ema=48`、`rsi_period=14`、`atr_period=14`、`bollinger_period=20`、`bollinger_std=2.0`。默认交易成本：`fee_rate=0.0008`、`slippage_bps=2`。

## 0. 符号约定

- `P_t`：第 `t` 根 bar 的收盘价。
- `O_t`：第 `t` 根 bar 的开盘价。
- `H_t`、`L_t`：第 `t` 根 bar 的最高价、最低价。
- `V_t`：成交量。
- `r_t = P_t / P_{t-1} - 1`：简单收益率。
- `EMA_n(P)_t`：价格 `P` 的 `n` 期指数移动平均。
- `ATR_n`：`n` 期平均真实波幅。
- `BB_mid_t = SMA_n(P)_t`。
- `BB_upper_t = BB_mid_t + k * std_n(P)_t`。
- `BB_lower_t = BB_mid_t - k * std_n(P)_t`。
- `target_pct`：策略输出的目标仓位百分比，正数为做多，负数为做空。
- 现货策略不能表达空头仓位；swap/永续策略可以表达空头仓位。

## 1. 策略总览

| 名称 | 代码/登记 ID | 状态 | 类型 | 主要数据 | 当前定位 |
| --- | --- | --- | --- | --- | --- |
| EMA 趋势 | `trend` | 已实现 | 时间序列趋势 | OHLCV | 基础单资产趋势策略 |
| RSI/Bollinger 均值回归 | `mean_reversion` / `rsi_bollinger_reversion` | 已实现 | 均值回归 | OHLCV | 研究用单资产反转策略 |
| 趋势 + 均值回归组合 | `trend_mr` | 已实现 | 规则组合 | OHLCV | BTC 时间序列动量 baseline |
| 波动率调整趋势 | `vol_trend` | 已实现 | 趋势 + 波动率缩放 | OHLCV/ATR | BTC 低复杂度趋势 baseline |
| Donchian 突破 | `donchian_breakout` | 已实现 | 通道突破 | OHLCV | 研究用突破策略 |
| BTC 波动率突破 | `btc_volatility_breakout` | 已实现 | 压缩后突破 | OHLCV/ATR/波动率 | 研究用 BTC 单资产策略 |
| BTC 实现波动率目标 | `btc_realized_volatility_targeting` | 已实现 | 风险覆盖/波动率目标 | OHLCV/realized vol | 保守 BTC 暴露 overlay |
| 截面动量组合 | `cross_sectional_momentum` | 已实现研究/纸交易候选 | 截面动量/轮动 | 多资产 OHLCV | 当前 primary paper candidate |
| 自适应趋势组合 | `adaptive_trend` | 已实现研究 | 趋势 + 风险调整组合 | 多资产 OHLCV | 低回撤 backup candidate |
| 资金费率 carry | `funding_carry` | 已实现研究 | 永续 carry/相对价值 | funding | research only |
| BTC/ETH 协整配对 | `btc_eth_cointegration_pairs` | 已实现研究 | 统计套利/配对 | 双资产 OHLCV | research only |
| 外部 alpha 因子组合 | `alpha_ensemble` | 已实现研究 | 因子 transform ensemble | 内置/外部因子 | research only |
| 网格交易 | `btc_grid_trading` | 候选未实现 | 网格/库存策略 | OHLCV + 订单状态 | 需库存回测器 |
| Altcoin-BTC 残差反转 | `altcoin_btc_arbitrage_factor_reversion` | 因子已实现，策略未实现 | 统计套利 | 多资产 OHLCV | factor research |
| 盘口做市/HFT | `btc_orderbook_market_making` | 候选未实现 | 做市/微观结构 | L2/L3 + trades + latency | 暂不优先 |

## 2. 已实现信号策略

### 2.1 EMA 趋势策略 `trend`

类型：时间序列动量 / 趋势跟随。

数学表达：

```text
fast_t = EMA_fast(P)_t
slow_t = EMA_slow(P)_t
```

规则：

```text
if len(data) < slow_ema or V_t < min_volume:
    target_pct = 0
elif fast_t > slow_t and RSI_t < 75:
    target_pct = 0.15
elif fast_t < slow_t and instrument_type == swap:
    target_pct = -0.10
else:
    target_pct = 0
```

市场逻辑：

- 中期趋势持续时，短期均线高于长期均线代表上涨趋势。
- RSI 低于 75 是过热过滤，避免在短线明显过度上涨后追高。
- 现货只做多/空仓；永续可在下跌趋势中表达小幅空头。

重要风险：

- 震荡市容易反复追涨杀跌。
- EMA 滞后，趋势反转初期会亏损。
- 单一 BTC 趋势 baseline 不能替代组合策略。

### 2.2 均值回归策略 `mean_reversion`

类型：短期均值回归 / 技术反转。

数学表达：

```text
BB_lower_t = SMA_bollinger(P)_t - bollinger_std * std_bollinger(P)_t
BB_upper_t = SMA_bollinger(P)_t + bollinger_std * std_bollinger(P)_t
```

规则：

```text
if len(data) < bollinger_period:
    target_pct = 0
elif P_t < BB_lower_t and RSI_t < 35:
    target_pct = 0.10
elif P_t > BB_upper_t and instrument_type == swap:
    target_pct = -0.08
else:
    target_pct = 0
```

市场逻辑：

- 价格跌破下轨且 RSI 偏弱，代表短期过度抛售，可能出现技术反弹。
- 价格突破上轨时，永续可表达短期回落预期。
- 该逻辑更适合震荡、有流动性冲击但没有强趋势延续的环境。

重要风险：

- 下跌趋势中容易接飞刀。
- Crash continuation 时 RSI 和 Bollinger 都会持续极端。
- 必须配合趋势/风险过滤，当前不应作为独立 live 策略。

### 2.3 RSI/Bollinger 反转 `rsi_bollinger_reversion`

类型：均值回归。

数学表达和规则：

```text
rsi_bollinger_reversion == mean_reversion
```

市场逻辑：

- 这是 `MeanReversionStrategy` 的同逻辑包装，用于在策略 sweep 中以独立名称评估 RSI + Bollinger 家族。

当前定位：

- `knowledge/bitcoin_strategy_knowledge_base.yaml` 中登记为 `rsi_bollinger_btc_reversion`。
- `promotion_status = research_only`。

### 2.4 趋势 + 均值回归组合 `trend_mr`

类型：规则组合 / 趋势与反转混合。

数学表达：

```text
target_raw_t = target_trend_t * confidence_trend_t
             + target_mr_t * confidence_mr_t

target_pct_t = clip(target_raw_t, -0.15, 0.20)
confidence_t = min(0.90, max(confidence_trend_t, confidence_mr_t))
```

市场逻辑：

- 趋势信号负责参与持续行情。
- 均值回归信号负责捕捉短期超跌/超涨修复。
- 两者按置信度加权，输出一个统一目标仓位。

重要风险：

- 趋势和反转逻辑可能在不同市场状态下互相抵消。
- 简单加权不是优化器，无法保证组合后风险更低。
- 当前在知识库中是 BTC 时间序列动量 baseline，不是 primary paper candidate。

### 2.5 波动率调整趋势 `vol_trend`

类型：趋势跟随 + 波动率归一化。

数学表达：

```text
trend_strength_t = (EMA_fast(P)_t - EMA_slow(P)_t) / P_t
atr_pct_t = max(ATR_t / P_t, 0.005)
raw_t = trend_strength_t / atr_pct_t
target_pct_t = clip(0.10 * raw_t, -0.15, 0.20)

if spot:
    target_pct_t = max(target_pct_t, 0)
```

市场逻辑：

- EMA 差值代表趋势方向和强度。
- 用 ATR 百分比归一化，避免在高波动阶段给过大仓位。
- 趋势越强、单位波动越低，目标仓位越高。

重要风险：

- ATR 估计滞后，无法提前处理跳空或急跌。
- 低波动趋势可能导致仓位偏大。
- 仍然是趋势策略，震荡市会亏损。

### 2.6 Donchian 通道突破 `donchian_breakout`

类型：突破 / Turtle-style trend following。

默认窗口：`lookback=55`，`exit_lookback=20`。

数学表达：

```text
upper_t = max(H_{t-lookback}, ..., H_{t-1})
lower_t = min(L_{t-lookback}, ..., L_{t-1})
exit_low_t = min(L_{t-exit_lookback}, ..., L_{t-1})
exit_high_t = max(H_{t-exit_lookback}, ..., H_{t-1})
```

规则：

```text
if P_t > upper_t:
    target_pct = 0.18
elif P_t < lower_t and instrument_type == swap:
    target_pct = -0.12
elif P_t < exit_low_t or (swap and P_t > exit_high_t):
    target_pct = 0
else:
    target_pct = 0
```

市场逻辑：

- 突破过去 N 根 bar 的高点说明价格脱离旧区间，可能进入趋势扩张。
- 短窗口通道用于退出，避免回吐过多。

重要风险：

- 假突破多，尤其在 crypto 新闻和流动性扰动下。
- 若没有 ATR sizing 或止损，风险暴露较粗糙。
- 当前为 research only。

### 2.7 BTC 波动率突破 `btc_volatility_breakout`

类型：低波动压缩后的突破。

默认窗口：`range_lookback=72`，`compression_lookback=120`。

数学表达：

```text
upper_t = max(H_{t-range_lookback}, ..., H_{t-1})
lower_t = min(L_{t-range_lookback}, ..., L_{t-1})
recent_vol_t = std(r_{t-range_lookback+1}, ..., r_t)
baseline_vol_t = std(r_{t-compression_lookback+1}, ..., r_t)
compressed_t = recent_vol_t <= 1.15 * baseline_vol_t
trend_ok_t = EMA_fast(P)_t >= EMA_slow(P)_t
atr_pct_t = max(ATR_t / P_t, 0.0001)
```

规则：

```text
if P_t > upper_t and compressed_t and trend_ok_t:
    target_pct = min(0.20, max(0.08, 0.16 / max(atr_pct_t / 0.02, 1.0)))
elif P_t < lower_t or EMA_fast(P)_t < EMA_slow(P)_t:
    target_pct = -0.08 if swap else 0
else:
    target_pct = 0
```

市场逻辑：

- 低波动区间后的上破可能触发趋势扩张、止损单和跟随资金。
- 趋势过滤减少逆大势突破。
- ATR 百分比越高，突破仓位越保守。

重要风险：

- 压缩判定使用 realized volatility，可能滞后。
- 假突破和消息面反转会造成快速亏损。
- 当前仍需 BTC-only sweep、regime split 和成本敏感性验证。

### 2.8 BTC 实现波动率目标 `btc_realized_volatility_targeting`

类型：风险覆盖 / volatility targeting overlay。

默认窗口：`volatility_bars = 24 * 14`，`target_annual_vol = 0.25`。

数学表达：

```text
ann_vol_t = max(std(r_{t-volatility_bars+1}, ..., r_t) * sqrt(24 * 365), 0.05)
trend_score_t = EMA_fast(P)_t / EMA_slow(P)_t - 1
raw_exposure_t = target_annual_vol / ann_vol_t
```

规则：

```text
if trend_score_t > 0:
    target_pct = min(raw_exposure_t * 0.20, 0.25)
elif instrument_type == swap and trend_score_t < -0.01:
    target_pct = -min(raw_exposure_t * 0.10, 0.12)
else:
    target_pct = 0
```

市场逻辑：

- 目标波动率思想：波动高时降仓，波动低时允许更高暴露。
- 趋势过滤避免在下行/无趋势阶段裸多。
- 更像仓位 overlay，而不是独立 alpha。

重要风险：

- realized vol 对未来跳跃风险反应滞后。
- 大跌后波动升高可能低仓错过反弹。
- 适合作为保守风险控制模块对比 `vol_trend`。

## 3. 已实现组合研究策略

### 3.1 截面动量组合 `cross_sectional_momentum`

类型：截面动量 / 多币种轮动。

默认窗口：`lookback_bars = 24 * 30`，`hold_bars = 24 * 7`，`top_n = 1`。

数学表达：

```text
score_{i,t} = P_{i,t} / P_{i,t-lookback} - 1
selected_t = TopN_i(score_{i,t})
```

组合规则：

```text
每 hold_bars 调仓一次：
1. 全部卖出旧持仓。
2. 按 score 排序买入 top_n 个标的。
3. 对 selected_t 等权分配资金。
4. 买卖都计入 fee 和 slippage。
```

市场逻辑：

- Crypto 市场经常出现主题轮动和强弱分化。
- 过去一段时间强势的币种，可能在未来一段时间继续吸引资金。
- 截面排名比单资产趋势更关注“买哪个币”，适合多资产 universe。

重要风险：

- Universe 幸存者偏差和流动性过滤非常重要。
- 强反转行情中，上一期强势币可能成为下一期跌幅最大资产。
- 调仓周期较长时可能错过快速切换；周期较短时成本和换手上升。

当前定位：

- 知识库标记为 `primary_paper_candidate`。
- 策略短名单建议保留为 active paper-trading strategy。

### 3.2 自适应趋势组合 `adaptive_trend`

类型：趋势跟随 + 风险调整组合 / 低回撤备选策略。

默认窗口：`lookback_bars = 24 * 30`，`hold_bars = 24 * 7`，`top_n = 2`，`ema_span = 24 * 20`，`volatility_bars = 24 * 14`，`target_volatility = 0.20`，`max_weight = 0.50`。

数学表达：

```text
r_{i,t} = P_{i,t} / P_{i,t-1} - 1
rolling_sharpe_{i,t} = mean(r_i, lookback) / std(r_i, lookback)
trend_ok_{i,t} = P_{i,t} > EMA_ema_span(P_i)_t
score_{i,t} = rolling_sharpe_{i,t}, only if score > 0 and trend_ok
selected_t = TopN_i(score_{i,t})

ann_vol_{i,t} = std(r_i, volatility_bars) * sqrt(24 * 365)
raw_weight_{i,t} = min(target_volatility / ann_vol_{i,t} / len(selected_t), max_weight)
weights_t = normalize so sum(weights) <= 1
```

组合规则：

```text
每 hold_bars 调仓一次：
1. 卖出旧持仓。
2. 仅保留 rolling_sharpe > 0 且价格高于 EMA 的标的。
3. 选择 score 最高的 top_n。
4. 按目标波动率分配权重，保留未使用现金。
5. 计入 fee 和 slippage。
```

市场逻辑：

- 只参与有正风险调整收益且处于上行趋势的资产。
- 用波动率目标降低高波动资产的权重。
- 比单纯截面动量更保守，目标是降低回撤。

重要风险：

- rolling Sharpe 和 realized vol 都有估计误差。
- 参数多于简单动量，更需要 walk-forward 和参数稳定性。
- 可能在快速反弹时因趋势/波动过滤过慢而低仓。

当前定位：

- 知识库标记为 `backup_paper_candidate`。
- 策略短名单建议作为 low-drawdown backup，不替代 active paper strategy。

### 3.3 资金费率 carry `funding_carry`

类型：永续资金费率 carry / 相对价值。

默认窗口：`lookback_periods = 3`，`hold_periods = 1`，`top_n = 2`，`min_funding_rate = 0`，`max_notional_pct = 1.0`。

数学表达：

```text
score_{i,t} = mean(funding_rate_{i,t-lookback}, ..., funding_rate_{i,t-1})
selected_t = TopN_i(score_{i,t}), only if score_{i,t} > min_funding_rate
weight_{i,t} = max_notional_pct / len(selected_t)
```

资金费率 PnL：

```text
funding_pnl_t = equity_t * sum_i(weight_{i,t} * funding_rate_{i,t})
```

换仓成本：

```text
two_leg_cost_rate = 2 * (fee_rate + slippage_bps / 10000)
cost_t = equity_t * turnover_weight_t * two_leg_cost_rate
```

市场逻辑：

- 永续合约的 funding 是多空拥挤和基差压力的现金流补偿。
- 当某个合约近期 funding 持续为正时，做空永续并用现货/其他腿对冲可能收取 funding。
- 当前实现更偏 funding ranking 研究模型，尚未完整模拟现货-永续 delta-neutral 两腿、保证金和强平。

重要风险：

- Funding 会突然翻转。
- Basis squeeze、保证金、强平距离和两腿成交风险没有完全建模。
- 当前 walk-forward 证据弱，知识库标记为 `research_only`。

### 3.4 BTC/ETH 协整配对 `btc_eth_cointegration_pairs`

类型：统计套利 / 配对均值回归。

默认窗口：`lookback_bars = 24 * 30`，`entry_z = 2.0`，`exit_z = 0.5`，`max_hold_bars = 24 * 7`，`max_gross_exposure = 0.50`。

数学表达：

```text
x_t = log(P_base,t)
y_t = log(P_hedge,t)
beta_t = rolling_cov(x, y, lookback) / rolling_var(y, lookback)
beta_t = clip(beta_t, 0.1, 5.0)

spread_t = x_t - beta_t * y_t
z_t = (spread_t - mean(spread, lookback)) / std(spread, lookback)
```

交易方向：

```text
if current_side == 0 and z_t >= entry_z:
    next_side = -1   # short spread: short base, long hedge
elif current_side == 0 and z_t <= -entry_z:
    next_side = 1    # long spread: long base, short hedge
elif abs(z_t) <= exit_z or holding_bars >= max_hold_bars:
    next_side = 0
```

权重：

```text
denominator = 1 + beta_t
weight_base = side * max_gross_exposure / denominator
weight_hedge = -side * max_gross_exposure * beta_t / denominator
```

市场逻辑：

- BTC 和 ETH 长期共同受 crypto beta 驱动，短期价差可能偏离后回归。
- Rolling hedge ratio 用于估计 ETH 对 BTC 的动态 beta。
- Dollar-neutral spread 降低整体市场方向暴露。

重要风险：

- 当前没有正式 cointegration p-value gate。
- BTC/ETH 结构关系可能断裂。
- 两腿执行、借券/保证金、短仓限制和极端行情扩散风险仍需加强。

### 3.5 外部 alpha 因子组合 `alpha_ensemble`

类型：因子 transform ensemble / CTA-style signal research。

输入：

```text
factor_values = {ts, symbol, factor}
```

支持 transform：

```text
ma_diff:
    ma_t = rolling_mean(factor, window)
    momentum long: factor_t > ma_t * (1 + threshold)
    momentum short: factor_t < ma_t * (1 - threshold)

z_score:
    z_t = (factor_t - rolling_mean_t) / rolling_std_t
    momentum long: z_t > threshold
    momentum short: z_t < -threshold

minmax:
    normalized_t = (factor_t - rolling_min_t) / (rolling_max_t - rolling_min_t)
    momentum long: normalized_t > threshold
    momentum short: normalized_t < 1 - threshold

robust_scaling:
    scaled_t = (factor_t - rolling_median_t) / (IQR_t + 1e-10)
    momentum long: scaled_t > threshold
    momentum short: scaled_t < -threshold

box_cox:
    adjusted factor is shifted positive if needed
    transformed_t = (adjusted_t ** 0.3 - 1) / 0.3
    then use z_score-style threshold

rate_of_change:
    roc_t = pct_change(factor, window) * 100
    momentum long: roc_t > threshold
    momentum short: roc_t < -threshold
```

`style = reversion` 时，多空条件反向。

Position type：

```text
long_only:  signal = 1 if long_cond else 0
short_only: signal = -1 if short_cond else 0
binary_LS:  signal = 1 if long_cond else -1
binary_SL:  signal = -1 if short_cond else 1
long_short: signal = 1 if long_cond, -1 if short_cond, else 0
```

组合：

```text
group_signal = mean(transform_signals within group)
ensemble_signal = clip(sum(group_signal_g * weight_g) / sum(abs(weight_g)), -1, 1)
```

当前 example 配置：

| Group | Factor | Weight | Transform |
| --- | --- | --- | --- |
| `btc_time_series_momentum_transforms` | `btc_time_series_momentum_336h` | 0.25 | `ma_diff` / `z_score`, long-only momentum |
| `volatility_adjusted_btc_trend_transforms` | `volatility_adjusted_btc_trend` | 0.25 | `robust_scaling`, long-only momentum |
| `funding_carry_transforms` | `funding_carry_recent` | 0.20 | `rate_of_change`, long-short momentum |
| `cross_sectional_momentum_transforms` | `cross_sectional_momentum_720h` | 0.30 | `minmax`, long-only momentum |

市场逻辑：

- 把不同来源的 alpha 因子统一转换成有界交易信号。
- 用多个 transform 检查同一因子是否在不同标准化方法下仍有预测力。
- 当前只用于研究评估，不直接进入 paper/live。

重要风险：

- Transform 和 threshold 容易参数过拟合。
- 外部因子可能 stale、格式错误或不可交易。
- 组合权重是显式研究权重，不是优化结果。

## 4. 已实现因子

### 4.1 Crypto 动量因子 `crypto_momentum_24h`

类型：价格动量因子。

默认窗口：`lookback_bars = 24`。

数学表达：

```text
factor_{i,t} = P_{i,t} / P_{i,t-24} - 1
```

市场逻辑：

- 捕捉短周期趋势延续。
- 可用于截面排序或时间序列趋势判断。

注意：

- 单独 24h 动量可能很噪声，需结合流动性、成本和市场状态。

### 4.2 Crypto 反转因子 `crypto_reversal_6h`

类型：短期反转因子。

默认窗口：`lookback_bars = 6`。

数学表达：

```text
factor_{i,t} = -(P_{i,t} / P_{i,t-6} - 1)
```

市场逻辑：

- 过去 6 小时跌得越多，因子越高，表达短期反弹预期。
- 过去 6 小时涨得越多，因子越低，表达短期回落预期。

注意：

- 在强趋势和崩盘延续中风险很高。

### 4.3 成交量压力因子 `crypto_volume_pressure`

类型：成交量异常 / liquidity pressure。

默认窗口：`lookback_bars = 24`。

数学表达：

```text
mean_vol_{i,t} = rolling_mean(V_i, 24)
std_vol_{i,t} = rolling_std(V_i, 24)
factor_{i,t} = (V_{i,t} - mean_vol_{i,t}) / std_vol_{i,t}
```

市场逻辑：

- 异常成交量代表资金流、消息冲击或强制交易。
- 可作为趋势确认、反转过滤或风险状态变量。

注意：

- 仅有量能没有方向，通常需要和价格收益、盘口或清算数据结合。

### 4.4 截面动量因子 `cross_sectional_momentum_720h`

类型：截面动量因子。

默认窗口：`lookback_bars = 24 * 30 = 720`。

数学表达：

```text
factor_{i,t} = P_{i,t} / P_{i,t-720} - 1
```

市场逻辑：

- 过去约 30 天表现更强的币种，可能继续获得资金关注。
- 这是 `cross_sectional_momentum` 组合策略的因子化版本。

当前定位：

- `factor_pipeline_ready`。
- 对应策略是 primary paper candidate。

### 4.5 自适应趋势质量因子 `adaptive_trend_quality`

类型：趋势质量 / 风险调整动量。

默认窗口：`return_bars = 720`，`volatility_bars = 336`，`ema_span = 480`。

数学表达：

```text
ret_{i,t} = P_{i,t} / P_{i,t-return_bars} - 1
vol_{i,t} = rolling_std(r_i, volatility_bars)
ema_{i,t} = EMA_ema_span(P_i)_t
trend_filter_{i,t} = max(P_{i,t} / ema_{i,t} - 1, 0)

factor_{i,t} = (ret_{i,t} / vol_{i,t}) * trend_filter_{i,t}
```

市场逻辑：

- 只奖励价格高于 EMA 的正趋势资产。
- 用收益/波动刻画趋势质量，而不是只看收益绝对值。
- 对应 `adaptive_trend` 组合策略。

注意：

- 低波动资产可能因 `ret/vol` 变大而得分高，需要权重上限和流动性过滤。

### 4.6 资金费率 carry 因子 `funding_carry_recent`

类型：funding carry 因子。

默认窗口：`lookback_periods = 3`，频率 `8H`。

数学表达：

```text
factor_{i,t} = mean(funding_rate_{i,t-2}, funding_rate_{i,t-1}, funding_rate_{i,t})
```

市场逻辑：

- 正 funding 说明多头愿意向空头支付费用，可能存在 carry 收益。
- 近期平均 funding 越高，潜在 carry 越高。

注意：

- 该因子本身不是完整 delta-neutral 策略。
- 需要现货/永续两腿、保证金、basis、强平距离和交易所约束才能接近真实交易。

### 4.7 BTC 时间序列动量因子 `btc_time_series_momentum_336h`

类型：BTC 时间序列动量。

默认窗口：`lookback_bars = 24 * 14 = 336`。

数学表达：

```text
factor_t = P_t / P_{t-336} - 1
```

市场逻辑：

- 约 14 天 BTC 趋势延续。
- 用作 BTC-only baseline 和 alpha ensemble 输入。

注意：

- 当前更适合作为 baseline IC screening，不是独立 paper candidate。

### 4.8 波动率调整 BTC 趋势因子 `volatility_adjusted_btc_trend`

类型：风险调整动量。

默认窗口：`lookback_bars = 336`，`volatility_bars = 336`。

数学表达：

```text
momentum_t = P_t / P_{t-336} - 1
realized_vol_t = rolling_std(r, 336)
factor_t = momentum_t / realized_vol_t
```

市场逻辑：

- 同样的动量收益，如果波动更低，则风险调整后的趋势质量更高。
- 与 `vol_trend` 类似，但使用收益/realized volatility，而非 EMA spread/ATR。

注意：

- realized volatility 过小会放大因子，需稳定性和异常值检查。

### 4.9 Altcoin-BTC 残差反转因子 `altcoin_btc_residual_reversion`

类型：统计套利 / 残差均值回归因子。

默认窗口：`lookback_bars = 336`，`beta_window = 720`，`btc_symbol = BTC/USDT`。

数学表达：

```text
r_btc,t = P_btc,t / P_btc,t-1 - 1
r_i,t = P_i,t / P_i,t-1 - 1
beta_{i,t} = rolling_cov(r_i, r_btc, beta_window) / rolling_var(r_btc, beta_window)
residual_{i,t} = r_i,t - beta_{i,t} * r_btc,t
residual_return_{i,t} = sum(residual_i over lookback_bars)
factor_{i,t} = -residual_return_{i,t}
```

市场逻辑：

- 先剥离 altcoin 对 BTC 的 beta 暴露。
- 如果某个 altcoin 相对 BTC 因子过度跑输，残差反转因子变高，表达相对修复预期。
- 如果过度跑赢，因子变低，表达回落预期。

当前定位：

- 因子已实现。
- 策略构建和回测尚未开始，知识库为 `not_started`。

重要风险：

- Altcoin beta 会漂移。
- 小币种流动性、下架、meme squeeze 和短仓可得性是关键风险。
- 需要 dollar-neutral portfolio 和 liquidity/concentration cap。

## 5. 候选但未实现策略

### 5.1 BTC 网格交易 `btc_grid_trading`

类型：网格 / 库存型 market making。

候选数学表达：

```text
range = [P_low, P_high]
grid_levels_k = P_low + k * (P_high - P_low) / K
```

核心规则：

- 在区间内分层挂买单和卖单。
- 低位成交买入，高位成交卖出。
- 库存和单格 notional 必须有限制。
- 趋势突破、库存过大或费用超过格距时停止。

市场逻辑：

- 横盘震荡时，价格在区间内来回波动，网格试图收割波动。

为什么尚未实现：

- 需要库存状态、订单状态、部分成交、撤单、重新挂单的模拟器。
- 仅用 OHLCV 回测容易高估网格收益。

### 5.2 BTC 盘口做市 / HFT `btc_orderbook_market_making`

类型：做市 / 高频微观结构。

候选数学表达：

```text
mid_t = (best_bid_t + best_ask_t) / 2
imbalance_t = bid_depth_t / (bid_depth_t + ask_depth_t)
microprice_t = (best_ask_t * bid_depth_t + best_bid_t * ask_depth_t)
             / (bid_depth_t + ask_depth_t)
edge_t = expected_short_horizon_move_t - fees - adverse_selection_cost
```

核心规则：

- 当预期 edge 超过费用和逆向选择成本时双边或单边报价。
- 报价随库存、盘口不平衡、队列位置和波动率变化。
- 库存超过阈值时停止偏向一侧或强制降仓。

市场逻辑：

- 提供流动性赚 spread、rebate 或短期订单流边际。

为什么尚未实现：

- 需要 L2/L3 order book、trades、latency、queue model 和微观结构回放。
- 当前平台虽有 orderbook/trades snapshot 数据，但还不是 HFT 级执行基座。
- 知识库明确建议不作为首个 live 系统优先方向。

## 6. 因子评估与晋级口径

### 6.1 Forward return

价格类因子：

```text
forward_return_{i,t,h} = P_{i,t+h} / P_{i,t} - 1
```

Funding 类因子：

```text
forward_return_{i,t,h} = sum(funding_rate_{i,t+1}, ..., funding_rate_{i,t+h})
```

### 6.2 IC / RankIC

每个时间截面计算：

```text
IC_t = corr(factor_{i,t}, forward_return_{i,t,h})
RankIC_t = corr(rank(factor_{i,t}), rank(forward_return_{i,t,h}))
```

汇总：

```text
mean_ic = mean(IC_t)
icir = mean(IC_t) / std(IC_t)
positive_ic_rate = mean(IC_t > 0)
```

### 6.3 分位数组合

每个时间截面按因子值分成 `quantiles` 组：

```text
top_bottom_mean = mean(return_top_quantile - return_bottom_quantile)
```

市场逻辑：

- 如果高因子组未来收益稳定高于低因子组，因子更可能有截面预测力。

### 6.4 Turnover

```text
turnover_t = 1 - |Top_t ∩ Top_{t-1}| / |Top_{t-1}|
```

市场逻辑：

- 高 turnover 会放大手续费、滑点和执行风险。
- 因子收益如果依赖频繁换手，需要更严格成本敏感性检查。

## 7. 当前策略分层判断

### 7.1 当前主线

- `cross_sectional_momentum`：当前最重要的 paper 候选，已完成 walk-forward 和成本验证，继续作为 active paper strategy。
- `adaptive_trend`：低回撤备选，适合作为 backup paper candidate。

### 7.2 研究保留

- `funding_carry`：逻辑重要，但当前证据和执行/保证金模型不足，保留 research only。
- `btc_eth_cointegration_pairs`：可复现研究策略，但缺少 cointegration 稳定性门控和完整两腿约束。
- `alpha_ensemble`：适合 alpha discovery，不应直接进入 live。
- `donchian_breakout`、`rsi_bollinger_reversion`、`btc_volatility_breakout`、`btc_realized_volatility_targeting`：适合 BTC 单资产研究和 baseline 对比。

### 7.3 暂不推进实盘

- `btc_grid_trading`：先补库存/订单状态回测器。
- `btc_orderbook_market_making`：先补 L2/L3、latency、queue model、订单状态机和微观结构模拟。
- `altcoin_btc_arbitrage_factor_reversion`：因子可研究，但策略和交易约束尚未实现。

## 8. 下一步建议

1. 先围绕 `cross_sectional_momentum` 和 `adaptive_trend` 继续学习和复盘，因为它们最贴近当前平台主线。
2. 对 `funding_carry` 单独开一章，补齐现货-永续两腿、保证金、basis、funding reversal 和 liquidation distance。
3. 对 BTC 单资产策略做统一 baseline 表：收益、回撤、Sharpe、成本敏感性、适用 regime、失败 regime。
4. 不急于做网格和 HFT；这两类策略的关键不是公式，而是订单状态、库存、延迟和撮合仿真。
