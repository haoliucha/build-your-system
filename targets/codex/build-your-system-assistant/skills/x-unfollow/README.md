# x-unfollow v3 架构

v3 是破坏性状态模型升级：不再保存日期快照，只维护 following、followers 两张最新原始表和一个派生关系并集。

## 数据流

```text
旧 current ───────┐
                  ├─ 本地差异/关系合并 ── latest reports ── 原子替换 current
新 .staging/run ──┘                         │
        │                                  └─ 成功后删除 staging
        └─ URL/覆盖率/数量/异常失败 ────────── 保留旧 current
```

| 模式 | 扫描 | 结果 |
|---|---|---|
| `report` | following | latest non-recip + following changes |
| `followers-report` | followers | latest follower changes；首跑只建基线 |
| `relationships-report` | following → followers | coherent 完整并集 |
| `unfollow` | following + 必要动作 + following | 显式取关与本地批量复核 |

## 扫描状态机

```text
navigate target
  ├─ URL 不精确 / 顶层跳转 → PAGE_DRIFT(15)
  └─ 每轮 collect
       ├─ unique 下降或超过 header+容差 → 17
       ├─ unique 增长 → stable=0
       ├─ unique 不变 → stable++（忽略 scrollHeight）
       ├─ stable=8 & coverage≥95% → stable stop
       └─ stable=8 & coverage<95% → 最多恢复2次，否则17
```

负向集合差额外要求 `stable stop && coverage>=99%`。最大轮和停止轮之后不再执行 60 秒休息，元数据中的 `rounds` 是实际执行轮数，不偏一。

## 关键模块

- `run.sh`：四模式编排、互斥锁、staging 清理。
- `scripts/list-snapshot.cjs`：following/followers 通用扫描器、页面漂移与覆盖率防护。
- `scripts/promote-current.cjs`：读取 staging 并晋升 current。
- `scripts/lib/current-store.cjs`：原子文件替换、latest reports。
- `scripts/lib/relationship-state.cjs`：并集、连续未回关压缩、差异与证据冲突。
- `scripts/lib/list-scan-state.cjs`：URL、计数、稳定停止与休息边界纯逻辑。
- `scripts/classify.cjs`：只读 current relationship 的未回关分类。
- `scripts/profile-counts.cjs`：仅 unfollow 流程按需刷新，并把最新计数嵌回关系行。
- `scripts/unfollow.cjs`：精确语义控件取关，拒绝“订阅”按钮。
- `scripts/verify-unfollow.cjs`：只读 current/following 的本地集合差。

## 离线测试

```bash
node tests/run-tests.cjs
node tests/v3-current-state.test.cjs
bash -n run.sh
node --check scripts/list-snapshot.cjs
```

测试覆盖两表与并集、关系类型、大小写去重、只留最新 current/latest、非连续日期重置、页面 URL 漂移、`scrollHeight` 不影响稳定停止、数量异常、低覆盖、证据冲突、最大轮休息边界、中止清理和并发锁。测试不访问 X。
