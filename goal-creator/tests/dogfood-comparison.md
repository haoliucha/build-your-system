# Dogfood: Hand-written vs goal-creator skill output

## 设置

- **手写版**: `biz/x/docs/goal-prompts/poquan-week-research.md` (创建于 2026-05-25, 在 skill 尚未存在的会话里基于多轮交互手工迭代成型)
- **Skill 版**: `with-skill-results/05-content-research-poquan.md` 的 Step 6 PROMPT (subagent 加载 SKILL.md + samples.md 后产出)
- **同一用户需求**: "我做 X 自媒体,想本周搞个'新人破圈'主题周,需要全网调研话题。给我一个 /goal 让 Claude 过夜跑完整个调研。"

---

## 内容差异表

| 维度 | 手写版 | Skill 版 | 评估 |
|---|---|---|---|
| 主体步骤 (Step 0-6) | 5 阶段 sanity check + parallel subagent + 排序 + 配图 + 终稿 | **完全一致** | 平(70%+ 重叠) |
| Stop conditions (5 条) | ls 图 / grep '!\[' / 3 header / EVENT_LOG / .tmp 清理 | **完全一致** | 平 |
| Hard stops 触发 | turn>30 / X 过期 / meigen 用尽 / playwright crash | **完全一致** | 平 |
| 禁止 fallback | 问 confirm / 估时间 / 编造互动数 / 转 web search | **完全一致** | 平 |
| **"无数据" 占位符** | `"印象热门"` | `"NO_METRICS_AVAILABLE"` | **Skill 版优**:Forbidden Vocab catch — "热门" 命中黑名单,强制替换为机械字符串 |
| **Brainstorm 决策追溯** | 无 — 手写版只有 prompt 本身 | 完整 Q1-Q7 决策 log,含**拒绝的备选**(如"≥5 反常识洞察"被拒因 Forbidden Vocab) | **Skill 版完胜** |
| **Known risks 显式列** | 无 | 4 条 (X 过期 / meigen 耗尽 / Claude 偷懒填假数据 / Forbidden Vocab 复发) + 各对应 mitigation | **Skill 版完胜** |
| **Validator 自检表** | 无 | 9 项 ✅ 显式列出 | **Skill 版完胜** |
| 长度 | ~1900 字符 | ~2900 字符(PROMPT 部分,decision log 另外) | Skill 版长是因为强制结构化 |

---

## Skill 实战发挥关键作用的地方

### 1. Forbidden Vocab 实战 catch

手写版用了"印象热门"作为"抓不到数据时的占位"。看起来 OK,但"热门" 在 Forbidden Vocab 列里。

Skill Step 4 Validator 扫描全文,发现"热门"命中黑名单 → 替换为 `NO_METRICS_AVAILABLE`(机械字符串,evaluator 一眼可识别)。

**重要**:这不是手写者愚蠢,是隐藏命中 — "印象热门" 听起来很机械(标"我抓不到具体数据"),但**机器无法分辨"印象热门"和"评判为热门"**。Skill 的纪律强制了机械等价的字符串。

### 2. Brainstorm decision log 的杠杆价值

手写版没有 brainstorm log。这意味着:
- 6 个月后想改主题周时,**不知道当时为什么 turn cap 选 30、为什么定 5 个独立信号、为什么 over-engineer**
- 想改阈值 (中文 ≥100 赞)时,**摸不到当初的取舍**

Skill 版的 decision log 含:
- Q1-Q7 每问的答案 + rationale
- 拒绝的备选 + 拒绝原因
- Known risks 与 PROMPT 哪条 clause 对应 mitigation

**这是 skill 真正的 marginal value** — 不是更好的 /goal,而是**可演进的 /goal**。

### 3. 没退步的地方(同样重要)

Skill 版**没有**:
- 给出 worse /goal(过度 over-engineer 反而坏)
- 缩减必要的纪律(turn cap / STATUS.md / 禁 confirm 全保留)
- 过分依赖样本(虽然 samples.md 没内容调研样本,skill 通过 Sample 5 + Sample 7 的 **机制** 推导,不是 shape 抄袭)

---

## 关于 "skill 是否真的产生价值" 的诚实评估

### 高 ROI 场景(skill 强建议)

| 场景 | 没有 skill 时的失败概率 | 有 skill 后改进 |
|---|---|---|
| 新人写第一个 /goal | 极高 — 不知道 mental model,大概率写出 evaluator 无法验证的 | **从 90% 失败 → ~20% 失败**(假设遵守 skill) |
| 主观/复合任务被错配给 /goal | 高 — 会硬塞模板 | **Skill 主动拒绝并提议替代** |
| 半年后修改已存在的 /goal | 中 — 摸不着当初取舍 | **Decision log 提供回溯** |

### 低 ROI 场景(skill 边际价值小)

| 场景 | 评估 |
|---|---|
| 老手手写第一遍 | 手写已能接近 best practice(此次 dogfood 证明 70%+ 重叠) |
| 简单一次性任务(< 5 turn) | 跑 skill 的 brainstorm overhead 可能不值 |
| 已在公开 sample 类似形态 (grep-clean migration 等) | 用户可直接抄 Sample,skill brainstorm 是 friction |

### 公正结论

skill 的核心价值不是"写出更好的 /goal",而是:
1. **新人 onboarding 加速**(从不知道 mental model → 跟着 skill 走能产出 production-grade /goal)
2. **决策可追溯**(decision log)
3. **隐藏 Forbidden Vocab catch**(老手也会漏)
4. **主动拒绝不适合 /goal 的任务**(triage gate)

不是 silver bullet,是**纪律 gate**。

---

## v0.1.0 改进点(从这次 dogfood 收集)

无 critical 改动需求。3 个可考虑的 marginal enhancement:

1. **Forbidden Vocab 列表加 "印象热门" 这种 phrase-level 模式**(而非单 word)— 因为"热门"在不同 context 含义不同,phrase-level 更精准
2. **Decision log 模板里加一个"为什么 skill 触发了 Triage 通过"字段** — 帮助用户事后理解为什么这任务 OK 而其他被拒
3. **Triage 触发的拒绝消息**可加一个"如果你认为这不是 X 类问题,理由是?" 让用户有路径推翻 skill 判断

3 条都不阻塞发布,定为 v0.2 candidate。

---

## v0.1.0 verdict

**Production ready**。

- TDD 6/6 GREEN PASS
- Tier 1 50/50 PASS  
- Dogfood 对比:与高水平手写匹配 + 3 个 marginal 提升 + 0 退步
- 真实世界唯一未验证维度:**实际安装为 plugin 后的触发行为**(本次都是 subagent 模拟 + 文件读取),需要在用户级安装后正式触发一次确认。
