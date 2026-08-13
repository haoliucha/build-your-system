# 隐私契约

原始 `sessions/` 与 `archived_sessions/` 只读。模型只能接收 helper 已脱敏的 work item；原始正文、原始路径、原始 session ID 不进入 facet、state、manifest 或报告。

禁止持久化或回显密钥、Bearer、Cookie、邮箱、IP、私人绝对路径和疑似高熵凭据。命中检测时必须 fail closed，不得降低规则、手工绕过或复制命中值解释错误。输出目录只允许 `$CODEX_HOME/usage-data/insights`，提交只能通过同一长驻 helper 的一次性 `run_id`。
