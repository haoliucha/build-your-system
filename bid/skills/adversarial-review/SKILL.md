---
name: adversarial-review
description: Use when a To-B bid or client deliverable needs pre-delivery adversarial review — after positioning/wording rewrites, cross-file financial number cascades, multi-agent synthesis drafts, or regenerated visual artifacts (diagrams/PDF/slides). Orchestrates parallel independent review lenses (consistency, cross-document claim provenance, desensitization, overclaim, freshness, arithmetic balancing, page-by-page visual inspection), verifies the checkers themselves against injected known errors, and adjudicates findings before commit. Triggers on phrases like "对抗审校", "多透镜审校", "红队一下这份方案", "交付前审校", "数字级联校验", "脱敏检查", "审一下这份交付物", "adversarial review".
---

# adversarial-review — 交付前对抗审校

对 To-B 投标/交付物在落盘或送客户前跑**多透镜并行对抗审校**。核心信念:改写/级联/综合类工作的真风险不是错字,是**自己引入的隐性自相矛盾与 overclaim**——实测某 To-B 投标项目一轮定位改写引入 6 处缺陷(绝对化 overclaim、防御空话重复、孤儿引用反向泄露等),全部被 4 个独立透镜抓出。

## 何时必跑

- 定位/口径类改写完成后(高危:自引矛盾)
- 财务数字跨文件级联后、commit 前
- 多 agent 综合稿落盘前(二手臆造高发)
- 视觉产物(图/PDF/PPT)重生成后
- 售前材料带去谈之前(红队三视角:客户砍价/合规过度承诺/第三方能力验真)

## 六条铁则

1. **完美贴合结论的引用必核存在性**。无法核实的来源即使承载多条主张也整体剔除+透明度声明;结论改由多条独立证据链支撑,单一来源被证伪后结论不得坍塌。
2. **竞品/第三方平台能力断言逐项验真**。查无公开披露写「官方未公开,不评判」;凭体验语气的推断不得写成事实断言(客户一通电话即可证伪)。写进方案的平台能力与免费配额必须实测或查证后才承诺。
3. **绝对化否定句是 overclaim 高发区**。「不依赖任何 X/绝不 Y」会锁死同文档刻意留开的备选;改陈述具体正向事实。删前提后全文扫孤儿引用,防悬空比较基准反向泄露被隐藏事物的存在。
4. **机械可检问题送审前自修**(算术、超载、舍入)。评审只挑判断类问题——评审是校验,不是替执行者做平衡。
5. **审校结论与用户已明确事实冲突时,按用户事实定稿**,冲突转成置顶的现场核实项,不盲从审校意见改稿。
6. **查不到就明说**。显式列「需进一步确认」清单并附核验路径,禁止用推测填空;抓取被墙(登录墙/风控站点)即停下报告,绝不围绕抓不到的内容编造。

## 三类审校对象 × 透镜清单

### 文档类(方案/报告/纪要)
| 透镜 | 查什么 |
|---|---|
| 一致性 | 文档内自相矛盾;修辞改写混入的语义/义务强度变更须单独申报,不得自称语义等价 |
| claim 溯源 | 跨文档:肯定断言不得与另一份交付物的「未公开/需核实」caveat 打架 |
| 脱敏 | 五类清单 grep 清零:他方客户名/锁定价格等机密、「规避」式表述、内部批注、指向内部文件的引用、折扣策略;合法例外显式保留 |
| overclaim | 绝对化否定句、无据卖点、防御空话重复、孤儿引用 |
| 时效 | 型号/版本/规格/价格等易过期硬事实联网核最新,措辞尽量代际无关 |
| 口径分层 | 已报客户的数字=锁定口径,内部区间/中位数勿外发;客户向与内部的有意不一致须显式报告、由用户拍板 |

### 财务表(报价/成本/排期)
| 透镜 | 查什么 |
|---|---|
| 算术配平 | 独立重算:每总额=分项Σ、每差额=两方相减、中点、章节间对账,清零才 commit |
| 级联完整性 | 口径变更按「文档类别」全量清扫(如所有客户向文件),不只改任务提及的文件;发现一处泄漏即对同类全部 grep |
| 免疫设计 | 叙述类文档保持阶段级/方向性表述、不硬编码周数金额,收窄数字变更的级联爆炸半径 |

### 视觉(图/PDF/PPT/原型)
| 透镜 | 查什么 |
|---|---|
| 逐页目检 | 亲自打开渲染产物,按版面类型抽样(封面/正文/表格/图/多语言页);命令跑通≠排版正确 |
| 对照原始证据 | 综合稿的视觉断言(颜色/布局/文件名)逐条回原始截图重新取样;二手推断不落盘 |
| 实物再核 | 子代理看不到用户截图/文件时,其结论转述前必须与实物逐数核对并明说「已核对吻合」 |

## 工作流实施(多 agent 编排)

1. **子代理简报四件套**:锁定不许改的基线常量、严格输出 schema、来源优先级(官方>一手实测>社区>代理商)、反编造纪律条款。结果质量由简报质量决定。
2. **schema 属性键只用 ASCII**:中文键会被 API 以 400 拒绝(Property keys should match pattern),中文语义放 description/值里。
3. **锚点样例先行**:批量生产同构产物时先手写少量锚点样例锁死全部约定(结构/命名/引用方式),再作模板喂并行 agent 按 author→verify 生产其余,最后统一集成跑真实验证。
4. **检查器有效性反向验证**:检查绿灯后注入一个已知错误,确认检查器真能抓到,删除后复测干净——防空转假通过。报错的检查≠通过的检查,必须修好重跑拿到真实零命中。
5. **grep 管道假阴性**:`grep | head` 掩盖退出码;清零判据用 `grep -c` 计数=0。命中须人工分类——「禁止出现 XX」的规则自述不是泄露。
6. **≥3 独立视角并行**,高优先发现多方共指基本必为真问题;逐条落地后重新验证。
7. **送达即完成**:子代理完成判据=结果已送达编排者并确认成功,不是本地产出文本;中途被问进度即返回当前最佳结果,不为完美拖延。

## 脚本

残留词/敏感词清零校验(退出码可信、缺文件报错不算通过):

路径约定：先定位本 SKILL.md 所在目录，再从该目录解析 `scripts/...`；不要相对于进程 CWD 解析。

```bash
bash scripts/check-residuals.sh scan <词表.txt> <文件...>
# 退出码: 0=清零 / 1=有命中(人工分类) / 2=检查本身报错(不算通过)
bash scripts/check-residuals.sh selftest
# 注入已知脏词反向验证检查器本身有效
```

## 延伸资料

- `references/lens-prompts.md` — 各透镜子代理 prompt 模板(简报四件套骨架、ASCII schema 样例、裁定模板)
- `references/failure-patterns.md` — 反模式→正确做法全目录(高权重实战教训)
- `references/orchestration.md` — 多 agent 编排细节(扇出/裁定/收敛/环境坑)
