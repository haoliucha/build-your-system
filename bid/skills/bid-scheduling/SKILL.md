---
name: bid-scheduling
description: This skill should be used when building or repairing the schedule of a To-B bid or delivery project — PERT three-point estimation, dependency-topology-aware resource leveling under per-person weekly capacity caps, machine-checking dependency inversions, honest utilization denominators (gating-bound vs work-bound), itemized AI-productivity accounting, and elastic-scope handling of structural overflow. Triggers on phrases like "投标排期", "交付排期", "资源平衡", "排期溢出", "利用率偏低", "压缩团队", "工期不可行", "依赖倒挂", "PERT 估算", "甘特图工作包".
version: 0.1.0
---

# bid-scheduling — 投标排期与资源平衡

To-B 投标/交付物项目的排期方法论。排期表是评审逐格挑刺的对象:一处依赖倒挂、一格超载、一行合计对不上,整份材料的可信度就崩。全流程以「机器排出、机器校验、诚实呈报」为底线。

## 硬规则

1. **排期禁手摆**。工作包起止周由带依赖拓扑约束的资源平衡器算出(`scripts/level.cjs`)。手摆/naive 均摊会把跨度重叠的包当同时并行——某投标项目首版手摆排期出现单人单周 11+ 人天(上限 5),整体不可行。
2. **产出后必做机器校验**:每包开始周 ≥ 全部前置完成周。贪心/优先级调度都可能破坏拓扑序;曾有一版自动输出的依赖倒挂被 3 个独立评审同时标出。根治靠算法(拓扑深度排序+强制约束,脚本已内置),辅以多个独立 review agent 专抓倒挂。
3. **不可行时呈分叉,不静默变通**。用户给定的工期约束经平衡器证明不可行(关键包溢出且解不掉)时,停下,给「压缩硬塞 vs 放宽窗口」两选项及各自代价让用户裁决;可在计划里预承诺「不可行即上浮」。禁止静默延长工期、静默改依赖、静默降范围。
4. **数据不撒谎**。目标指标(如利用率须达某值)倒推时,只走诚实口径重定义——分母从理论产能改为有效可投产能(扣非交付工时),原有余量显式拆解保留,不虚改底层工时数据。

## 工作流

1. **建任务表 JSON**(格式见 `references/input-format.md`)。每包三点估算 PERT=(o+4m+p)/6;AI 提效写明账「原始估算 × 系数 → 净值」,系数只给代码生成类包,ML 训练/合规类不吃红利、悲观值反而拉宽(见 `references/estimation-utilization.md`)。
2. **跑平衡器**:`node scripts/level.cjs tasks.json`(`--json` 给机器读,`--strict` 下超载/溢出即非零退出)。倒挂恒为退出码 2。
3. **修复循环**:限最小可辩护微调——密排系数微调、依赖细化、关键路径标记;每步重跑平衡器;发现把超载转嫁给别的角色(换 owner 后闲角色尾段反超载)立即回滚。
4. **溢出分诊**:腾挪 owner 只是跷跷板(修好一个坏另一个)= 结构性溢出 → 按弹性范围条款把非基线可选项整体后置运营期并向用户披露;绝不硬塞,不留表内合计对不上的可见缺口。详见 `references/repair-playbook.md`。
5. **口径呈报**:利用率先辨 work-bound(工程量驱动)还是 gating-bound(合规/审批日历门控撑大分母);跨项目比较先对齐分母。日历刚性项(监管审批、数据沉淀、机构档期)不塞建设窗口,诚实切分为并行持续项并给统一理由。计费口径与日历口径有意分层时须在交付物中显式声明(与 bid-costing 的接口)。

## 反模式速查

| 反模式 | 正确做法 |
|---|---|
| 工期解不掉就静默延长/砍范围 | 呈「硬塞 vs 放宽」分叉带代价,让用户选 |
| 溢出包换 owner 给闲角色 | 尾段反超载即回滚,改依赖细化+密排微调 |
| 软化依赖抢并行后不复核 | 发现倒挂据实恢复依赖、后移里程碑使排期自洽 |
| AI 提效一刀切下调全部包 | 三段明账+只折代码生成类,高危包上调 |
| 压缩团队只砍人头报数 | 完整评估法:砍最低利用率非关键角色+shift-left+验证峰值+预答法定岗位反驳(见 `references/team-compression.md`) |
| 跨项目直比利用率 | 先拆分子分母结构性成因,对齐口径再比 |

## 脚本

```bash
node scripts/level.cjs tasks.json            # 人读诊断:负载矩阵/起止周/三项校验
node scripts/level.cjs tasks.json --json     # 机器读输出
node scripts/level.cjs tasks.json --strict   # CI 门禁:超载/溢出即失败
node scripts/level.cjs --selftest            # 自测(内置最小示例)
```

## 延伸资料

- `references/input-format.md` — 平衡器输入/输出格式、字段语义、退出码
- `references/estimation-utilization.md` — PERT 细则、AI 提效明账、日历刚性项、利用率口径与有效产能分母
- `references/repair-playbook.md` — 修复微调清单、结构性溢出判定与弹性条款、分叉呈报模板
- `references/team-compression.md` — 压缩团队完整评估法、卖点 UI 缺口拆分
