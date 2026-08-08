# x-unfollow 安全收尾实施计划

> **执行方式：** 当前会话内按顺序执行；每项修改先写失败测试，再做最小实现并回归。

**目标：** 取消 24 小时冷却，只允许一个 x-unfollow 网络流程同时运行；将逐账号验证改成一次 `/following` 拉取后的集合差；完成既有 94 个目标的剩余处理，并同步 Codex、Claude Code 与安装副本。

**安全边界：** 任何 X 网络脚本必须持有活动运行锁；锁只覆盖进程生命周期，正常退出立即释放，异常退出允许自动回收。点击必须绑定目标 handle，明确排除“订阅”，并使用 8–12 秒扫描节奏、45–90 秒取消关注节奏和批次休息。离线测试完成前不访问 X。

---

## 任务 1：建立基线与互斥运行锁

**文件：**
- 修改：`targets/codex/build-your-system-assistant/skills/x-unfollow/tests/run-tests.cjs`
- 新建：`targets/codex/build-your-system-assistant/skills/x-unfollow/scripts/lib/run-lock.cjs`
- 新建：`targets/codex/build-your-system-assistant/skills/x-unfollow/scripts/run-lock.cjs`
- 修改：`targets/codex/build-your-system-assistant/skills/x-unfollow/scripts/lib/rate-gate.cjs`
- 修改：`targets/codex/build-your-system-assistant/skills/x-unfollow/run.sh`
- 删除：`targets/codex/build-your-system-assistant/skills/x-unfollow/scripts/rate-guard.cjs`

- [ ] 写测试：首次 claim 成功、并发 claim 被拒、release 后立即可再次 claim、死进程锁可回收、错误 token 不能释放。
- [ ] 运行测试并确认因缺少新实现而失败。
- [ ] 使用原子目录锁实现 claim/status/release；锁中记录 token、ownerPid、startedAt。
- [ ] `run.sh` 在网络阶段前 claim，并用 trap 在退出/中断时 release。
- [ ] 删除 `FULL_RUN_COOLDOWN_MS`、`network-run-state.json` 及全部 24 小时判断。
- [ ] 回归运行锁与原有测试。

## 任务 2：关注列表批量验证

**文件：**
- 新建：`targets/codex/build-your-system-assistant/skills/x-unfollow/scripts/lib/following-diff.cjs`
- 修改：`targets/codex/build-your-system-assistant/skills/x-unfollow/scripts/verify-unfollow.cjs`
- 修改：`targets/codex/build-your-system-assistant/skills/x-unfollow/scripts/snapshot.cjs`
- 修改：`targets/codex/build-your-system-assistant/skills/x-unfollow/run.sh`
- 修改：`targets/codex/build-your-system-assistant/skills/x-unfollow/tests/run-tests.cjs`

- [ ] 写纯函数测试：大小写归一、重复 handle、removed/remaining、空列表、覆盖率元数据。
- [ ] 运行测试并确认失败。
- [ ] 将 `verify-unfollow.cjs` 改为只读 post-action snapshot，不再逐个打开 profile。
- [ ] `snapshot.cjs` 写入原始覆盖率和最多 100% 的展示覆盖率元数据。
- [ ] `run.sh` 在动作完成后只追加一次 `/following` 扫描，然后执行本地集合差。
- [ ] 删除 verify 的请求上限与节奏配置。

## 任务 3：动作日志可恢复合并

**文件：**
- 新建：`targets/codex/build-your-system-assistant/skills/x-unfollow/scripts/lib/action-log.cjs`
- 修改：`targets/codex/build-your-system-assistant/skills/x-unfollow/scripts/unfollow.cjs`
- 修改：`targets/codex/build-your-system-assistant/skills/x-unfollow/tests/run-tests.cjs`

- [ ] 写测试：同日多次运行保留旧账号、同账号以新结果覆盖、无效旧文件安全降级。
- [ ] 运行测试并确认失败。
- [ ] 每个账号处理后原子写入合并日志，使中断后可继续。
- [ ] 移除 `unfollow_assumed` 和过时 verify flags。

## 任务 4：目标区域判断与 DOM fixture

**文件：**
- 修改：`targets/codex/build-your-system-assistant/skills/x-unfollow/scripts/lib/unfollow-safety.cjs`
- 修改：`targets/codex/build-your-system-assistant/skills/x-unfollow/scripts/unfollow.cjs`
- 新建/修改：`targets/codex/build-your-system-assistant/skills/x-unfollow/tests/fixtures/*.json`
- 修改：`targets/codex/build-your-system-assistant/skills/x-unfollow/tests/run-tests.cjs`

- [ ] 写 fixture：目标 profile 关注了你、页面其他区域出现“关注了你”、订阅按钮、精确/错误 handle 菜单、确认弹窗。
- [ ] 运行测试并确认新增边界失败。
- [ ] 只从目标 profile header 读取 followsYou；任何“订阅”候选继续硬拒绝。
- [ ] 回归所有 fixture。

## 任务 5：双端同步、剩余账号与发布

**文件：**
- 修改：`targets/codex/build-your-system-assistant/skills/x-unfollow/SKILL.md`
- 修改：`targets/codex/build-your-system-assistant/skills/x-unfollow/README.md`
- 修改：`targets/codex/build-your-system-assistant/README.md`
- 修改：`x/.claude-plugin/plugin.json`
- 修改：`targets/codex/build-your-system-assistant/.codex-plugin/plugin.json`
- 修改：`.claude-plugin/marketplace.json`
- 同步：`x/skills/x-unfollow/**`、`~/.agents/skills/x-unfollow/**`、Codex 插件缓存副本

- [ ] 更新技能文档：仅并发互斥、一次列表复核、无 24 小时冷却。
- [ ] 运行同步脚本并对四份技能目录做字节级对比。
- [ ] 运行技能快速校验、单元测试、根级策略测试、shell 语法检查、`git diff --check`。
- [ ] 在持锁且非并发状态下处理 `Pidanksez`、`bvipone`，保持既定低频节奏。
- [ ] 只拉取一次完整关注列表，集合差确认两个账号是否仍存在并写报告。
- [ ] 删除工作区临时诊断脚本，复跑验证。
- [ ] 提交精确范围内的改动；仅在仓库已有可用发布机制时执行已授权发布/安装步骤。
