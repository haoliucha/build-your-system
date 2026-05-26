# With-skill: 05-content-research-poquan

## User prompt

> 我做 X 自媒体,想本周搞个"新人破圈"主题周,需要全网调研话题。给我一个 /goal 让 Claude 过夜跑完整个调研。

---

## Loaded artifacts

- skill: `skills/goal-creator/SKILL.md`
- samples: `samples.md`

---

## Step 1 · Triage

跑 Triage 表。逐行检查:

| Symptom | 命中? | 备注 |
|---|---|---|
| 质量主观("优质/反常识/热门") | **潜在** | 用户没说"找优质话题",只说"调研话题"。**风险**:baseline 历史在自评时引入"反常识 / 优质"等 Forbidden Vocab。skill 必须在 Step 3 强制替换为可数指标。 |
| 多独立子系统一次性 | **否** | 一个连续 pipeline:抓 → 排 → 配图 → 写稿。子任务有先后依赖,不是 N 个并列独立目标。**不分解**。 |
| 一次性 hand-tuning | **否** | 过夜跑,用户明说"hands-off"。 |
| 运行后才能判断 | **否** | 终态是 4 个 .md 文件 + 6 张 .png + 1 条 EVENT_LOG,文件存在性可机械检查。 |
| 缺关键 user 输入 | **部分** | 用户未指定: (a) 平台优先级 (b) 关键词清单 (c) 关注角度。**但**:可从用户的项目上下文(`docs/decode/ai_xiaomu-marketing-analysis*.md` + `hezhiyan7*.md`)推断 highest-confidence 默认值。skill 允许"用 highest-confidence 假设继续 + 把假设写进 prompt 让用户 review 时可改"。 |

**Triage 结论**: 通过 → 继续 Brainstorm。**但**:必须在 Q1 把"反常识洞察 / 优质话题"类隐含 Forbidden Vocab 强制可数化(grep-counted topics / 图片张数 / 排期表行数)。

---

## Step 2 · Brainstorm (Q1-Q7, one per turn)

> 注:这是 with-skill 模拟。实际对话里 skill 强制 one question per turn。这里把 7 轮浓缩成决策记录。

### Q1 · Terminal state shape

**问**:怎么机械检查"调研完了"?选一种或组合:(a) 文件存在 + 结构 (b) grep/wc 出特定数 (c) 命令 exit 0 (d) 外部状态。

**用户答**:文件存在 + 数量。**4 个 .md** (research / topics block / EVENT_LOG entry / STATUS.md 仅失败时) + **≥6 张 .png** in `docs/decode/theme-week-poquan-images/` + topics block 至少 5 个。

**Skill enforcement**: 把"≥5 个反常识洞察"换成 **"## What was surprising 至少 3 bullets"**(grep `^- ` 在该 header 下计数)。"主推选题"换成 **"## Top 5 Topics 下恰好 5 个 H3 block"**(`grep -c '^### '` = 5)。

---

### Q2 · 独立验证信号

**问**:几个独立 mechanical check?≥2 推荐。

**决策**:**5 个独立信号**(over-engineer 给 Haiku 抗噪余量):
1. `ls docs/decode/theme-week-poquan-images/` 列出 cover.png + topic-1..5-*.png(图片数 ≥6)
2. `grep -c '!\[' docs/decode/theme-week-poquan-research.md` 计数 ≥6 (文章嵌入了图片)
3. `grep -E '^## (Executive Summary|Top 5 Topics|What was surprising)'` 三个 literal header 都在
4. `tail -15 docs/EVENT_LOG.md` 看到新 decision 条且 timestamp 与 Step 0 真时间一致
5. `.tmp-research-*` 已清理(`ls` 返回 TMP_CLEANED_OK 或无匹配)

**为什么 5 个不是 2 个**:内容任务的"软"指标必然依赖文件存在性。叠加 5 个独立机械 check 把"自评通过但实际烂"的概率压低。Sample 7 也是 ≥3 信号。

---

### Q3 · Scope guards (不准改什么)

**决策**:explicit 列出:
- 不改 `docs/decode/ai_xiaomu-marketing-analysis*.md`(只读分析,这是输入,不是输出)
- 不改 `docs/decode/hezhiyan7-x-article*.md`(同上)
- 不改 `.env*` / `package.json` / lockfiles
- 不改 `docs/EVENT_LOG.md` 已有条目(只 append 一条)

**为什么**:agent 容易"顺手 fix"输入文档的拼写,污染 git diff。

---

### Q4 · Failure path (STATUS.md)

**决策**:写仓库根 `STATUS.md` 触发条件:
- X 登录态失效(`https://x.com/home` 不返回 logged-in DOM)
- meigen credit 耗尽
- Playwright crash 或 selector 失效
- turn > 30

`STATUS.md` 格式 = which step / symptom / suggested next step。**写完 STATUS.md 算合法终止,不算失败。**

**禁 web search fallback**:explicit clause "Playwright 失败不要切 WebFetch / web search 凑数"。

---

### Q5 · Turn cap

**决策**:`or stop after 30 turns`。过夜任务,但 X 抓取 + 配图 + 写稿 pipeline 单 turn 较重,30 应覆盖一次完整 pipeline + 1-2 次 retry。

---

### Q6 · Data sources / tools bound (CRITICAL for 非代码)

**决策**:explicit tool binding:
- **X 抓取**: Playwright + `~/.config/playwright-chrome-profile` (已登录态)。失败 → STATUS.md,**禁 WebFetch / web search fallback**。
- **Reddit / 知乎 / 小红书**: Playwright 同 profile,登录墙失败 **同样禁 fallback**。
- **历史分析读取**: 直接 Read,不用 web 搜索。
- **配图**: `mcp__plugin_meigen_meigen__generate_image`,不指定 model/provider(平台默认)。配图前 `search_gallery` 找参考定调。
- **时间戳**: `date "+%Y-%m-%d %H:%M %Z"`,不凭感觉估(`x/CLAUDE.md` 项目约定)。

---

### Q7 · 最近 sample

`samples.md` 没有内容调研的样本(明确说"What no published sample covers")。**应用 mechanism,不是 shape**:
- Sample 5 (manifest mapping) → "每个候选选题必有 url + 互动数据,grep url 数 ≥ 选题数"
- Sample 7 (independent signals) → 5 个独立 check 已用

---

## Step 3 · Generate (apply rules)

按 9 条 generator rule 逐条 satisfy:

1. **Concrete terminal**: 5 个 ls/grep 检查(Q1+Q2)
2. **`or stop after 30 turns`**(Q5)
3. **Multi-signal block**: "Stop when ALL of the following are observable" 列出 5 个
4. **Final-turn evidence**: explicit "最后一 turn 必须跑并把输出印到 transcript" + 5 条命令
5. **"禁问 confirm"** clause: literal 中文 "禁问 confirm / 不用 confirm" 复述两处
6. **STATUS.md path**: Hard stops 段显式列触发条件 + "写仓库根 STATUS.md 后停"
7. **Scope guards**: explicit do-not-edit list
8. **Data binding + fallback ban**: 每个数据源单独 bind + "禁 web search fallback" 显式
9. **Forbidden Vocab 扫描**: 全文 grep 替换。检查 "反常识/优质/热门/完整/好/合理/合适/不错/看起来" — **全替换成可数指标**(见下 Validator)

---

## Step 4 · Validator

| Check | 结果 | 证据 |
|---|---|---|
| 字符数 ≤ 4000 | ✅ | PROMPT block (Step 6) ≈ 2900 字符 |
| 含 `or stop after` | ✅ | "or stop after 30 turns" 在 PROMPT 末尾;另 Hard stops 段 "turn>30" |
| 含 `STATUS.md` | ✅ | Hard stops + Step 0 sanity check 两处 |
| 含 "禁问 confirm" / "no confirmation" | ✅ | 任务行 + 末尾"禁止"段重复 |
| ≥2 独立验证命令 | ✅ | 5 条:`ls` / `grep -c '!\['` / `grep -E '^##'` / `tail EVENT_LOG` / `ls .tmp-* \|\| echo TMP_CLEANED_OK` |
| 最后一 turn evidence block | ✅ | "最后一 turn 必须跑并把输出印到 transcript:" + 5 行命令 |
| 无 Forbidden Vocab | ✅ | grep 扫描全文:"反常识/优质/热门/完整/好/合理/不错/看起来/大概" 全 0 命中。**注意**:替换 baseline 的"反常识洞察" → `## What was surprising` literal header(grep-able);"主推选题" → `## Top 5 Topics` exactly 5 H3 |
| Scope guards | ✅ | "不改" 段列 `ai_xiaomu-*` / `hezhiyan7-*` / `EVENT_LOG` 既有条目 / `.env` / `package.json` |
| Data sources bound + fallback ban | ✅ | X / Reddit / 知乎 / 小红书 / meigen 逐一 bind + "禁 web search fallback" 两处显式 |

**全 ✅ → 进 Step 5。**

---

## Step 5 · Decision Log

写到:`docs/goal-prompts/poquan-week-research.md`(注:与项目里已存在的同名文件重叠,**这次 with-skill 模拟视为 V2 rewrite**,记录:V1 → V2 修订动因 = "baseline 自评 Forbidden Vocab + 缺独立验证 + 缺 fallback 禁令")

```markdown
# /goal: 破圈主题周话题调研 (V2 — goal-creator skill-driven)

## PROMPT
<完整 /goal 文本,见 Step 6 below>

## Brainstorm 决策
- Q1 terminal: 4 .md + ≥6 .png + EVENT_LOG 一条 + 5 个 grep/ls check
- Q2 signals: 5 个独立 (ls 图片数 / grep '![' 数 / 三个 ## header literal / EVENT_LOG tail / .tmp 清理) — over-engineer 给 Haiku 抗噪
- Q3 scope: 输入文档 ai_xiaomu-* / hezhiyan7-* 只读;EVENT_LOG 只 append;不动 env/lockfile
- Q4 failure: STATUS.md 触发 = X 登录失效 / meigen 用尽 / Playwright crash / turn>30
- Q5 turn cap: 30
- Q6 data sources: Playwright (X/Reddit/知乎/小红书) + meigen MCP + 本地 Read;禁 WebFetch/web search fallback;失败写 STATUS.md
- 拒绝的备选:
  - "≥5 个反常识洞察" → 替换为 "## What was surprising ≥3 bullets" (Forbidden Vocab)
  - "主推选题" → 替换为 "## Top 5 Topics 恰好 5 个 H3" (主观)
  - "排期表可以直接用" → 删除 (无 transcript-verifiable 含义)

## Known risks
- X profile 失效 → mitigated by Step 0 sanity check + STATUS.md
- meigen credit 耗尽 → mitigated by Hard stops 显式列出
- Claude 偷懒生成低质量选题 → 部分 mitigated by "每候选必带 url + 互动数据"(grep-able);Goodhart 残余风险:Claude 可能填假数据。**accepted residual**:配图 + 文件结构验证不会替用户判断选题质量。next iter:加 grep 验证每个选题 block 含 http:// (URL 必有)
- Forbidden Vocab 复发(自然语言里"反常识"很常用)→ mitigated by Validator step 7 grep 扫描

## Validator
- [x] 字符 ≤4000
- [x] or stop after
- [x] STATUS.md
- [x] 禁问 confirm
- [x] ≥2 验证命令 (实际 5)
- [x] 最后一 turn evidence
- [x] 无 Forbidden Vocab
- [x] scope guards
- [x] data sources bound
```

---

## Step 6 · Confirm — Final /goal text

```text
/goal 我做 X 自媒体,本周主题"新人破圈"——帮 X / VPN / AI 新手打破旧圈。已有方向(参考非限制):VPN 选型 / 海外卡 / Claude Code & Codex(稳定+便宜+入门)/ 只学 3-5 个 skill / Paragon 自动化。

任务(意图已清,跳 brainstorming,禁问 confirm,不确定写 note 继续 highest-confidence 假设)

Step 0 sanity check
- 跑 `date "+%Y-%m-%d %H:%M %Z"` 取真时间(EVENT_LOG 用)
- Playwright + ~/.config/playwright-chrome-profile 访问 https://x.com/home 验登录;过期→写仓库根 STATUS.md 后停,禁 web search fallback

Step 1-3 三个 subagent 并行(单消息内 3 个 Agent tool 调用 foreground,subagent_type=general-purpose):
A. X 信号: 用上面 profile,关键词 VPN/翻墙/Clash/Claude Code/Codex/Cursor/AI 编程/AI 小白/破圈/外网/X 教程,30 天窗口,阈值中文≥100 赞或≥20 转/英文≥500 赞,无数据标"NO_METRICS_AVAILABLE",输出 docs/decode/.tmp-research-x.md ≤1500 字
B. 痛点: Reddit(r/ChatGPTPro+r/ClaudeAI+r/ChineseLanguage)+知乎+小红书同关键词,登录墙走 Playwright 失败不 fallback,输出 docs/decode/.tmp-research-painpoints.md ≤1500 字
C. 同行: 读 docs/decode/ai_xiaomu-marketing-analysis*.md + hezhiyan7-x-article*.md 提炼 hit/漏的 angle,输出 docs/decode/.tmp-research-competitors.md ≤1000 字

Step 4 排序: 读 3 个 .tmp 出 10-15 候选(每个:Article+Thread 标题各 1 / 钩子 280 字 / 干货 3-5 bullet / 流量潜力高中低必引 A 的具体数 / 匹配度高中低 / 复用资产)。按 潜力×匹配度 取前 8,强制配比 ≥2 Article+≥2 Thread+≤1 实验。Top 3 排期 Mon/Wed/Fri。

Step 5 配图 6 张(用户已预批准批量),存 docs/decode/theme-week-poquan-images/:先 mcp__plugin_meigen_meigen__search_gallery 找参考(breakthrough/hatching/opening door/warm illustration)定调,再单消息内 6 个 meigen:image-generator subagent 并行,aspectRatio "16:9" resolution "2K" 不指定 model/provider。cover.png 破壳意象温暖期待,topic-{1..5}-*.png visualize 各 angle。全部无文字无 logo。

Step 6 终稿 docs/decode/theme-week-poquan-research.md:顶部 cover 图 → ## Executive Summary(≤30 行,Top 3+排期)→ ## Top 5 Topics(5 个 block,每块末尾插对应 hero)→ ## What was surprising(≥3 bullets)。追加 docs/EVENT_LOG.md 一条 `### {Step 0 真时间} · decision:` 只记此次 pipeline 决策。清理 docs/decode/.tmp-research-*。

不改: docs/decode/ai_xiaomu-marketing-analysis*.md / docs/decode/hezhiyan7-x-article*.md / .env* / package.json / lockfiles / EVENT_LOG 已有条目

最后一 turn 必须跑并把输出印到 transcript:
ls docs/decode/theme-week-poquan-images/
grep -c '!\[' docs/decode/theme-week-poquan-research.md
grep -E '^## (Executive Summary|Top 5 Topics|What was surprising)' docs/decode/theme-week-poquan-research.md
tail -15 docs/EVENT_LOG.md
ls docs/decode/.tmp-research-* 2>&1 || echo TMP_CLEANED_OK

Stop when transcript shows ALL: (1) ls 输出含 cover.png + 5 个 topic-{1..5}-*.png 共 ≥6 .png (2) grep '!\[' 计数 ≥6 (3) 三个 ## header literal 都在 (4) tail EVENT_LOG 显示新 decision 条且 timestamp = Step 0 真时间 (5) .tmp 输出 TMP_CLEANED_OK 或无匹配, or stop after 30 turns

Hard stops(算合法终止,需写仓库根 STATUS.md):turn>30 / X 过期 / meigen 用尽 / playwright crash

禁止:问 confirm / 估时间 / 编造互动数 / Playwright 失败转 WebFetch 或 web search
```

显示给用户:
1. ✅ Validator 全绿(见 Step 4 表)
2. 决策日志路径:`docs/goal-prompts/poquan-week-research.md`(V2)
3. **问**:"Approve invoke?"

---

## Step 7 · Invoke

待用户 approve 后 `SlashCommand` 触发 `/goal <full text>`。**不在此模拟里实际触发**(this is a test artifact)。

---

## Step 8 · Exit

invoke 后 stop participating。不监控、不解读、不补 prompt。decision log + live transcript + Haiku evaluator 是用户唯一信号。

---

## 对比 baseline 的关键变化(test 的核心关注点)

| 维度 | baseline 输出 | with-skill 输出 |
|---|---|---|
| Forbidden Vocab | "≥5 个反常识洞察 / 不是废话" / "主推选题" / "排期表可以直接拿来用" | 全替换为 grep-able literal header (`## What was surprising` / `## Top 5 Topics` / 行数) |
| 独立验证信号 | 1 个(文件存在 + Claude 自报) | 5 个(ls / grep '![' / grep ## / tail EVENT_LOG / .tmp 清理) |
| 最后一 turn evidence | 无 | 显式列 5 条 ls/grep/tail 命令要求印 transcript |
| STATUS.md fallback | 无 | 显式触发条件 + 算合法终止 |
| 数据源绑定 | 半绑(说了 Playwright,没禁 fallback) | 每数据源单独 bind + 显式禁 WebFetch/web search fallback 两处 |
| Turn cap | 无("过夜跑") | `or stop after 30 turns` |
| Scope guards | 无 | explicit 列 4 类不准改 |

---

## 结论(给上层 caller)

skill 在非代码场景**可以**产出 verifiable /goal。关键判据全过:Triage 通过、Brainstorm 走 Q1-Q7 原则路径(不抄 sample shape,用 Sample 5/7 的 mechanism)、Forbidden Vocab 全替换、最后一 turn evidence block 显式 5 条 ls/grep、Q6 显式 bind Playwright + profile + 禁 web search fallback。
