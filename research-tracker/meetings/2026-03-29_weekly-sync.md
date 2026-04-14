# Weekly Meeting Note

## 基本信息

- 日期：`2026-03-29`
- 会议名称：`weekly sync`
- 参会人：`你 / 两位同学`
- 对应周次：`2026-W13`
- 来源笔记：`/Users/sensen/Desktop/Meeting Note/060329Note.md`

## 本次会议的关键结论

- PCP 修改后的结果需要尽快补齐并纠正。
- Theory 线要尽快推进，不能只停留在工程实验。
- Sample-based SAA 需要切换或扩展 setting，不能只盯一个困难设置。
- 加速方法仍然是核心目标，理想目标是相对 CPBSD-A 和 CPBSD 同时做到更快、且 revenue 更优。

## 已有实验共识

- `N=20` 的初步结果里，`FCP-pruned-MB` 平均 runtime 约 `113.44s`，明显快于 `CPBSD-A` 的 `601.14s`，且 `Rev-In/BSP` 约 `1.2873`。
- GCN inference time 在已有记录里较低：
  - `N=10` 平均约 `0.2276s`
  - `N=20` 平均约 `0.2756s`
- MB 时间过长的主因仍是求解器 `optimize` 阶段。
- 使用 `threads_10` 在若干 MB case 上观察到了约 `1.65x - 1.77x` 的加速。

## 新增待探索方向

### 方向 1

- 名称：`ic-constraint-adjustment`
- 核心问题：`IC constraint 修改后能否减少求解负担，同时不破坏模型语义`
- 为什么值得做：`这是当前 formulation 与求解难度的直接瓶颈之一`
- 负责人：`DLY`
- 优先级：`high`

### 方向 2

- 名称：`n30-extension`
- 核心问题：`现有方法在 N=30 上是否还能保持可解性与速度优势`
- 为什么值得做：`需要把当前结论从小规模推向更有说服力的规模`
- 负责人：`WCH`
- 优先级：`high`

### 方向 3

- 名称：`cpu-parallel-comparison`
- 核心问题：`BSP / CPBSD / MB 在 CPU 并行设置下的收益分别如何`
- 为什么值得做：`已有 MB 线程对比信号不错，但还不系统`
- 负责人：`WCH`
- 优先级：`medium`

### 方向 4

- 名称：`common-benchmark-setting`
- 核心问题：`是否应固定 normal, rho=0.0, full, zero 作为公共对照 setting`
- 为什么值得做：`后续所有加速和泛化实验需要统一 benchmark 口径`
- 负责人：`WCH`
- 优先级：`high`

### 方向 5

- 名称：`hanson-style-reduction`
- 核心问题：`是否能通过 Hanson 风格的 bundle binary/constraint 缩减来加速`
- 为什么值得做：`直接对应当前 optimize bottleneck`
- 负责人：`DLY`
- 优先级：`medium`

### 方向 6

- 名称：`subadditive-counterexample`
- 核心问题：`文章 remark 里的 subadditive 反例如何构造并用于说明机制边界`
- 为什么值得做：`这关系到理论完整性与写作说服力`
- 负责人：`DLY`
- 优先级：`medium`

### 方向 7

- 名称：`pcp-on-top-of-fcp`
- 核心问题：`PCP 是否应建立在 FCP 的 nested candidate 基础上`
- 为什么值得做：`这是 GCN / candidate generation 线的关键结构选择`
- 负责人：`DLY`
- 优先级：`high`

### 方向 8

- 名称：`training-size-scaling`
- 核心问题：`training size 变化对 generalization 和 candidate quality 的影响有多大`
- 为什么值得做：`已有 MB generalization 证据强烈指向 sample complexity`
- 负责人：`WCH`
- 优先级：`high`

## 延续推进的方向

- `mb-oos-generalization`：已有较清晰诊断，需要把 common setting 与 training size 设计锁定下来。
- `mb-bundle-coverage-and-candidate-space`：已有 coverage 证据，需要转为 candidate strategy 设计。
- `mb-optimize-acceleration`：已有 partial evidence，但 large-instance 证据未补全。

## 本次会议分工

- `shared`：继续推进 generalization、加速和 candidate 三条主线的实验与汇报准备

## 下次会议前必须完成的输出

- `补齐 PCP 修改后的核心结果`
- `明确一个公共 benchmark setting`
- `补一轮训练规模或更大 N 的对照结果`

## 需要同步更新的文件

- `research-tracker/CURRENT.md`
- `research-tracker/EXPERIMENT_MAP.md`
- `research-tracker/directions/...`

## 会后行动

- [x] 把会议笔记转成结构化 meeting note
- [x] 将已有实验主线映射到 tracker directions
- [ ] 在新增方向里挑出本周真正要推进的 2 到 3 条
