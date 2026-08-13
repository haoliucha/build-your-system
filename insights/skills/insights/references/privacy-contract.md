# 隔离、隐私与提交边界

这些是 Codex 工程护栏，不是 Claude `/insights` 的产品 meaning，也不是新的分析视角。

- 会话源只读；输出固定为 `$CODEX_HOME/usage-data/insights/`。
- 原始 session ID 只用于发现与去重；持久 facet 使用 opaque key、source fingerprint 和安全项目标签。
- 模型输入先拦截 secret、Bearer、Cookie、邮箱、IP 与私人绝对路径；仍保留目标、错误、反馈和结果语义。
- 每个 `codex exec` 使用隔离 HOME/CODEX_HOME、现有登录凭据、只读 sandbox、忽略用户配置与项目规则，并关闭 Shell、Web、MCP、Apps、浏览器、Computer Use、图片与多代理。
- stdout JSONL 和 stderr 必须同时持续排空；Schema 结果先写 `.partial`，通过验证后原子接纳。暂停或失败删除 partial。
- SQLite 队列权限 0600，WAL + FULL synchronous；成功 facet 立即持久化，running 在恢复时回到 queued。
- 清单阶段把标准化、脱敏后的分析材料冻结到 SQLite，支持崩溃恢复；不持久化原始 JSONL、原始路径或原始 session ID，成功提交后清除材料快照。
- 分析版本、meta、normalizer、facet prompt 与 source fingerprint 共同决定缓存有效性；语言变化不使 facet 失效。
- 当前运行基于 `snapshot_at` 时刻的不可变分析材料；源 JSONL 后续追加只让下一轮 source fingerprint 失配，不阻断当前提交。
- commit 核验分析材料 hash 与 Insights state，使用独占锁、generation CAS、staging、备份、manifest/state/facet hash、回滚和 state-last。
- 锁、Insights state CAS、hash、隐私或事务错误 fail closed；旧报告在新提交成功前保持可用。
