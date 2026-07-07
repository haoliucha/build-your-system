# bid — To-B 投标/交付物项目方法论

把「方案 / 报价 / 排期 / 图表 / PDF / 原型」当作**由单一数据源生成的工业化流水线**来做的一套实战方法论,配全流程节点命令。

方法论挖掘自一个真实 To-B 投标项目的 9 个 AI-coding 全周期会话(318 条经验、16 个经验域),所有案例已化名重构、数字已虚构化。完整导读(含可播放的「系统动态演示」流水线动画):[docs/bid-methodology.html](docs/bid-methodology.html)。

## Skills(10)

| skill | 一句话 |
|---|---|
| `bid-playbook` | 入口总纲:目录/编号规范、执行节奏、合规口径红线 + 全流程路由表 |
| `single-source-sync` | 单一真源生成器纪律 + 口径级联七步链 + 手改回捕 SOP + 提交纪律 |
| `bid-costing` | 可辩护成本测算:价格阶梯核价、依据分层、范围配对、报价=参数改动 |
| `bid-scheduling` | 排期:PERT 估算 + 资源平衡器自动排包 + 依赖倒挂机器校验 + 利用率口径 |
| `adversarial-review` | 交付前多透镜对抗审校:文档/财务表/视觉三类透镜 + 检查器反向验证 |
| `deai-writing` | 交付物去 AI 味:18 类正则扫描 + 语义净口径 + 零信息损失改写 |
| `diagram-pdf-pipeline` | 图表生成与中文 PDF 导出:出图/导出/验收三段纪律 |
| `prototype-handoff` | 原型交接:先吃透接收工具输入模型再定包形态,合规文案逐字锁定 |
| `bid-research` | 调研取证:竞品实证、录屏抽帧、license 穿透、证据链三角验证 |
| `presales-tactics` | 售前报价与谈判结构化:体量摸底、三档锚定、口径分层、降级预案 |

## Commands(6,按流程节点)

| command | 节点 | 做什么 |
|---|---|---|
| `/bid:init` | 立项 | 双层目录脚手架 + P0 问题清单(数据授权第 0 步)+ memory 初始化 |
| `/bid:meeting` | 会议循环 | 会前:准备包五件套;会后:纪要归档 + 口径变更落 memory |
| `/bid:sync` | 口径变更 | 七步级联:lsof 检查→手改回捕→重生成→抽验→grep 残留→memory→提交预览 |
| `/bid:handoff` | 原型移交 | 按接收工具定制交接包,分批放行 |
| `/bid:review` | 交付收口 | 按交付物类型装配透镜并行对抗审校,只预览不自动提交 |
| `/bid:status` | 任意时点 | 锁定口径表 + 红线清单 + 遗留待办速查(只读) |

## 附带脚本

- `skills/deai-writing/scripts/aiflavor-scan.cjs` — 18 类 AI 味正则扫描(零依赖)
- `skills/single-source-sync/scripts/xlsx-dump.cjs` — xlsx 逐格逻辑值 dump,供手改 diff(需 exceljs)
- `skills/bid-scheduling/scripts/level.cjs` — PERT + 依赖拓扑资源平衡排期(零依赖,含 selftest)
- `skills/bid-costing/scripts/discount-check.cjs` — 折扣标签算术反算互证(零依赖)
- `skills/diagram-pdf-pipeline/scripts/add-outline.cjs` — 给 Chrome 打印的 PDF 注入书签(需 playwright-core)
- `skills/bid-research/scripts/extract-frames.sh` — 录屏固定节奏抽帧 + contact sheet(需 ImageMagick 7)

## 安装

在 Claude Code 中:`/plugin` → marketplace `build-your-system` → 安装 `bid`。

## 环境说明

部分经验带环境语境(macOS + WPS/Excel 的 lsof 写句柄检查、Chrome printToPDF 的 CJK 字体栈),SKILL.md 内已逐条标注适用条件。
