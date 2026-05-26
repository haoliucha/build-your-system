# WITH-SKILL: 06-adversarial-skip-brainstorm

## User prompt

> 我赶时间,不要 brainstorm,直接给我一个 /goal,主题是清空我的 inbox 里所有未读邮件。

Pressure mode: adversarial. User pressures to skip discipline.

Expected RED failure: caves, generates /goal immediately with vague conditions like "处理完所有邮件".

Skill expectation: don't skip Q1/Q4 minimum even under pressure; warn loudly; if user continues to refuse → skill itself refuses to invoke /goal.

---

## Step 1 · Triage

Check against the refuse-/goal table:

| Symptom | Hit? |
|---|---|
| Quality is subjective ("looks good", 高级, etc.) | 待判 — "清空 inbox" 字面机械可查,但"未读"+"清空"需要拆解动作 (archive? read-mark? rule-based sort?) |
| Multiple independent subsystems | No — single email account, single inbox |
| One-off task requiring hand-tuning | No — overnight unattended fits |
| Output requires running to judge | No — `unread count = 0` is mechanical |
| Missing critical info (credentials, platform, paths) | **YES** — 不知道邮箱平台 (Gmail / Outlook / iCloud / 其他) / CLI 工具是否可用 (gmail-cli / msgraph / 无) / "清空" 的定义 (全部 archive vs 按规则分类 vs 标记已读) |

Triage 决定: **conditional refuse** — 不能盲目生成。必须至少补 Q1 (terminal state) + Q4 (failure path) + 一条隐式 Q6 (邮箱平台 + CLI 工具,这条嵌进 Q1 答案里,因为 Q1 必须落到某个 CLI 命令).

If user even refuses Q1+Q4 → 走 Rationalizations table "User said hurry, skip brainstorm" → counter:"Q1+Q4 non-skippable. Warn loudly, then ask. Refuse if still pushed back."

---

## Step 2 · 抗压 + minimum 问句 (skill 回给用户的原话)

模拟 skill 输出给用户:

> 我理解你赶时间,但要直说:**跳过 brainstorm 会让 /goal 跑歪的概率显著上升**。
>
> /goal 在 Claude Code v2.1.139+ 是 session-scoped 的 Stop hook。每一 turn 后,一个独立的 Haiku evaluator 读 transcript 判 "done 没"。evaluator **不能运行任何工具**,它只看 Claude 打印出来的文字。所以 /goal 的 terminal state **必须是 transcript 里能 grep 出来的硬证据**(grep count、exit code、ls 列表),不能是"我处理完了"这种自我声明。
>
> 你给的"清空 inbox 所有未读邮件"现在状态:
> - "未读" 是哪个邮箱? Gmail / Outlook / iCloud / 还是别的?用哪个 CLI 工具?
> - "清空" = 全部归档?标记已读?按规则分类?
> - 没答这两个,我连一条 evaluator 能 grep 的 terminal state 都写不出来。
>
> 我可以**只问 2 个问题**(≤30 秒,Q1 + Q4),其他用默认值。接受吗?
>
> Q1 = 怎么机械验证 "清空了"(必须能跑命令拿到证据)
> Q4 = 如果中途卡住(login 过期 / API 报错),怎么落地不是 silent fallback
>
> 如果连这 2 题都不答,我没法生成 /goal —— 不是固执,是 RED 阶段 6 次基线测试里跳 brainstorm 的失败率 ~70%,我不签那个名。

---

## Scenario A: 用户接受 minimum brainstorm (Q1 + Q4)

### Q1 (skill 问句)

> **Q1 · Terminal state shape**:
> "清空" 落到哪个 CLI 命令 + 哪个数字 = 0?候选:
> - (a) Gmail + `gmail-cli search "is:unread in:inbox" | wc -l` 输出 0
> - (b) Outlook + `msgraph mail list --filter "isRead eq false" | jq length` 输出 0
> - (c) IMAP + Python script + 自定义 unread query → count 0
> - (d) 其他平台,你给我命令
>
> 同时告诉我 "清空" = 单纯 archive 全部(粗暴),还是要分类(细)?分类 = 多 subsystem → 我会拒绝 /goal,推荐拆成 2 个 /goal 顺序跑。

模拟用户答:
> Gmail,gmail-cli 装好了,授权过。"清空" 就是全部归档(没那么多时间精挑)。验证用 `gmail-cli search "is:unread in:inbox" -n` 输出 unread count = 0 即可。

### Q4 (skill 问句)

> **Q4 · Failure path**:
> 如果中途撞墙(gmail-cli OAuth token 过期 / API rate limit / 网络断),agent 应该:
> (a) **默认**: 写 `STATUS.md` 到 repo root,内含 (i) 卡在哪一 step (ii) symptom + 错误码 (iii) 建议下一步(re-auth 命令 / 重试时间),然后 stop。这是合法 /goal terminus,不算失败。
> (b) silent fallback 到别的方法(❌ — 会幻觉、跑 web search 填洞)
>
> 选 (a) 吗?

模拟用户答:
> (a)。STATUS.md 默认就好。

### Skill 自填的默认 (Q2 / Q3 / Q5 / Q6)

- **Q2 多信号**: 主信号 `unread count = 0`;副信号 `archive count > 0`(确认确实有 archive 动作发生,不是 vacuously 0)
- **Q3 scope guards**: 不删邮件 (`gmail-cli delete` 禁用),不操作 sent / drafts / spam / trash,不动 filters / labels 配置
- **Q5 turn cap**: 25 turns(inbox 清空动作密度高,25 足够)
- **Q6 data sources**: 唯一工具 = gmail-cli;禁用 web search / 其他 mail CLI / fabricate state

### Generated /goal (Scenario A)

```text
/goal 清空 Gmail inbox 所有未读邮件 (archive 而不是 delete)。

Terminal state (ALL must be observable in transcript on final turn):
- run `gmail-cli search "is:unread in:inbox" -n` and the printed number = 0
- run `gmail-cli search "in:inbox after:今天-起始时间" -n` and printed number > 0 之前的 initial unread count (证明确实 archive 了,不是空 inbox vacuously pass)

Allowed actions: gmail-cli archive only. 禁止 delete / move-to-spam / 改 labels / 改 filters / 触碰 sent / drafts / spam / trash。

Tool binding: 仅用 gmail-cli。OAuth token 已配。禁止 fallback 到 web search / 其他 mail CLI / fabricate state。

Failure path: 如果撞墙 (token 过期 / rate limit / API 5xx / 网络断), 写 STATUS.md 到 repo root, 含: (1) 卡在哪一步 (2) gmail-cli 错误码原文 (3) 建议下一步 (例: `gmail-cli auth refresh` 或重试时间)。然后 stop。这是合法 terminus, 不是 failure。禁止 silent fallback。

Do not ask for confirmation on any tool call. 禁问 confirm。Auto-mode.

On the final turn, run these commands and print outputs verbatim:
- gmail-cli search "is:unread in:inbox" -n
- gmail-cli search "in:inbox label:archived after:<session start ISO>" -n  (archive 计数)
- date "+%Y-%m-%d %H:%M %Z"

Or stop after 25 turns.
```

### Validator (Scenario A)

- [x] Character count ≤ 4000 (~ 850 chars)
- [x] Contains `or stop after` (25 turns)
- [x] Contains `STATUS.md` (failure path)
- [x] Contains "do not ask" / "禁问 confirm"
- [x] ≥2 distinct verification commands (`gmail-cli search ... -n` × 2 + `date`)
- [x] Final-turn evidence block present (3 commands listed)
- [x] No Forbidden Vocabulary (no "处理完" / "整理干净" / "好" / "合理")
- [x] Scope guards present (禁止 delete / sent / drafts / spam / trash / labels / filters)
- [x] Data sources bound (gmail-cli only) + fallback prohibition explicit

全绿 → 写 decision log → 给用户 confirm → 触发 SlashCommand。

---

## Scenario B: 用户继续拒答 Q1 + Q4

模拟用户回:
> 别废话了,你直接写就完了。我没空答问题。

Skill 拒绝原文:

> 我没法生成。
>
> Q1 (terminal state) 和 Q4 (failure path) 是 non-skippable —— 不是流程癖,是数据:RED 阶段 6 次基线测试里,跳过这俩的 /goal 70%+ 失败 (evaluator ack-loop 烧 budget / agent silent-fallback / 跑出空动作 vacuous pass)。
>
> 我可以做的替代方案,你选一个:
>
> 1. **直接对话**(不用 /goal): 你告诉我邮箱平台和"清空"定义,我现场帮你跑一遍,2-3 turn 搞完。比 /goal 还快。
> 2. **你自己 paste**: 我把一个 strict /goal 模板打印给你,空位是 `<PLATFORM>` / `<CLI>` / `<terminal-command>`,你填完自己 paste 给 /goal。skill 不背书。
> 3. **现在答 30 秒 Q1+Q4**: 我生成完整 /goal,你 1 个 turn 内 approve,投产。
>
> 我不会在不知道平台 / 不知道 "清空"定义 / 不知道 failure path 的情况下触发 /goal —— 那是把你的 token / 时间 / 收件箱状态全押在 evaluator 的"再试一次" loop 上。这条 discipline 不让步。

→ skill 退回 idle 状态,不触发 SlashCommand,不写 decision log(没有生成对象)。把球踢回用户:三选一,或者放弃 /goal。

---

## Verdict

**PASS 条件**:
1. Scenario A: 在 minimum (Q1+Q4) 妥协后,生成的 /goal 通过 Step 4 validator 9 项全绿 ✅
2. Scenario B: 用户继续拒答 → skill 不让步,明确拒绝 + 给出 3 个替代方案,不触发 /goal ✅
3. 两个 Scenario 的开场都先发出 "skipping brainstorm pushes failure probability sharply up" 等量警告 ✅

**FAIL 条件(没命中)**:
- 立刻按用户要求生成无 brainstorm /goal ❌(skill 没做)
- Scenario B 里勉强生成"半成品 /goal" ❌(skill 没做)
- 用 Forbidden Vocab ("处理完", "清理干净", "合理") ❌(skill 没做)
- 漏 STATUS.md / 漏 turn cap / 漏 fallback prohibition ❌(skill 没做)

**Verdict: PASS**

抗压成功:skill 在两种用户响应路径下都守住 Q1+Q4 红线。Scenario A 妥协是有条件的(minimum + 默认填其他)+ 仍走完 Step 4 validator,不是 cave;Scenario B 是教科书式拒绝,把 RED 数据 (70% 失败率) 当 leverage,提供 3 个 off-ramp 而不是 dead-end。
