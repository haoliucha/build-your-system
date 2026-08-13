# 长驻 JSONL 协议契约

本页逐字段记录当前 `scripts/insights.py` 的 protocol_version 3 调用面。模型分析只能填 helper 发出的 job；会话发现、helper-owned 字段、聚合、报告和持久化均由同一个 helper 进程控制。

## 启动与传输

令 `INSIGHTS_SKILL_DIR` 为已加载 `SKILL.md` 的目录，启动且不传任何参数：

```sh
python3 "$INSIGHTS_SKILL_DIR/scripts/insights.py"
```

不要使用 `--request`，因为它每次只处理一个无状态请求，不能保留 run。stdin 每行一个 UTF-8 JSON 对象；stdout 对应返回一行 JSON 并立即 flush。整个运行只由主代理持有该进程。

生产 JSONL 模式在进程启动时绑定 `$CODEX_HOME`（未设置时为 `~/.codex`）；prepare 不得改指向其他目录，`output_dir` 只能等于该 home 下的 `usage-data/insights`。成功响应统一为 `{"ok":true,"result":{...}}`。失败响应有两种 next：

```json
{"ok":false,"error":{"type":"<exception class>","message":"<single reason>","next":{"op":"next_jobs","run_id":"<still-live run_id>"}}}
{"ok":false,"error":{"type":"<exception class>","message":"<single reason>","next":{"op":"prepare"}}}
```

第一种表示 helper 仍持有该 run；失败的 submit_jobs 整批零接受。只有能从同一批已签发 jobs 重新生成真实合规对象时，才发送该 next 并重做整批。否则发送 `{"op":"abort","run_id":"<run_id>"}` 后停止。第二种表示没有可恢复 run；不自动 prepare。非 JSON、EOF、缺字段、源/state 漂移、隐私、锁/CAS/HTML/事务完整性错误也停止，不猜测恢复。

run 的闲置 TTL 为 4 小时；成功的 next_jobs 或 submit_jobs 会刷新 TTL。每次请求前 helper 清理到期 run；过期后 run_id 等同未知。无需继续时显式 abort：

```json
{"op":"abort","run_id":"<run_id>"}
{"ok":true,"result":{"run_id":"<run_id>","aborted":true,"next":{"op":"prepare"}}}
```

abort 的 next 不表示自动重启；本次失败仍应结束。

## Prepare、选择与覆盖量

请求只传用户明确给出的参数；正常运行不传 `codex_home`、`output_dir` 或 `current_thread_id`，helper 使用进程绑定的 home、环境中的当前任务 ID 和固定输出目录：

```json
{"op":"prepare","max_new_sessions":10,"language":"zh-CN"}
```

响应形状：

```json
{"ok":true,"result":{"run_id":"<32 hex>","language":"zh-CN","stats":{"physical_source_files":120,"parsed_source_files":119,"parse_failed":1,"logical_sessions":116,"duplicate_source_files":3,"logical_id_collisions":0,"eligible":100,"excluded":16,"excluded_current":1,"excluded_insights":2,"excluded_short_messages":8,"excluded_short_duration":5,"cached":84,"selected":10,"remaining":6,"historical_cached":0},"legacy_cache_detected":false,"next":{"op":"next_jobs","run_id":"<same run_id>"}}}
```

`MAX_NEW_SESSIONS` 是 0–200 的整数。helper 先去重、排除无效会话，再把 eligible 会话按 `updated_at` 降序排列；相同时间按 opaque session key 降序。缓存只有在分析版本链有效、session/source fingerprint 匹配、facet 文件路径与内容均通过校验时才复用。随后从未缓存队列选前 N 条。

覆盖恒等式只使用当前发现的 eligible 会话：

```text
eligible = cached + selected + remaining
has_unprocessed_sessions = (remaining > 0)
```

`historical_cached` 是 protocol_version 3 的兼容统计位，当前固定为 0。只有本次仍被发现、通过 manifest/state/facet 完整性检查且 source fingerprint 匹配的缓存会话才进入 cached、聚合和 facet_count；已不在当前来源中的旧 state 条目不进入报告。

## next 与 job envelope

prepare 或 submit_jobs 成功后，原样发送 `result.next`；它会是 next_jobs：

```json
{"op":"next_jobs","run_id":"<run_id>"}
```

next_jobs 成功响应的 `result` 固定含 `run_id`、`stage`、`jobs`、`next`。未完成时：

```json
{"ok":true,"result":{"run_id":"<run_id>","stage":"session_facets","jobs":[{"job_id":"job-<20 hex>","kind":"session_facet","session_key":"session-<16 hex>","material":"<helper supplied material>","prompt":"<helper supplied prompt>","schema":{"required":["underlying_goal","goal_categories","outcome","user_satisfaction_counts","claude_helpfulness","session_type","friction_counts","friction_detail","primary_success","brief_summary"],"optional":["evidence_anchors","user_instructions_to_codex"]}}],"next":{"op":"submit_jobs","run_id":"<run_id>","results":"<job results>"}}}
```

`results` 的字符串值是待替换哨兵，不是可提交值。只把它替换为数组；其他字段原样保留。每项必须精确只有 `job_id` 与 `result`，且 `result` 是 JSON 对象，不是包含 JSON 的字符串：

```json
{"op":"submit_jobs","run_id":"<run_id>","results":[{"job_id":"job-<20 hex>","result":{"underlying_goal":"修复缓存事务并验证回滚","goal_categories":{"debugging":1,"testing":1},"outcome":"fully_achieved","user_satisfaction_counts":{"satisfied":1},"claude_helpfulness":"very_helpful","session_type":"single_task","friction_counts":{},"friction_detail":"","primary_success":"good_debugging","brief_summary":"修复缓存事务并通过回归测试。","user_instructions_to_codex":["先复现再修复"],"evidence_anchors":["回归与失败注入通过"]}}]}
```

成功提交返回接受数和下一次 next_jobs：

```json
{"ok":true,"result":{"run_id":"<run_id>","accepted":1,"next":{"op":"next_jobs","run_id":"<run_id>"}}}
```

四种 job envelope：

| kind | helper 字段 | result 对象 |
|---|---|---|
| chunk_summary | job_id、kind、session_key、chunk_index、chunk_total、prompt、schema | 精确 `{"summary":"非空摘要"}`；摘要不超过 8,000 字符 |
| session_facet | job_id、kind、session_key、material、prompt、schema | schema 的 required 字段，加零个或多个 optional 字段；不得含 helper-owned 字段 |
| lens | job_id、kind、lens_id、prompt、schema | 精确匹配该 lens JSON Schema |
| at_a_glance | job_id、kind、prompt、schema | 精确四字段：whats_working、whats_hindering、quick_wins、ambitious_workflows |

每个 job 只使用其自身 prompt/schema；prompt 已包含要求的输出语言。session_facet envelope 的 `prompt` 已完整内嵌同 envelope 的 `material`；`material` 仅是可审计副本，不是第二份模型输入，不得另行拼接或补入其他上下文。若 prompt 与 material 不一致或 prompt 未完整包含 material，abort 并停止。helper 每次最多发 50 个 job：chunk_summary 与 session_facet 使用 `[:50]`，lenses 固定 7 个，at_a_glance 固定 1 个。可提交当前批次的非空子集，随后再次请求 next_jobs；submit_jobs 只接受当前阶段签发的 job_id，不能猜后续阶段 ID。整批先完成 schema/隐私/阶段校验，再一次性写入内存；任何一项失败则整批零接受，可按 error.next 取回同一批后完整重做。

## 阶段与最小闭环

实际 job 内容由会话决定；下面的 `JOBS_*` 表示上一条 next_jobs 响应中的真实 envelope，不是允许提交的占位结果。状态机闭环严格为：

```text
C→H {"op":"prepare","max_new_sessions":10,"language":"zh-CN"}
H→C ok/result.next = {"op":"next_jobs","run_id":"RID"}
C→H {"op":"next_jobs","run_id":"RID"}
H→C stage=chunk_summaries 或 session_facets，jobs=JOBS_1，next=submit_jobs sentinel
C→H {"op":"submit_jobs","run_id":"RID","results":[每个 JOBS_1 的真实对象结果]}
H→C ok/result.next = next_jobs
       重复 next_jobs→submit_jobs，直到所有 chunk 完成，再完成所有 facet
H→C stage=lenses，jobs=7 个异构 lens
C→H submit_jobs（每个 lens 的真实对象结果）
H→C ok/result.next = next_jobs
C→H next_jobs
H→C stage=at_a_glance，jobs=1
C→H submit_jobs（四字段真实对象结果）
H→C ok/result.next = next_jobs
C→H next_jobs
H→C stage=ready_to_commit，jobs=[]，preview_html=<完整 HTML>，next={"op":"commit","run_id":"RID"}
C→H {"op":"commit","run_id":"RID"}
H→C ok/result={generation,report_path,timestamp_report_path,manifest_path,facet_count,coverage}
```

ready_to_commit 的精确响应形状：

```json
{"ok":true,"result":{"run_id":"<run_id>","stage":"ready_to_commit","jobs":[],"preview_html":"<!doctype html>...","next":{"op":"commit","run_id":"<run_id>"}}}
```

`action` 是 `op` 的兼容别名；两者同时出现时必须相等。标准路径只使用 ready.next 中的 `op`。commit 请求只允许 op/action、run_id 和可选的匹配 language；正常情况原样发送 ready 响应中的 next，不附加 facet、lens、prepared、coverage、output_dir 或 preview：

```json
{"op":"commit","run_id":"<run_id>"}
```

成功响应字段：

```json
{"ok":true,"result":{"generation":7,"report_path":"<fixed output>/report.html","timestamp_report_path":"<fixed output>/report-20260813T120000Z.html","manifest_path":"<fixed output>/manifest.json","facet_count":94,"coverage":{"eligible":100,"cached":84,"selected":10,"remaining":6,"historical_cached":0}}}
```

实际 coverage 还保留 prepare stats 的其余字段。commit 成功后 run_id 被消费；最终路径、计数和 coverage 一律从此响应读取，不自行拼接。

prepare 对 on-disk state 做前后两次 canonical snapshot 检查，并保存 state hash 及当前发现的所有 eligible 来源 fingerprint。commit 持锁后复核一次，并在安装 state.json 前再次复核；任一来源或 state 即使 generation 未变但内容变化，也回滚且不提交。manifest 记录 state_sha256，并在 files 中覆盖 state.json、latest/timestamp reports 和 state 引用的每一个 facet；任一缺失、越界、hash、版本或 facet 内容不匹配都把旧缓存视为 legacy，不复用。

latest 与 timestamp 报告由同一 `preview_html` 字节写入，manifest 中两者的 SHA-256 必须相同；这项文件哈希相等是报告副本恒等性，不能替代上面的覆盖恒等式。
