---
name: bid-playbook
description: This skill should be used when running a To-B bid/deliverable project as an AI coding agent — the entry playbook of the bid plugin. Covers repository layout (meeting/ notes by date, customer-facing docs/ physically separated from docs/内部/, build/ generators as the single source of numbers, dependency-ordered deliverable numbering with letter-suffix insertion), execution rhythm (spec→plan→execute; ask only at real forks with a recommended option; lock the full value table before wide cascades), compliance-first sequencing (data authorization as step zero, worst-case-default safe paths), and a routing table to the plugin's other 9 skills and 6 /bid:* commands. Triggers on phrases like "投标项目怎么推进", "新建投标项目", "交付物编号怎么排", "投标项目目录规范", "这个点要不要问用户", "口径锁定了怎么改", "多项目怎么分目录", "bid playbook", "投标方法论".
version: 0.1.0
---

# bid-playbook — To-B 投标/交付物项目方法论总纲

bid 插件入口,管三件事:目录与编号规范、执行节奏(何时问/何时自决)、合规与口径红线。执行者假设是 AI coding agent:交付物由 build/ 生成器产出,数字与措辞受锁定口径约束。先读本文,再按路由表进专项。

## 项目目录规范

```
<project>/
├─ meeting/        # 纪要按日期命名(YYYY-MM-DD-主题.md),全项目共享编年
├─ docs/           # 客户向交付物,序号化(01-, 02-, …)
│  └─ 内部/         # 内部文件(成本底稿/作战手册),绝不外发
├─ build/          # 生成器脚本:xlsx/PDF/图的唯一真源
└─ .claude/memory/ # 口径决策即时落盘
```

- 把客户向与内部**物理分离**——这是故意设计:防误发、防投屏;两层对同一事实可有意持不同口径(内部保留的前提=报价成本依据),差异须显式记录。
- 按**依赖/阅读顺序**编交付物序号,不按产出先后。后补文档用字母后缀插位:需求细化是 02 需求分析的展开就编 02B 紧跟 02,不追加到成本文档之后;既有编号绝不 renumber。
- 多主体项目按项目对称拆分交付物目录并声明独立性;meeting/ 保持共享编年+每篇打「涉及项目」标签(同一批人常跨项目开会)。新线索先落临时目录,成单再转正。

## 全流程路由表

command 是流程动作,skill 是方法论。

| 阶段 | 用什么 | 何时用 |
|---|---|---|
| 总纲 | `bid-playbook` | 本文:节奏/目录/岔路口治理 |
| 立项 | `/bid:init` | 目录脚手架+P0 问题清单+memory 初始化 |
| 调研 | `bid-research` | 竞品/对标实证、选型证据链、license 穿透 |
| 谈判设计 | `presales-tactics` | 体量摸底、分档锚定、砍价预案、谈判红线 |
| 成本 | `bid-costing` | 数字算得可辩护:价格阶梯/依据分级/区间口径 |
| 排期 | `bid-scheduling` | 资源平衡器排包、利用率口径、工期压缩 |
| 写作 | `deai-writing` | 对外文稿去 AI 味,零信息损失只改外壳 |
| 出图/出版 | `diagram-pdf-pipeline` | 架构图生成、中文 PDF 导出(CJK 字体/嵌图) |
| 原型移交 | `prototype-handoff` + `/bid:handoff` | 先吃透接收工具输入模型,再定交接包形态 |
| 改口径 | `single-source-sync` + `/bid:sync` | 改任何已锁定数字/措辞:改源→重生成→级联→grep 残留。macOS+WPS 环境下重生成 xlsx 前先 lsof 查写句柄 |
| 审校 | `adversarial-review` + `/bid:review` | 口径改写后多透镜审校、财务表算术配平、交付前收口 |
| 会议 | `/bid:meeting` | 会前出准备包五件套;会后归档纪要+口径变更落 memory |
| 速查 | `/bid:status` | 锁定口径表+红线清单+遗留待办 |

## 节奏纪律

- **真分叉才问,且带推荐项**:只把实质改变交付物形态/数字的岔路口一次性收敛成选择题请示;机械可推导的自决推进,阶段完成短报告后直接继续。
- 走 **spec→用户确认→带验收标准的逐任务 plan→按依赖执行**;文档项目把 TDD 适配为「产出→校验→提交」。
- **宽级联前先锁完整取值表**:用户只改部分条目却触发全链路级联时,逐项列全表(含推理值与未动项)请确认,未提及条目不猜。
- 指令顺序会固化矛盾时**提替代顺序**:如「先 commit 手改再更新下游」会把不一致锁进版本库,改为「意图落源→重生成→级联→一次一致 commit」,说明理由并保留按原样拆分选项。
- 未知客户事实**不当阻塞项**:压成摸底问题清单带去现场,准备不停。
- 客户交付物改动默认不 commit,等用户确认;只 stage 本任务文件,无关预存改动点名不碰。

## 合规与口径红线

- **数据授权是先于代码的第 0 步**。反模式:先设计数据管线,授权后补。正确:首谈 P0 问「存量数据当年采集的知情同意是否覆盖新用途」;答不上就按最坏情形默认「去标识化+合成重建」安全路径,推进不依赖答复。
- **已报客户的数字即锁定口径**。反模式:对外文件与内部行情中位数混用,口播即露馅。正确:对外一律用锁定口径;内部区间只留内部文件,红线写明勿口播勿投屏。
- **锁定口径清扫按文档类别全量执行**。反模式:只改任务提及的文件,同类漏网。正确:发现一处泄漏立即 grep 全类清零,例外须明示。
- **前提变化时重构结论**:不硬守旧结论,也不无理由顺从,以新前提为轴重推自洽论证。

## 延伸资料

- `references/directory-and-numbering.md` — 目录/编号/多项目治理/memory 维护细则与失败案例
- `references/decision-gates.md` — 岔路口判据、取值表模板、指令冲突处置、提交纪律
- `references/compliance-and-caliber.md` — 数据合规前置、口径锁定、分层脱敏红线
