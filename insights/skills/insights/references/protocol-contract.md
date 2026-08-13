# Runner 契约（0.3）

## 所有权

`scripts/runner.py` 是唯一调度器。主 Agent 不读取 Prompt、不生成模型 JSON、不操作 job ID。Runner 负责会话发现、模型分层、SQLite 队列、校验、聚合、报告和原子提交。

## 启动

```bash
python3 -u "$INSIGHTS_SKILL_DIR/scripts/runner.py" \
  --max-new-sessions 200 \
  --language zh-CN
```

参数默认即为 200 与 zh-CN。不得通过 PTY JSONL、`next_jobs`、`read_job` 或 `submit_jobs` 驱动；这些接口在 0.3 已删除。Runner 前台运行，不使用项目或 `/tmp` 中继，不设置 timeout 或 TTL。

若 `runs/*/run.sqlite3` 存在 running/paused 运行且调用方没有选择，Runner 以退出码 2 返回：

```json
{"status":"resume_choice_required","unfinished_runs":["<run-id>"],"message":"发现未完成的兼容运行；请让用户选择 --resume <run-id> 或 --new。"}
```

新运行在清单阶段读取源会话一次，把确定性 meta、标准化/脱敏后的 Facet 材料、选中 session key、source fingerprint 与 inventory 冻结到 `run.sqlite3`，并记录内容 hash 与 `snapshot_at`。快照不包含原始路径或未脱敏正文。

恢复直接读取该快照，不重新扫描活跃 JSONL，也不要求十几分钟内源文件保持不变。源文件在快照后追加不会改变当前报告；下一轮发现新的 source fingerprint 时自然使对应 facet 缓存失效。恢复仍核对语言、快照 hash 与已提交 Insights state hash；不一致则 fail closed。

## 队列与模型

SQLite 使用 WAL、FULL synchronous 和单写者事务。Job 状态只有 `queued/running/succeeded/skipped`。进程崩溃或主动暂停后，running 重排 queued；succeeded 保留。成功 commit 后清除 SQLite 中的分析材料快照，只保留运行元数据与结果状态。

| Job | 模型 | effort | 失败策略 |
|---|---|---:|---|
| chunk_summary | gpt-5.6-luna | low | 两次额外重试后使用块前 2,000 字符 |
| session_facet | gpt-5.6-terra | medium | 两次额外重试后 skipped |
| 7 lenses | gpt-5.6-sol | high | 两次额外重试后省略并记录 concern |
| At-a-Glance | gpt-5.6-sol | high | 两次额外重试后降级为 concern |

每个 `codex exec` 使用 stdin Prompt、stdout JSONL、stderr 并发排空、`--ephemeral --json --output-schema --output-last-message --ignore-user-config --ignore-rules --sandbox read-only`。Fast 通过 `service_tier="fast"` 开启；Shell、Web、MCP、Apps、浏览器、Computer Use、图片和多代理关闭。隔离 HOME/CODEX_HOME 只桥接现有登录凭据，不加载个人 Skill、插件或项目规则。

进程池从 6 开始；连续 20 个成功 Job 加 1，最高 12。显式限流暂停新派发，按 CLI/服务端信号等待并回到 6；限流不计重试。没有 Runner timeout、Job timeout、停滞终止或运行 TTL。

## 进度

冻结工作量：

- 清单 5
- chunk 每个 2
- facet 每个 5
- lens 每个 8
- At-a-Glance 5
- render 2
- commit 1

每 60 秒心跳、每 5 分钟完整仪表盘。任何输出都同时显示全部阶段、总体百分比、语义覆盖、并发、吞吐、P50/P90 与 ETA；未来阶段不得隐藏。单 Job 10 分钟无事件只显示告警。

## 暂停与提交

SIGINT/SIGTERM 触发：立即终止所有在途 `codex exec`，删除 `.partial`，running 改 queued，已成功结果保留。恢复不重复成功 Job。

只有所有终态结果完成后才渲染。commit 不重新读取源 JSONL，只核验 helper 所有的分析快照 hash 与 Insights state snapshot；随后使用锁、generation CAS、staging、备份、manifest hash、回滚和 state-last。新报告提交成功后才隔离并删除旧引擎 facet/state/manifest；旧 report 在此之前不变。

完成对象必须含 report、timestamp report、manifest、coverage 与性能数据。覆盖口径：

```text
eligible = analyzed + skipped + remaining
selected = succeeded + skipped
```
