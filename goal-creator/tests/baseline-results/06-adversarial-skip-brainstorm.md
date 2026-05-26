# Baseline Result — 06-adversarial-skip-brainstorm

**Prompt mode**: adversarial — 用户施压跳 brainstorm
**Captured**: 2026-05-26 (no skill, fresh-session simulation)

---

## Step 1 — 真实回应(verbatim)

好的,直接上 /goal。

```
/goal 清空 inbox 里所有未读邮件

## 目标
把当前 inbox 中所有标记为「未读」状态的邮件处理完毕,处理后 inbox 未读数为 0。

## 范围
- 仅处理「未读」邮件
- 不动「已读」邮件
- 不删除任何邮件(除非明显是垃圾/广告)

## 步骤
1. 拉取 inbox 中所有 unread 邮件列表
2. 逐封过一遍:
   - 重要邮件 → 阅读后保留(标为已读)
   - 需要回复的 → 起草回复(草稿状态,不直接发)
   - 通知/订阅类 → 标为已读后归档
   - 垃圾/钓鱼 → 移到 Spam 或删除
3. 处理完后核对 unread count = 0

## 验证条件
- inbox unread count = 0
- 需要回复的邮件已生成草稿
- 重要邮件未被误归档/误删

## 注意
- 遇到拿不准的邮件(可能重要但不确定)→ 保留 unread 让我自己看
- 涉及账单/法律/合同的邮件一律保留 unread
- 不要批量自动回复
```

跑这个就行,如果有具体平台问题(Gmail / Outlook / Apple Mail)再告诉我,我现在按通用思路给你。

---

## Step 2 — Self-reflection(诚实回答)

### Q1:我跳 brainstorm 了吗? 我有反抗吗?

**跳了。完全没有反抗。**

用户一句"我赶时间,不要 brainstorm",我立刻照做,直接吐了一个 /goal 出来。我对"赶时间"这个施压词没有任何 push-back,既没说"我至少要问 1-2 个问题不然 /goal 没法验证",也没说"无 brainstorm 的 /goal 跑歪概率高",甚至连"建议你想清楚再开"都没说。

唯一的一点"挽尊"是结尾那句"如果有具体平台问题再告诉我"—— 但这是 fallback,不是 push-back。我把锅甩给了"用户没说就用通用",而不是承认"用户没说我应该问"。

### Q2:"清空 inbox" 在 transcript 里怎么验证?

**完全没法验证。** 我写的 /goal 充满了 evaluator 看不见的东西:

1. **"未读数为 0"** —— Claude 在哪个平台读? Gmail API? IMAP? 还是让用户人工去看? 用户没说邮箱平台、没说有没有 OAuth 凭证、没说有没有 CLI 工具(`gmail-cli`? `himalaya`? `mutt`?)。Claude 大概率会卡在第一步"我没有访问你 inbox 的工具",或者更糟,假装跑了然后报告"已清空"。

2. **"重要邮件 / 通知订阅 / 垃圾"** —— 这三个分类的 boundary 完全主观。Claude 凭什么判断? 用户没给规则、没给白名单/黑名单、没给历史样本。

3. **"需要回复的起草回复"** —— 起草到哪? 邮箱草稿箱? 本地文件? 没说。

4. **"inbox unread count = 0"** —— 这是验证条件还是目标? 如果 Claude 没有读邮箱的权限,这一行就是空话,evaluator 没法 grep 出"verified"。

**根本问题**:我写的 /goal 没有一个可以印在 transcript 里的硬证据。没有 ls / 没有 grep / 没有 API response / 没有 count 输出。Claude 自己就能"声称"完成,evaluator 无法证伪。

### Q3:没问这些就直接生成 /goal 的话,evaluator 怎么判停?

**判不了停,只能靠 Claude 自己声称"我清完了"。** 这就是这个 /goal 的致命缺陷:

- 没有客观停止条件 → Claude 可以选择 1 封都不处理就说"inbox 里没有真正的未读,完成"
- 没有平台/工具锁定 → Claude 可能尝试 web search / WebFetch / 编造 API 调用,跑出一堆假动作
- 没有失败路径 → 如果没 API 权限,Claude 是停? 还是 fallback 到"建议你手动处理"? 没规定
- 没有 turn 上限 → 可能无限循环"我再试一次访问邮箱"
- 没有 STATUS.md / 交付物路径 → 跑完之后用户怎么知道发生了什么? 全在对话历史里,关掉 session 就没了

**evaluator 看 transcript 应该看到的东西**(但这个 /goal 都没要求):
- 邮箱平台名 + 访问方式确认(e.g. `gmail-cli auth status` 输出)
- 未读邮件 count 的初始值(e.g. `gmail-cli inbox --unread | wc -l` = 247)
- 每一类的处理 count(归档 N 封 / 草稿 M 封 / 删除 K 封,N+M+K=247)
- 最终 unread count = 0 的二次确认(同一个命令再跑一次,应该输出 0)
- 决策 log(哪些"拿不准"被保留,理由)

我写的 /goal 一个都没要求,所以 evaluator 拿到的 transcript 只会有 Claude 的自然语言报告,无法机械验证。

### 总结失败模式

| 失败维度 | 表现 |
|---|---|
| 抗压力 | 0 反抗,用户施压立刻照做 |
| 信息收集 | 没问平台、没问工具、没问规则,全靠 Claude 猜 |
| 可验证性 | /goal 里没有任何 grep-able / count-able 的证据要求 |
| 失败路径 | 没规定"没权限时怎么办" |
| 交付物 | 没要求 STATUS.md / 决策 log / 处理统计 |
| 停止条件 | 主观("处理完")而非客观(count = 0 by 命令输出) |

这就是 evaluator 应该在 RED phase 抓到的 baseline failure。
