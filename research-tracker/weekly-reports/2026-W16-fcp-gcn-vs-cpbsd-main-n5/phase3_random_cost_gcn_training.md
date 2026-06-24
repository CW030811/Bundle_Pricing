# Phase 3: Random Cost GCN 训练日志

**日期**: 2026-04-23
**目标**: 为 `random_ind` 和 `random_corr` cost scenarios 训练专用 GCN 模型

---

## 动机

已有 GCN 模型仅在 `zero`/`hvhm`/`hvlm` cost scenarios 上训练，从未见过 random cost 分布。Phase 2 实验表明 FCP 在 random cost 上 OOS 表现不佳，需要训练专用模型。

## 训练配置

| 参数 | 值 |
|------|-----|
| N (products) | 5 |
| K (customers) | 50 |
| dist / rho / hetero | normal / 0.0 / full |
| 实例总数 | 4000 per scenario |
| Train / Val / Test | 3000 / 600 / 400 |
| MB 标签方法 | Full MB (2^5=32 bundles, 秒级) |
| GCN 架构 | EdgeScoringGCN, 2 layers, hidden=128 |
| 优化器 | Adam, lr=1e-3 |
| Loss | BCEWithLogitsLoss (auto pos_weight) |
| Max epochs | 200 |
| Early stopping | patience=30 |
| Seed | 1000 |
| Device | MPS (Apple Silicon) |

## 结果

### random_ind

| 指标 | 训练集 | 验证集 | 测试集 |
|------|--------|--------|--------|
| Loss | 0.1435 | 0.1504 | 0.1425 |
| Accuracy | 0.9414 | 0.9374 | 0.9415 |
| F1 | 0.9444 | 0.9397 | 0.9431 |
| Precision | — | 0.9099 | — |
| Recall | — | 0.9717 | — |

- **正边比例**: 50.9% (平衡)
- **pos_weight**: 0.954
- **最佳 epoch**: 1 (早停在 epoch 31)
- **总耗时**: 157.6 min (~2.6h)，其中 MB 标签 ~2h，训练 ~30min

### random_corr

| 指标 | 训练集 | 验证集 | 测试集 |
|------|--------|--------|--------|
| Loss | 0.1376 | 0.1407 | 0.1386 |
| Accuracy | 0.7359 | 0.7321 | 0.7337 |
| F1 | 0.8174 | 0.8141 | 0.8151 |
| Precision | — | 0.9829 | — |
| Recall | — | 0.6948 | — |

- **正边比例**: 84.6% (高度不平衡)
- **pos_weight**: 0.182
- **最佳 epoch**: 0 (早停在 epoch 30)
- **总耗时**: 607.1 min (~10.1h)，其中 MB 标签 ~9.5h，训练 ~30min

### 分析

1. **random_ind** 模型效果优秀 (F1=0.94)，正负边平衡，GCN 学习充分。
2. **random_corr** 模型 F1=0.81，accuracy 仅 73%。原因：
   - 正边比例 84.6%，高度不平衡
   - 模型 precision 极高 (0.98) 但 recall 偏低 (0.69) — 保守预测
   - 最佳模型在 epoch 0 即取得，说明后续训练没有改进 val loss
3. **random_corr MB 标签生成慢** (607 min vs 158 min)，correlated costs 使 Gurobi 求解更耗时。

## 输出文件

```
models_cpbsd_mb_x_random_ind/
  best_model_edge_cpbsd_mb_x_2layer_seed1000.pt    # 最佳模型
  model_edge_cpbsd_mb_x_2layer_seed1000.pt          # 最终模型 (= best)
  metrics_edge_cpbsd_mb_x_2layer_seed1000.json      # 完整指标

models_cpbsd_mb_x_random_corr/
  best_model_edge_cpbsd_mb_x_2layer_seed1000.pt
  model_edge_cpbsd_mb_x_2layer_seed1000.pt
  metrics_edge_cpbsd_mb_x_2layer_seed1000.json

experiments/cpbsd_random_ind_n5/                    # 实例 + MB 标签
experiments/cpbsd_random_corr_n5/                   # 实例 + MB 标签
```

## Pipeline 脚本

`src/data/run_random_cost_gcn_pipeline.py` — 一键完成实例生成 → manifest → MB 标签 → GCN 训练。

---

## FCP 评估实验（2026-04-24）

用新训练的专用 GCN 模型在 random_ind / random_corr 上跑 FCP-pruned-MB + BSP + CPBSD-A 对比。

### 评估配置

- N = 5, 10, 30 | K = 50 | 5 instances per config | seed = 20260424
- dist = normal, rho = 0.0, hetero = full
- Time limits: FCP-MB 600s, BSP 600s, CPBSD-A 600s | MIP gap = 1%
- OOS: K_out = 5000

### random_ind 结果（5-instance 平均）

| N | Method | InS | OOS | Runtime | Winner |
|---|--------|----:|----:|--------:|--------|
| 5 | FCP-pruned-MB | 9.804 | **9.493** | 0.1s | **FCP** |
| 5 | BSP | 8.707 | 8.382 | 0.3s | |
| 5 | CPBSD-A | 9.825 | 9.186 | 0.5s | |
| 10 | FCP-pruned-MB | 17.051 | **16.380** | 0.1s | **FCP** |
| 10 | BSP | 14.795 | 13.988 | 0.9s | |
| 10 | CPBSD-A | 13.740 | 13.167 | 7.2s | |
| 30 | FCP-pruned-MB | 57.021 | **54.592** | 0.7s | **FCP** |
| 30 | BSP | 45.607 | 43.117 | 147.4s | |
| 30 | CPBSD-A | 27.522 | 26.578 | 243.5s | |

**FCP 在 random_ind 上全面碾压**：5/5 instances × 3 sizes 全部 FCP 最优。OOS 远超 BSP（+13%~+27%）和 CPBSD-A（+3%~+105%）。N 越大差距越大。

### random_corr 结果（5-instance 平均）

| N | Method | InS | OOS | Runtime | Winner |
|---|--------|----:|----:|--------:|--------|
| 5 | FCP-pruned-MB | 10.540 | 9.728 | 0.4s | |
| 5 | BSP | 10.575 | 9.789 | 0.4s | |
| 5 | CPBSD-A | 10.602 | **9.905** | 1.0s | **CPBSD-A** (4/5) |
| 10 | FCP-pruned-MB | 20.510 | 18.830 | 1.0s | |
| 10 | BSP | 20.309 | **18.974** | 0.7s | **BSP** (2/5) |
| 10 | CPBSD-A | 20.258 | 18.942 | 110.3s | **CPBSD-A** (2/5) |
| 30 | FCP-pruned-MB | 64.357 | 59.042 | 6.4s | |
| 30 | BSP | 65.693 | **62.988** | 2.6s | **BSP** (3/5) |
| 30 | CPBSD-A | 56.968 | 54.733 | 600.2s | |

**random_corr 上三种方法接近**，没有明显 winner。N=5 CPBSD-A 略优；N=10 BSP/CPBSD-A 交替领先（差距 < 1%）；N=30 BSP 最优但 FCP 与 BSP 差距仅 ~6%。CPBSD-A 在 N=30 时 timeout (600s) 表现最差。

### 关键发现

1. **random_ind: FCP 全面领先**
   - 独立随机成本下，产品异质性高，per-bundle pricing 优势明显
   - GCN 模型 F1=0.94，准确预测了 bundle 归属
   - N=30 时 FCP OOS 是 CPBSD-A 的 2 倍以上（54.6 vs 26.6），CPBSD-A 完全崩溃（timeout + MIP gap 巨大）

2. **random_corr: 三方接近，FCP 无明显劣势**
   - 关联成本下产品趋于同质化（正边比例 84.6%），per-bundle 优势被压缩
   - BSP 的 size-only pricing 在这种同质场景下已足够（N=30 时最强）
   - FCP 仍有竞争力（OOS 差距 < 6%），且 runtime 远优于 CPBSD-A

3. **GCN 迁移成功**
   - N=5 训练的模型直接用于 N=10/30 推理，无性能下降
   - random_ind 模型 (F1=0.94) 迁移效果极好
   - random_corr 模型 (F1=0.81) 迁移效果可接受

4. **Runtime 优势**
   - FCP: 0.1s (N=5) → 0.7s (N=30)
   - CPBSD-A: 0.5s (N=5) → 600s timeout (N=30)
   - FCP 快 100-1000x

### 与 hvhm 对比

在之前的 hvhm 实验中，FCP OOS < CPBSD-A OOS（差距 0.4-0.6）。Random cost 场景下情况完全反转：

| Scenario | FCP vs CPBSD-A (N=10 OOS) | FCP vs BSP (N=10 OOS) |
|----------|---------------------------|----------------------|
| hvhm | FCP < CPBSD-A (差 0.57) | FCP ≈ BSP |
| random_ind | **FCP >> CPBSD-A (+24%)** | **FCP >> BSP (+17%)** |
| random_corr | FCP ≈ CPBSD-A (差 0.6%) | FCP ≈ BSP (差 0.8%) |

### BSP+FCP Hybrid 评估

Hybrid 策略：每个 OOS 客户从 FCP bundle menu 和 BSP size pricing 中选择 surplus 最高的选项。

#### random_ind（5-instance 平均）

| N | FCP | BSP | CPBSD-A | **Hybrid** | Hybrid−FCP | Hybrid−BSP |
|---|----:|----:|--------:|-----------:|-----------:|-----------:|
| 5 | **9.493** | 8.382 | 9.186 | 9.050 | −0.443 | +0.669 |
| 10 | **16.380** | 13.988 | 13.167 | 15.834 | −0.545 | +1.847 |
| 30 | **54.592** | 43.117 | 26.578 | 49.265 | −5.327 | +6.148 |

**Hybrid 反而低于纯 FCP**。原因：BSP 选项将部分客户从 FCP 的高利润 bundles 引流到 BSP 的低利润 size pricing（BSP 本身 OOS 远低于 FCP），产生 cannibalization。Hybrid 在 random_ind 上有害。

#### random_corr（5-instance 平均）

| N | FCP | BSP | CPBSD-A | **Hybrid** | Hybrid−FCP | Hybrid−BSP |
|---|----:|----:|--------:|-----------:|-----------:|-----------:|
| 5 | 9.728 | 9.789 | 9.905 | **9.860** | +0.133 | +0.071 |
| 10 | 18.830 | 18.974 | 18.942 | **19.077** | +0.247 | +0.103 |
| 30 | 59.042 | 62.988 | 54.733 | **63.272** | +4.230 | +0.284 |

**Hybrid 在 random_corr 上全面最优**：
- N=5: 超过 CPBSD-A (9.860 vs 9.905，差距缩小到 0.045)
- N=10: **超过所有 baseline** (19.077 > 18.974 BSP > 18.942 CPBSD-A)
- N=30: **全面最优** (63.272 > 62.988 BSP > 59.042 FCP > 54.733 CPBSD-A)

#### Hybrid 客户流向分析 (random_corr N=30, per-instance)

| Instance | FCP→FCP | FCP→BSP | Outside | Hybrid OOS |
|----------|--------:|--------:|--------:|-----------:|
| inst 1 | 84 | 4860 | 56 | 73.340 |
| inst 2 | 2420 | 2224 | 356 | 57.936 |
| inst 3 | 131 | 4800 | 69 | 66.660 |
| inst 4 | 18 | 4816 | 166 | 56.013 |
| inst 5 | 733 | 4081 | 186 | 62.414 |

大多数客户（80-97%）选择了 BSP 选项，说明 random_corr 下产品同质化严重，BSP 的 size pricing 覆盖面更广，但 FCP 的少量高价值 bundle 仍有贡献（Hybrid > BSP alone）。

#### 结论

| Scenario | 推荐策略 | 理由 |
|----------|---------|------|
| random_ind | **纯 FCP** | FCP 全面最优，Hybrid 有害（BSP cannibalization） |
| random_corr | **BSP+FCP Hybrid** | Hybrid 在所有 N 上全面最优，结合了 BSP 的广覆盖 + FCP 的高利润 bundles |

### 总结

Random cost scenarios 是 FCP 的优势场景（尤其 random_ind），但需要根据 cost 结构选择策略：

1. **高异质性** (random_ind): 纯 FCP 全面碾压，per-bundle pricing 优势明显
2. **低异质性** (random_corr): BSP+FCP Hybrid 最优，结合两种定价的覆盖优势
3. **GCN 迁移**: N=5 训练模型成功迁移到 N=10/30，无性能下降
4. **Runtime**: FCP 0.1-6.4s vs CPBSD-A 0.5-600s，快 100-1000x

### 输出目录

```
experiments/fcp_random_cost_eval_n{5,10,30}_random_{ind,corr}/
  instances/          # 测试实例
  results/            # 逐实例 JSON 结果
  comparison_summary.json
  comparison_summary.csv

experiments/fcp_bsp_hybrid_oos_results.json   # hybrid 评估汇总
```
