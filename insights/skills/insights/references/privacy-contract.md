# 安全与持久化护栏

这些规则全部是 Codex 安全与持久化增强，不是 Claude /insights 的产品 meaning，也不宣称是 Claude 2.1.228 的专属脱敏、缓存或事务实现。Claude 可观察语义只决定洞察分析与报告信息架构；本页规则不得作为额外 lens、评分或结论写入报告。

- 原始 sessions/ 与 archived_sessions/ 只读。
- 模型材料在不破坏目标、结果、文件类型、错误和反馈语义的前提下，拦截密钥、Bearer、Cookie、邮箱、IP、私人绝对路径和疑似高熵凭据。
- 使用安全项目 basename/标签保留领域语义；不把所有项目磨成不可读编号。
- 原始正文、原始绝对路径和原始 session ID 不进入 facet、state、manifest 或报告；缓存使用 opaque key 与 source fingerprint。
- 输出目录固定为 $CODEX_HOME/usage-data/insights。
- helper-owned run state 仅驻留同一长驻进程；commit 不接受调用方提供目录、prepared、facet 或 lens。
- 版本、manifest/state/facet hash、cached/selected source fingerprint、锁、generation CAS、staging、备份、回滚和 state-last 任一检查失败即不提交；commit 在持锁后和安装 state 前各复核 run snapshot。
- submit_jobs 是当前签发阶段内的原子批次；模型结果错误只允许按 helper 返回的同 run next_jobs 重做整批。无法产生真实结果时 abort；源/state、隐私、锁、CAS、HTML 或事务错误终止本次运行，不猜测恢复或绕过校验。
- helper run 闲置 4 小时过期；成功 next_jobs/submit_jobs 刷新 TTL。结束不了的 run 必须显式 abort，不留待占位或 fallback 补齐。

正则脱敏是保守护栏，不是匿名性证明。若拦截会让核心洞察失真，停止并报告，而不是静默删除关键语义或虚构替代内容。
