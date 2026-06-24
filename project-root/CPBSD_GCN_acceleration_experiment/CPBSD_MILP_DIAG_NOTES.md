# CPBSD MILP 求解器问题排查（持续更新）

更新：2026-03-05

> 本文档用于记录“MILP/A/BSP 对比异常”的排查过程与结论。
> 每次排查新增条目，保持可审计。

---

## 0. 最新单实例验证结果（最小复现）

**实例设置**：N=5, K=5, normal, rho=0, full, hvhm, time_limit=30s

- **MILP ObjVal** = 1.3523
- **BSP ObjVal** = 0.8622
- **结论**：MILP ObjVal ≥ BSP ObjVal（符合理论预期）

> 该结论说明：之前“ MILP < BSP ”主要由对比口径错误引起。

---

## 1. 需要进一步确认的问题（按你指出的逻辑）

### Q1. MILP ObjVal 是否应 ≥ CPBSD-A ObjVal
- **理论预期**：精确 MILP ≥ 近似 A
- **需要验证**：
  - 用相同实例 + 时间/Gap 设定，比较 `MILP ObjVal` vs `A ObjVal`
  - 若出现 `A > MILP`，需排查 MILP 收敛（Gap/TimeLimit）或模型约束问题

### Q2. BCS 最优性约束是否“紧”
- **目标**：验证 `p*,d*` 下的消费者最优选择与 MILP 解中的 `x,y` 是否一致
- **方法**（一次性诊断，不需要每个实例都做）：
  1) 固定一个实例，取 MILP 最优 `p*,d*`
  2) 用 BCS（消费者最大化 surplus）求解每个 k 的最优选择
  3) 与 MILP 的 `x,y` 比较一致性

> 若不一致，说明 BCS-dual 约束在实现中不紧/存在口径偏差。

### Q3. in-sample / out-of-sample 评估口径
- **in-sample**：
  - 样本数 = K（如 50/100）
  - 使用同一组样本求解得到的 `p*,d*` 计算收益
  - 相当于训练集平均收益

- **out-of-sample**：
  - 样本数 = 5000
  - 从分布 F 重新采样估值
  - 用同一 `p*,d*` 计算收益
  - 用于验证泛化能力（测试集）

> 这两者都应该保留，用于衡量 SAA 解的泛化效果。

---

## 2. 当前阶段的改动说明

- **对比口径修正**：
  - 所有 ratio / baseline 对比统一使用 **ObjVal (in-sample)**
  - `revenue_in_eval` 仅作为诊断字段（检查 BCS tightness）

- **消费者选择逻辑修正**：
  - 后验评估使用“最大化 surplus”而非最大化 profit

---

## 3. 下一步排查计划

1) **验证 MILP ObjVal ≥ A ObjVal**（固定实例 + 同时限）
2) **执行 BCS 紧性诊断**（比较 MILP 解 vs BCS 选择）
3) 若存在系统性偏差：定位约束或数值设置问题

---

## 4. 记录模板（后续追加）

```
[日期] 实例设置：N=?, K=?, dist=?, rho=?, hetero=?, cost=?
- MILP ObjVal = ?
- A ObjVal = ?
- BSP ObjVal = ?
- 结论：
```


---

## [2026-03-05] Q2 一次性紧性检查（BCS vs MILP 解）

**实例设置**：N=5, K=10, normal, rho=0, full, hvhm, time_limit=120s

- MILP ObjVal = 2.0501（gap=0）
- BCS(基于 p*,d*) 与 MILP `x,y` **不完全一致**：
  - mismatch = 4 / 10
  - 示例：
    - k=0：MILP 选 s=4 (0,2,3,4)；BCS 选 s=3 (0,3,4)
    - k=6：MILP 选 s=3 (0,3,4)；BCS 选择不购买

**结论**：当前实现的 BCS-dual 约束在该实例下不紧（至少在某些客户上选择不一致）。
这说明“ObjVal 与后验评估不一致”是**真实约束紧性问题**，不是评估口径错误。

下一步：定位导致不一致的约束/变量设置（尤其 (9)-(11) dual 约束、(18)-(20) surplus 约束的实现细节）。


---

## [2026-03-05] Q2 补充：surplus 一致性检查

**实例设置**：同上 (N=5, K=10, normal, rho=0, full, hvhm)

- 以“surplus 是否一致”作为判定标准重新比较：
  - mismatch = 0 / 10 （全部在 1e-6 内一致）

**解释**：
- 之前的 mismatch 来自“选择了不同 bundle”，但 **surplus 相同**（等价最优解）。
- 因此 **BCS-dual 约束可能是紧的**，只是存在等价最优解导致的选择差异。

**结论**：
- 当前实现未发现 “surplus 非最优” 的证据；
- 后续若要严格一致，需要在 BCS 后验中处理 ties（或比较 surplus 而非具体 bundle）。


---

## [2026-03-05] Q3 评估口径（in-sample vs out-of-sample）

**目的**：评估 SAA 解的泛化能力（训练集/测试集视角）

- **in-sample**：
  - 样本数：K = 50 或 100
  - 使用与 MILP 求解相同的样本集
  - 计算得到的 (p*, d*) 在训练样本上的平均收益

- **out-of-sample**：
  - 样本数：5000
  - 重新从分布 F 采样估值
  - 用同一 (p*, d*) 计算收益
  - 目的：检验泛化能力

> 结论：两者都应保留，分别对应训练/测试评估。
