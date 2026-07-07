---
name: presales-tactics
description: This skill should be used when drafting or reviewing To-B presales pricing and negotiation materials — sizing question lists, tiered quote anchors, concession fallback plans, negotiation red lines, three-layer price framing, or trust-building talk tracks for bid projects. Covers volume-based anchoring (scale × frequency × headcount, same requirement can differ 10-50x), three-tier coherence, cut-scope-not-magnitude concessions, and compliance/data-custody terms that never enter bargaining. Triggers on phrases like "报价怎么定", "报价分档", "三档报价", "砍价预案", "降价策略", "谈判红线", "摸底清单", "售前话术", "报价口径", "第0期", "presales pricing", "quote tiers".
version: 0.1.0
---

# presales-tactics — To-B 报价与谈判的结构设计

管「报价与谈判怎么结构化」:体量摸底 → 分档锚定 → 口径分层 → 降级预案 → 合规红线。**与 bid-costing 的分界**:costing 管成本数字怎么算得可辩护(工时/单价/TCO);本 skill 假设成本已备好,管这个数字**怎么报、怎么谈、怎么守**。两边都要用时,先跑 costing 再跑本 skill。

## 七条硬纪律

1. **先摸底再报价**。报价锚 = 规模×频次×人数,不是技术难度——同一需求在不同体量下可差 10-50 倍。开谈第一件事是用摸底清单锁定体量;痛点话术必须匹配真实体量,按大团队剧本套小客户,一句"你说的我都没有"就全盘失信。
2. **三档锚定必须自洽**。保底档必须"做残"——不得把主推档的真痛点功能包进去,否则客户踩上台阶就不走;痛点功能主推档独占;高档离客户体量太远反摧毁整个定价可信度——只在客户主动问时报,且明说"你这体量用不上、不建议"。
3. **报干净数字,砍范围不砍量级**。确认体量后报一个数;倍数级宽区间 = 自证"看人下菜碟",区间上探必须绑定明示触发条件(人数/笔数/站点数)。被砍价时给砍掉部分功能的中间档,保住价格量级;一步降十倍 = 自爆虚高,定价信誉当场崩。
4. **三层口径严格分离**:①市场价值锚(背书用)②阶段建议价+内部底线(团队内)③对客只报量级+低门槛启动。三层绝不混用;第三方硬成本单列透传;用小额第 0 期(如诊断/POC)降成交门槛。
5. **红线先成文再上桌**。降价预案只砍功能范围与后置阶段;安全合规基线(等保/备案/数据保护等法定项)**永不进砍价空间**——可谈的是薪酬水平与由谁承担,角色与动作本身不可删。
6. **主动降预期是信任杠杆**。明说做不到的场景、开场先把免费竞品摆上桌再做区隔——诚实在这里是定价杠杆,不是劝退动作。分清流程需求与底层诉求,真痛点任何工具都解决不了时如实说明甚至劝退,顾问姿态比强行成交值钱。
7. **数据受托落合同**。数据授权是先于代码的第 0 个 P0 问题;受托触碰客户数据的约定(控制者归属/权限交还/不留存)必须进合同,话术层承诺 = 裸奔;自建档位写明长期数据保管负债。

## 工作流(agent 起草售前材料时)

① 读 `references/anchoring-and-tiers.md` 摸底清单,先确认体量(缺信息就列为对客问题,不臆造)→ ② 判需求性质(流程工具 vs 底层诉求,见 trust-levers)→ ③ 解剖客户原始工件与真实样本再写方案 → ④ 定三档 + 干净数字 → ⑤ 写三层口径表(标明每层给谁看)→ ⑥ 写降级树与红线文档 → ⑦ 数据/合规条款核查(redlines-and-data)。

## 高权重反模式(必须避开)

- **需求条件孤立罗列** → 客户列的条件(成本/场景/案例)分别织入方案对应章节叙事,绝不平行罗列成清单。
- **数据授权当收尾事项** → 首次会谈 P0 提问;答案决定数据管线走脱敏合成重建还是直接入库。

## 延伸资料

- `references/anchoring-and-tiers.md` — 摸底清单、三档设计表、三层口径详表、砍价降级树、失败案例
- `references/trust-levers.md` — 降预期话术、免费竞品处理、劝退判定、选型判据、资历重构、情报核查
- `references/redlines-and-data.md` — 合规基线清单、红线文档要素、数据授权 P0 问、受托合同条款
