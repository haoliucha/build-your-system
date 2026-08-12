# x-unfollow v4 架构

v4 维护 following、followers 两张最新原始表和一个派生关系并集。列表页由 X 正常滚动触发请求，扫描器被动解析分页响应，不主动调用私有 GraphQL。

## 数据流

```text
X 列表页 ──页面请求──> Followers / Following 响应
   │                         │
   └─ 主列表 DOM 兜底         ├─ 50 个 TimelineUser → handle/name/关系证据
                             └─ Bottom cursor → 分页连续性/末页证据
                                      │
旧 current ────────────────────────────┼─ 本地一次差异报告
新 .staging/run ───────────────────────┘
                                      └─ 校验成功后原子晋升 current/latest
```

主路径以无 Bottom cursor，或同 cursor 连续两次无新增结束；响应完全不可见时才用主列表 DOM 稳定到底。网络响应一旦出现，最终账号只取响应集合，不合并 DOM。分页间隔 1–3 秒，每 25 个真实响应暂停 10 秒，总时长看门狗为 45 分钟。

## 关键模块

- `scripts/list-snapshot.cjs`：被动响应监听、页面滚动、URL/异常防护、DOM 兜底。
- `scripts/lib/browser-launch.cjs`：扫描和取关共用的 Chrome 启动参数；默认无头，只有 `XU_HEADLESS=0` 才进入可见调试，且无头失败不自动回退。
- `scripts/lib/capture-source.cjs`：网络响应优先与 DOM fallback 数据源选择。
- `scripts/lib/timeline-response.cjs`：TimelineUser 提取、cursor 链、重复页与断链校验。
- `scripts/lib/current-store.cjs`：current/latest 原子写入与旧污染基线重建。
- `scripts/lib/relationship-state.cjs`：关系并集、单次粉丝差异与证据冲突。
- `run.sh`：模式编排、互斥锁、staging 清理和安全退出。

## 离线测试

```bash
node tests/run-tests.cjs
node tests/v3-current-state.test.cjs
node tests/v4-pagination.test.cjs
bash -n run.sh
node --check scripts/list-snapshot.cjs
node --check scripts/lib/timeline-response.cjs
```

测试不访问 X，覆盖50用户＋2 cursor、末页、重复页、断链、响应错误、网络/DOM 隔离、单次粉丝变化报告、污染基线重建、原子晋升和取关安全。
