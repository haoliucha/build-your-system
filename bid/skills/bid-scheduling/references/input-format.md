# level.cjs 输入/输出格式

## 输入 JSON

```json
{
  "weeks": 10,
  "weeklyCapacity": 5,
  "packTarget": 4.5,
  "perTaskCap": 2.8,
  "tailMergeMax": 0.6,
  "effectiveCapacityFactor": 0.85,
  "roles": [{ "id": "R1", "name": "架构" }, "R2"],
  "milestones": [{ "id": "M1", "week": 4 }],
  "tasks": [
    { "id": "A", "name": "底座", "role": "R1", "pert": { "o": 6, "m": 8, "p": 12 }, "deps": [], "critical": true },
    { "id": "B", "name": "引擎", "role": "R1", "pert": { "o": 6, "m": 9, "p": 14 }, "deps": ["A"], "critical": true },
    { "id": "D", "name": "集成联调", "role": "R2", "pert": { "o": 4, "m": 5, "p": 8 }, "deps": ["B", "M1"] },
    { "id": "E", "name": "次要功能", "role": "R2", "effort": 6, "deps": ["A"], "priority": 2 },
    { "id": "G", "name": "评审贯穿", "role": "R1", "effort": 5, "background": { "start": 1, "end": 10 } }
  ]
}
```

## 顶层字段

| 字段 | 必填 | 默认 | 语义 |
|---|---|---|---|
| `weeks` | 是 | — | 排期窗口长度(周) |
| `weeklyCapacity` | 否 | 5 | 单人单周硬上限(人天),超载校验用 |
| `packTarget` | 否 | weeklyCapacity×0.9 | 打包目标强度:贪心填充时每人每周装载上限,留缓冲不拉满 |
| `perTaskCap` | 否 | packTarget×0.6 | 非关键包单周强度上限(约束单人双线程),让非关键包填空隙而不挤占关键路径 |
| `tailMergeMax` | 否 | 0.6 | 收尾零头(小于此值)并入最后一周的上限,避免假性溢出;并入不破 weeklyCapacity |
| `effectiveCapacityFactor` | 否 | 1 | 有效可投产能系数(扣非交付工时),仅影响利用率分母,不影响排程 |
| `roles` | 是 | — | 角色列表,元素为 `"R1"` 或 `{id,name}` |
| `milestones` | 否 | [] | `{id, week}`;deps 可引用里程碑 id,表示「不早于该周开工」 |
| `tasks` | 是 | — | 工作包列表 |

## 任务字段

| 字段 | 必填 | 语义 |
|---|---|---|
| `id` | 是 | 唯一标识,deps 引用它 |
| `name` | 否 | 展示名 |
| `role` | 是 | 主责角色 id(单一 owner;需要多角色就拆包) |
| `pert:{o,m,p}` 或 `effort` | 二选一 | 三点估算(乐观/最可能/悲观,人天)或直接给净人天。PERT=(o+4m+p)/6 |
| `deps` | 否 | 前置任务 id / 里程碑 id 数组。语义:本包开始周 ≥ 全部前置完成周(允许同周衔接) |
| `critical` | 否 | 关键路径包:允许以 packTarget 满速推进;非关键包被限 perTaskCap |
| `priority` | 否 | 整数,0 最高,默认 1;同拓扑深度内的排序依据 |
| `background:{start,end}` | 否 | 贯穿型负载(如评审、长期合规建设):固定跨度薄摊,不参与贪心填充 |
| `earliestStart` | 否 | 硬约束最早开工周。用于外部前置——如外包美术资产到位周 |
| `preferredStart` | 否 | 软意图起周:**仅参与排序,不人为延后开工**(人为延后会制造假空窗) |

## 算法要点(读懂输出所需)

- 排序:拓扑深度升序(保证前置先排,从根上杜绝依赖倒挂)→ critical 优先 → priority → preferredStart → id。
- 贪心填充跑 3 遍收敛(依赖完成周依赖排程结果)。
- 依赖成环直接报错退出(码 3),不静默取 0。

## 输出

- 默认:人读诊断——PERT 合计/储备率、每角色利用率(分母=有效可投产能)、负载矩阵(超载格标 `*`)、各包起止周、三项校验结果。
- `--json`:`{params, total, byRole, utilization, effCapPerPerson, items:[{id,role,pert,w0,w1,span,critical,overflow}], load, issues:{inversions,overload,overflow}}`。

## 退出码

| 码 | 含义 |
|---|---|
| 0 | 校验通过(或仅有警告且未加 `--strict`) |
| 1 | `--strict` 下存在超载/溢出 |
| 2 | 存在依赖倒挂(恒为硬错误,无论是否 strict) |
| 3 | 输入不合法(缺字段/角色不存在/依赖成环/引用悬空) |

修复循环里把 `--strict` 当门禁:每次微调后重跑,退出码非 0 就不算修完。
