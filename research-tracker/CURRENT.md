# Current Research Dashboard

## 当前周

- 周次：`2026-W14`
- 汇报窗口：`2026-03-30` 到 `2026-04-05`
- 下次会议时间：`待定`
- 最近已整理会议：`research-tracker/meetings/2026-03-29_weekly-sync.md`
- 实验地图：`research-tracker/EXPERIMENT_MAP.md`
- 本周周报：`research-tracker/weekly-reports/2026-W14.md`

## 本周主线

- 方向 1：`mb-oos-generalization`
- 方向 2：`mb-bundle-coverage-and-candidate-space`
- 方向 3：`mb-optimize-acceleration`

## 活跃方向状态

| Direction | Owner | Status | Latest update | Next step |
| --- | --- | --- | --- | --- |
| `mb-oos-generalization` | `shared` | `running` | `已确认 hard setting 下约 27.8% drop 为真实现象，full-grid 聚合约 16.1%` | `锁定 common benchmark 和 training-size 方案` |
| `mb-bundle-coverage-and-candidate-space` | `shared` | `running` | `CPBSD Top-20 覆盖约 90.3%，native MB Top-20 仅约 21% 到 25%` | `把 coverage 结论转成 PCP/FCP 设计` |
| `mb-optimize-acceleration` | `shared` | `running` | `optimize 仍是主瓶颈，threads 有正信号，但 large-instance 证据未补齐` | `补齐 raw outputs 并做并行对照` |
| `subadditivity-family-design` | `shared` | `queued` | `literal Appendix C 不是主矛盾，subadd_only 是唯一正向 OOS 开关` | `把 subadditivity 线和 theory/remark 合并推进` |
| `ic-constraint-adjustment` | `shared` | `queued` | `来源于 2026-03-29 会议，尚未形成正式实验记录` | `整理成首个可执行实验设计` |
| `training-size-scaling` | `shared` | `queued` | `会议与 generalization 诊断都指向 sample complexity` | `确定本周优先跑哪些 K 值` |

## 本周必须产出

- `把已有实验主线压缩成一版可汇报口径`
- `确定 common benchmark setting`
- `明确下一轮优先推进的 2 到 3 个实验动作`

## 当前阻塞

- `large-instance acceleration 的 raw outputs 不完整`
- `common benchmark setting 还没有最终锁定`
- `K=50 下 validation 选择机制不稳定，难以稳定选出更保守的价格方案`

## 最近新增待探索方向

- `cpu-parallel-comparison`
- `hanson-style-reduction`
- `pcp-on-top-of-fcp`
- `n30-extension`
- `subadditivity-family-design`
- `subadditive-counterexample`

## 汇报前最后检查

- 本周所有重要实验是否都在 `experiment-logs/` 有记录
- 每个方向文件是否更新了最新结论
- 周报是否能从记录中直接生成，而不是重新回忆
