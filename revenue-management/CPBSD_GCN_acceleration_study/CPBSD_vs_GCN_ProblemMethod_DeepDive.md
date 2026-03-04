# CPBSD 机制深度整理（对照 Hanson 1990）

> 项目目录：`revenue-management/CPBSD_GCN_acceleration_study`
>
> 目标：围绕 CPBSD 的机制、建模与 tractability 逻辑，回答“为何相对 Hanson 的 Mixed Bundling 更可解”。

---

## 1. CPBSD 的机制介绍

CPBSD（Component Pricing with a Bundle Size Discount）的定价机制是：
- 给每个产品一个 component price：\(p_n\)
- 给每个 bundle size 一个每件折扣：\(d_s\)
- 若客户买 bundle \(S\subseteq\mathcal N\), \(|S|=s\)，支付
\[
\text{Pay}(S)=\sum_{n\in S}p_n-sd_s.
\]

Firm 对该 bundle 的利润为
\[
\Pi(S)=\sum_{n\in S}(p_n-c_n)-sd_s.
\]

---

### 1.1 与 Hanson Formulation 的差别

#### (a) 价格机制空间不同（最本质）
- **Hanson (1990) Mixed Bundling**：每个 bundle 一个独立价格 \(p_S\)（几乎“全自由”价格表）。
- **CPBSD**：价格被结构化为 \((p_n,d_s)\)，bundle 价格由规则生成，而不是对每个 \(S\) 自由定价。

=> 这是 CPBSD tractability 的核心来源：把高维自由价格表压缩为结构化参数。

#### (b) 需求建模粒度不同
- **Hanson**：分群确定性 reservation prices \(R_{ki}\)（客户群 k 对 bundle i 的估值已知）。
- **CPBSD**：随机估值向量 \(V\sim F\)，先写期望利润问题，再用样本近似（SAA）变成可解 MILP。

#### (c) 顾客选择问题写法不同
- **Hanson**：以 self-selection 约束直接写在主模型中。
- **CPBSD**：先显式写顾客 bundle content selection（BCS），再 LP relax，再 dual，再嵌入主 MILP。

#### (d) 成本与可行性约束表达不同
- **Hanson**：强调 bundle-level 成本/free disposal 等经济结构假设。
- **CPBSD**：强调 practical pricing constraints（如折扣单调/防拆单套利）
\[
sd_s\ge s_1d_{s_1}+s_2d_{s_2},\quad s_1+s_2=s.
\]

#### (e) 可解性路径不同
- **Hanson**：机制表达力强，但组合维度爆炸更明显。
- **CPBSD**：机制上主动加结构 + 求解上 dual reformulation + SAA，换取可计算性。

---

### 1.2 CPBSD 如何刻画顾客 Self-selection：BCS → BCS-LP → BCS-Dual

> 这一段回答：给定什么变量？求解什么变量？

在给定 \((p,d)\) 和给定 bundle size \(s\) 时，客户 k 需要选 bundle 内容（选哪些产品）。

设：
- \(x_{kns}\in\{0,1\}\)：客户 k 在 size=s 时是否选产品 n
- 样本估值为 \(v_n^k\)

则顾客子问题 BCS：
\[
\max_{x_{kns}}\sum_{n\in\mathcal N}(v_n^k-p_n+d_s)x_{kns}
\]
\[
\text{s.t. }\sum_{n\in\mathcal N}x_{kns}=s,\quad x_{kns}\in\{0,1\}.
\]

这里：
- **给定**：\(p,d,s,v^k\)
- **求解**：\(x_{kns}\)

#### BCS-LP
把二元约束放松为 \(0\le x_{kns}\le1\)。在该结构下，LP relax 与原 BCS 最优值一致（文中 Proposition 3 的一部分）。

#### BCS-Dual
对 BCS-LP 写对偶（引入 \(\alpha_{ks},\beta_{kns}\)）：
\[
\min\ s\alpha_{ks}+\sum_n\beta_{kns}
\]
\[
\text{s.t. }\alpha_{ks}+\beta_{kns}\ge v_n^k-p_n+d_s,\ \alpha_{ks}\text{ free},\ \beta_{kns}\ge0.
\]

利用 LP 强对偶，得到 BCS、BCS-LP、BCS-Dual 最优值一致（Proposition 3）。

---

### 1.3 CPBSD 如何把 BCS-Dual 带入 CPBSD-MILP（双层→单层）

> 这一段回答：Firm 决策变量是什么？约束变量是什么？Customer selection 如何保证？

原始逻辑是双层：
- 上层 Firm 选 \((p,d)\)
- 下层客户做最优自选择

CPBSD 的做法是将下层最优性“编译”为线性约束，嵌入一个单层 MILP。

#### Firm 决策变量（机制层）
- \(p_n\)：component prices
- \(d_s\)：size-based discounts

#### 关键辅助变量（用于嵌入客户最优性与线性化）
- \(x_{kns}\in\{0,1\}\)：客户-产品-尺寸选择
- \(y_{ks}\in\{0,1\}\)：客户是否选择 size=s
- \(q_{kns}\)：支付线性化变量（对应 \((p_n-d_s)x_{kns}\)）
- \(w_{ks},w_k\)：客户 surplus
- \(\alpha_{ks},\beta_{kns}\)：BCS-Dual 变量

#### Customer selection 如何保证
- 用 BCS-Dual 约束组（文中(9)-(11)）确保顾客 surplus 不违背最优性上界；
- 用选择一致性约束（文中(12)-(15)）确保“选 size”与“选产品”一致；
- 用 big-M 线性化（文中(16)(17)）把支付与二元选择连接；
- 用 surplus 定义与比较约束（文中(18)-(20)）保证顾客不会偏离最优自选择。

因此，不需要外部再单独解客户问题，主 MILP 内部已强制顾客理性选择。

---

### 1.4 CPBSD 最终 Objective：SAA 与求解器计算方式

原始目标是期望利润最大化（对 \(V\sim F\) 取期望），但直接求解困难。

#### SAA（Sample Average Approximation）
取 K 个样本客户估值 \(v^k\)，把期望替换为样本均值：
\[
\max\ \frac{1}{K}\sum_{k=1}^K \text{Profit}_k(p,d,\text{selection vars}).
\]

可理解为：
- 训练/求解时优化 in-sample average revenue（经验期望）
- K 越大，样本平均越接近期望（近似更稳，但 MILP 更大）

#### Gurobi 实际在算什么？
- Gurobi**不直接计算“理论期望积分”**；
- 理论期望已经被 SAA 离散成确定性 MILP 目标；
- Gurobi只是在解这个确定性 MILP（branch-and-bound/branch-and-cut）。

所以“Expected Revenue”的处理发生在建模层（SAA），求解器层处理的是确定性离散优化。

---

## 2. 机制优化：CPBSD 相对 Hanson 如何实现 Tractability

### 2.1 机制设计上优化了什么？

对比 Hanson 的 MB，CPBSD 的 tractability 来自“机制结构化 + 求解重构”两步：

1. **机制结构化降维（第一性原因）**
   - 从“每个 bundle 都可单独定价”
   - 变成“每个产品一个价格 + 每个尺寸一个折扣”
   - 大幅压缩价格决策空间维度

2. **双层问题单层化（第二性原因）**
   - 通过 BCS-LP-Dual 把客户理性选择转成线性约束
   - 避免显式双层求解

3. **随机目标离散化（第三性原因）**
   - 期望目标→SAA 样本平均目标
   - 使问题可交给标准 MILP 求解器

### 2.2 结论（给汇报可直接用）

CPBSD 并不是在“表达力”上全面超过 Hanson 的 MB；相反，它主动牺牲一部分价格自由度，换取：
- 更强可计算性（tractability）
- 更好规模适应性（scalability）
- 与商业实践更一致的价格结构（component + size discount）

这就是它相对 Hanson formulation 的机制创新价值。

---

## 3. Numerical Experiments 精读补充（CPBSD 原文 Section 6）

### 3.1 测试了哪些 Size、Sample、Distribution（\(N,K,F\)）

#### 产品规模 \(N\)
- 主实验：\(N\in\{5,10,30\}\)
- 渐近实验（Section 6.2）：\(N\in\{100,300,1000\}\)

#### 样本规模 \(K\)（in-sample）
- 当 \(N=5\)：\(K=50\)
- 当 \(N\ge 10\)：\(K=100\)
- 渐近实验：用于求策略的 in-sample 点数为 1000

#### 估值分布 \(F\) 设计
- 5 类边际分布：exponential / logit(Gumbel) / lognormal / normal / uniform
- 3 类相关结构：negative / independent / positive，相关参数 \(\rho\in\{-0.5,0,0.5\}\)，并用 Gaussian copula 构建联合分布
- 3 级估值异质性：none / partial / full
- 3 类成本场景：zero cost / HVHM / HVLM

#### 实例数量与评估
- 组合数：\(3\times3\times5\times3\times3=405\) setups
- 每个 setup 生成 5 个实例，总计 2,025 个实例（每个 \(N\) 下 675 个）
- out-of-sample：对每个实例再抽取 5,000 个估值样本评估泛化利润

---

### 3.2 对比了哪些 Baseline

#### \(N=5\)（完整对比）
- CP / PB / BSP / PBDC / MB
- 作者方法：CPBSD（MILP）与 CPBSD-A（近似算法）
- 额外参照：\(\max\{CP,BSP\}\)（文中记作 BCB）

#### \(N\ge 10\)
- 由于计算成本，文中主要对比 CP / PB / BSP / PBDC / CPBSD-A
- MB 与 CPBSD 精确 MILP 不做同等规模全面对比

#### 渐近实验（\(N=100,300,1000\)）
- 对比 PB / BSP / CPBSD
- 以 PPD 利润作为归一化参照

---

### 3.3 表现如何（核心结论与关键数字）

#### 主结论（\(N=5\)）
- 相对 BSP：
  - CPBSD in-sample 平均提升 29.4%
  - CPBSD out-of-sample 平均提升 23.7%
- 相对 PBDC：CPBSD in-sample 平均提升 12.9%
- 相对 \(\max\{CP,BSP\}\)：CPBSD in-sample 平均提升 9.9%
- CPBSD-A 与 CPBSD 的性能整体接近

#### 按成本/异质性拆分（\(N=5\)）
- zero cost：PB/BSP/PBDC/CPBSD 表现接近，且整体接近 MB
- positive cost：CPBSD 明显优于 BSP/PBDC，且异质性越强优势越大
- 文中给出的相对 BSP 平均提升：
  - HVHM：in-sample +9.7%，out-of-sample +1.6%
  - HVLM：in-sample +65.5%，out-of-sample +58.2%

#### \(N=30\)（CPBSD-A）
- 结论模式与 \(N=5\) 基本一致
- 相对 BSP 的提升：
  - HVHM：in-sample +5.5%，out-of-sample +7.8%
  - HVLM：in-sample +57.4%，out-of-sample +61.3%

#### 渐近实验（\(N=100,300,1000\)）
- 在零/负相关下，CPBSD 随 \(N\) 增大更接近 PPD
- 在正相关下不一定收敛到 PPD，但仍普遍优于替代机制
- HVLM 场景中，CPBSD 相对 BSP 优势最显著

---

### 3.4 求解器与计算设置（原文可复现实验细节）

- MILP 求解器：Gurobi 9.5.0
- 硬件：Intel i5-1135G7（2.42GHz）+ 16GB RAM
- 每次优化时间上限：
  - \(N=5\)：300s
  - \(N=10\)：600s
  - \(N=30\)：1200s

补充说明：原文重点在模型与结果，不以求解器参数调优（如 cut/heuristic/presolve 细节）为主要贡献点。

### 3.5 CPBSD-MILP vs CPBSD-A：为什么需要近似算法

#### CPBSD-A 的实现要点（简述）
- CPBSD-MILP 是完整精确建模，变量/约束规模随 \(K,N\) 快速增长，尤其在 \(N\) 较大时计算代价显著。
- CPBSD-A 采用结构化近似思路，避免完整 MILP 的重负担：
  1. 预设（或近似固定）一部分顾客偏好/选择结构；
  2. 文中实现里采用按 \(v_n^k-c_n\) 降序的 preference ranking；
  3. 在此基础上快速构造近似定价策略（\(p,d\)）并评估利润。
- 直观上：CPBSD-A 用“可解释规则 + 近似优化”替代“全量精确 MILP”。

#### 是否意味着 CPBSD-MILP 在 \(N\ge 30\) 仍有 tractability 压力？
是。论文实验设计本身就体现了这一点：
- 在 \(N=5\) 时，作者会系统比较 CPBSD-MILP 与其他机制；
- 在 \(N\ge 10\)（尤其 \(N=30\)）时，更多采用 CPBSD-A 进行大规模对比；
- 原文明确指出，当求解 (CPBSD-MILP) 计算负担较重时，(CPBSD-A) 可作为 good surrogate。

#### 结论（可直接引用）
- CPBSD-MILP：精确、解释完整、但算力开销高。
- CPBSD-A：牺牲部分全局最优性，换取显著可扩展性；在文中数值实验里通常与 CPBSD 表现接近。

---

## 附：一句话口径（答辩版）

“CPBSD 的关键不是把 MB 做得更复杂，而是把 MB 的自由价格机制结构化为 \((p,d)\)，再用 dual 把顾客自选择折叠到单层 MILP，并通过 SAA 把随机期望目标变成可计算的样本平均目标。”
