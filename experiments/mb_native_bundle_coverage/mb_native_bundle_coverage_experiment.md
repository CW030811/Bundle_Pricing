# MB Native Bundle Customer Coverage Experiment

## Objective

Analyze bundle coverage under the original MB (Mixed Bundling) data setting
with non-uniform Ns segment weights, and compare with CPBSD-setting results.

## Data Source

| Config | Dataset | m (segments) | n (products) | Bundle space | Samples |
|--------|---------|-------------|-------------|-------------|---------|
| m10 | `m10_n10_sample_100` | 10 | 10 | 1024 | 100 |
| m20 | `m20_n10_sample_100` | 20 | 10 | 1024 | 100 |
| m30 | `m30_n10_sample_100` | 30 | 10 | 1024 | 100 |

## Coverage Definition

- **Ns-weighted coverage**: For each segment k choosing bundle B,
  add `Ns[k]` to that bundle's coverage. Since `sum(Ns) = 1` per sample,
  total coverage per sample = 1.0.
- Averaged across 100 samples per m-value.
- Bundles ranked by average Ns-weighted coverage, descending.
- This is the TRUE Ns-weighted metric (non-uniform segment weights),
  unlike the CPBSD setting which uses uniform 1/K weights.

## Key Results

### m10

- Active bundles: 438 / 1024 (42.8%)

| Top-N | Cumulative Coverage |
|-------|-------------------|
| 1 | 2.80% |
| 2 | 4.66% |
| 3 | 6.40% |
| 5 | 9.58% |
| 10 | 16.05% |
| 20 | 25.10% |
| 50 | 42.24% |

| Coverage | Bundles Needed |
|----------|---------------|
| 50% | 70 |
| 80% | 198 |
| 90% | 269 |
| 95% | 319 |
| 99% | 389 |

### m20

- Active bundles: 642 / 1024 (62.7%)

| Top-N | Cumulative Coverage |
|-------|-------------------|
| 1 | 2.82% |
| 2 | 4.57% |
| 3 | 6.26% |
| 5 | 9.26% |
| 10 | 15.97% |
| 20 | 24.14% |
| 50 | 40.08% |

| Coverage | Bundles Needed |
|----------|---------------|
| 50% | 79 |
| 80% | 254 |
| 90% | 368 |
| 95% | 449 |
| 99% | 558 |

### m30

- Active bundles: 759 / 1024 (74.1%)

| Top-N | Cumulative Coverage |
|-------|-------------------|
| 1 | 2.55% |
| 2 | 4.06% |
| 3 | 5.48% |
| 5 | 8.22% |
| 10 | 14.01% |
| 20 | 21.46% |
| 50 | 37.28% |

| Coverage | Bundles Needed |
|----------|---------------|
| 50% | 93 |
| 80% | 295 |
| 90% | 432 |
| 95% | 533 |
| 99% | 660 |

### Top-20 Bundles Detail (m10)

| Rank | ID | Binary | Size | Count | Ns-Share | Cumulative | Avg Price |
|------|----|--------|------|-------|----------|------------|-----------|
| 1 | 1023 | 1111111111 | 10 | 29 | 2.80% | 2.80% | 2.40 |
| 2 | 1007 | 1111101111 | 9 | 14 | 1.86% | 4.66% | 2.31 |
| 3 | 1015 | 1111110111 | 9 | 14 | 1.75% | 6.40% | 2.31 |
| 4 | 895 | 1101111111 | 9 | 14 | 1.61% | 8.01% | 2.32 |
| 5 | 511 | 0111111111 | 9 | 15 | 1.58% | 9.58% | 2.31 |
| 6 | 1019 | 1111111011 | 9 | 16 | 1.49% | 11.07% | 2.31 |
| 7 | 959 | 1110111111 | 9 | 13 | 1.31% | 12.39% | 2.33 |
| 8 | 1021 | 1111111101 | 9 | 15 | 1.28% | 13.66% | 2.30 |
| 9 | 766 | 1011111110 | 8 | 10 | 1.27% | 14.93% | 2.24 |
| 10 | 767 | 1011111111 | 9 | 10 | 1.11% | 16.05% | 2.40 |
| 11 | 991 | 1111011111 | 9 | 9 | 1.06% | 17.11% | 2.34 |
| 12 | 987 | 1111011011 | 8 | 8 | 1.01% | 18.11% | 2.21 |
| 13 | 1022 | 1111111110 | 9 | 9 | 0.99% | 19.10% | 2.35 |
| 14 | 1018 | 1111111010 | 8 | 9 | 0.98% | 20.08% | 2.20 |
| 15 | 975 | 1111001111 | 8 | 9 | 0.95% | 21.03% | 2.22 |
| 16 | 507 | 0111111011 | 8 | 8 | 0.89% | 21.92% | 2.19 |
| 17 | 447 | 0110111111 | 8 | 7 | 0.88% | 22.80% | 2.16 |
| 18 | 887 | 1101110111 | 8 | 8 | 0.80% | 23.60% | 2.24 |
| 19 | 894 | 1101111110 | 8 | 7 | 0.76% | 24.36% | 2.18 |
| 20 | 503 | 0111110111 | 8 | 7 | 0.74% | 25.10% | 2.19 |

## Comparison: MB Native vs CPBSD

| Metric | CPBSD (n=5, K=50) | MB m=10 | MB m=20 | MB m=30 |
|--------|-------------------|---------|---------|---------|
| Bundle space | 32 | 1024 | 1024 | 1024 |
| Active bundles | 32 | 438 | 642 | 759 |
| Segment weights | uniform 1/K | Ns (non-uniform) | Ns | Ns |
| Top-1 coverage | 36.4% | 2.8% | 2.8% | 2.6% |
| Top-5 coverage | 60.7% | 9.6% | 9.3% | 8.2% |
| Top-10 coverage | 74.1% | 16.0% | 16.0% | 14.0% |
| Top-20 coverage | 90.3% | 25.1% | 24.1% | 21.5% |
| Bundles for 50% | 3 | 70 | 79 | 93 |
| Bundles for 80% | 13 | 198 | 254 | 295 |
| Bundles for 90% | 20 | 269 | 368 | 432 |

## Conclusion

### 核心发现

1. **MB 原生 setting 下 bundle 覆盖极度分散。**
   n=10 时共 1024 种可能 bundle，Top-20 只能覆盖约 21–25% 的 Ns 加权需求；
   达到 80% 覆盖需要 198–295 个 bundle（占 bundle 空间的 19–29%）。
   这与 CPBSD setting（Top-20 覆盖 90.3%）形成鲜明对比。

2. **分段数 m 越大，覆盖越分散。**
   m=10 时 438 个 bundle 被选中（42.8%）；m=30 时上升到 759 个（74.1%）。
   更多细分客户群导致更多差异化 bundle 需求，单个 bundle 的平均权重被稀释。

3. **两个 setting 间差异的来源。**
   覆盖集中度的差距主要来自三个因素：
   - **n 的差异**：n=5 → 32 bundles，n=10 → 1024 bundles。指数级增长的 bundle 空间本身就降低了单一 bundle 的命中率。
   - **无购买选项的影响**：CPBSD 中空 bundle（不购买）独占 36.4%，极大提升了 Top-1 集中度；MB 数据中无此效应（求解器不含空 bundle 的外部选项）。
   - **Ns 非均匀权重 vs 均匀权重**：Ns 的随机性使少数大权重客户被分配到不同 bundle，进一步分散覆盖。

4. **Top-20 bundle 的组成结构（m10 为例）。**
   Top-20 几乎全部是 size=8–10 的大 bundle（包含 8–10 个产品），
   其中 Rank-1 固定为全产品 bundle (1111111111)。
   说明 MB 最优解倾向于让高权重客户购买接近全集的 bundle，利润主要来自大 bundle 定价。

### MB vs CPBSD 综合对比

| 维度 | CPBSD (n=5, K=50, 均匀权重) | MB (n=10, m=10–30, Ns 权重) |
|------|---------------------------|---------------------------|
| Bundle 空间 | 32 | 1024 |
| 活跃 bundle 比例 | 100% | 42.8–74.1% |
| Top-1 覆盖 | 36.4%（空 bundle 主导） | 2.6–2.8% |
| Top-20 覆盖 | 90.3% | 21.5–25.1% |
| 80% 覆盖所需 bundle 数 | 13（占 40.6%） | 198–295（占 19.3–28.8%） |
| 覆盖分布形态 | 陡峭的帕累托曲线 | 近似对数曲线，长尾显著 |
| 是否支持"少数 bundle 覆盖大部分需求" | 部分支持（但含空 bundle 贡献） | **不支持** |

### 对 GCN 加速策略的 Implications

上述覆盖率分析对 GCN-based 加速策略有如下关键启示：

**1. GCN 在 MB 原生 setting 下面临更高的预测难度。**
在 CPBSD (n=5) 中，GCN 只需从 32 个候选 bundle 中预测正确组合，且 Top-20 已覆盖 90%——
即使预测不精确，high-recall 策略仍能捕获大部分最优解。
而在 MB (n=10) 中，1024 个候选 bundle 里 Top-20 仅覆盖 ~25%，
GCN 必须在一个远更分散的分布上做出准确预测，否则初始解质量将大幅下降。

**2. 阈值型策略（FCP）可能失效。**
FCP 通过对 GCN 的边概率 P[k,j] 应用全局阈值来决定 bundle 组合。
当最优 bundle 分布集中时，阈值容易校准（大多数客户选相似的 bundle）；
当分布分散如 MB setting 时，不同客户的最优 bundle 大小和组成差异很大（size 8–10 混合），
单一全局阈值无法同时适配所有客户段，预测准确率将显著下降。

**3. Local Search 的必要性更强，但搜索空间也更大。**
在 CPBSD 中，GCN 初始解即使偏差也只需少量 LS 迭代修正（32 个 bundle × K 个客户的邻域）。
在 MB (n=10) 中，每次 LS 迭代的邻域规模为 O(2n × m)，且需要覆盖更多候选 bundle，
使得 LS 收敛所需迭代数和每次迭代的 LP/MILP 调用数都可能大幅增加。
Global Top-K LS (`LS_Path_Test.py`) 的 K=ceil(sqrt(m)) 策略在 m=10 时 K=4，
仅探索 8 个邻居/迭代——这在分散的 MB setting 下可能不足以找到好的改进方向。

**4. 分层 / 渐进式策略更有潜力。**
鉴于 MB 最优 bundle 以大 bundle 为主（size 8–10），GCN 可以采用分层策略：
- **第一层**：预测每个客户的最优 bundle size（1–10）——size 分布相对集中（8–10），较易预测；
- **第二层**：在给定 size 约束下预测具体产品组合——搜索空间从 C(10,k) 而非 2^10。
这种分层设计可大幅缩减搜索空间，与 PCP（渐进式选择预测）的思路一致，
但需要在 GCN 架构中显式编码 size 信息。

**5. 对训练数据和评估指标的启示。**
- **训练数据**：需要确保训练集覆盖足够多样的 bundle 组合（438+ 种 active bundles）。
  如果训练集过小或 bundle 分布有偏，GCN 将无法泛化到长尾 bundle。
- **评估指标**：在 MB setting 下，edge-level accuracy（单个产品是否包含在 bundle 中）
  比 bundle-level exact match 更实际——因为 exact match 在分散分布下几乎不可能达到高值。
  建议引入 Jaccard similarity 或 bundle-size MAE 等更宽容的指标。
- **类别不平衡**：Top-1 bundle 仅占 2.8%，而长尾 bundle 各 <0.5%。
  BCEWithLogitsLoss 需要配合样本加权或 focal loss 以避免模型退化为"总是预测全集 bundle"。

**6. 实际加速效果的预期调整。**
在 CPBSD (n=5) 上取得的 GCN 加速比（LP 调用减少约 64%）
不应直接外推到 MB (n=10) 场景。
由于覆盖分散、搜索空间大、GCN 预测精度下降，
实际加速比在 MB setting 下可能大幅降低。
建议在 n=10 MB 数据上重新基线测试 GCN 各策略（FCP / PCP / LS），
以获得真实的加速效果评估。

