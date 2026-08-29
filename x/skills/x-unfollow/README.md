# x-unfollow v4 架构

v4 维护 following、followers 两张最新原始表和一个派生关系并集。列表页由 X 正常滚动触发请求，扫描器被动解析分页响应，不主动调用私有 GraphQL。

## 插件来源门禁

`run.sh` 首先调用插件根目录的 `scripts/plugin-provenance.cjs`，验证 Claude/Codex manifest 均存在、插件名和版本一致、当前目录确实是 `x/skills/x-unfollow`，再打印版本、宿主、实际路径和内容指纹。旧 `~/.agents/skills/x-unfollow` standalone 副本没有完整插件根，必须在账号配置、运行锁、Playwright、Chrome 和 X 请求之前以 exit 2 拒绝。维护者用 `node x/scripts/plugin-provenance.cjs doctor` 检查双宿主活动版本、缓存内容指纹和 legacy 冲突。

## 浏览器与登录态

`scripts/lib/cdp-browser.cjs` 启动系统 Google Chrome 子进程，以 `--remote-debugging-address=127.0.0.1` 和随机端口交给 Playwright `connectOverCDP`。系统 Chrome user-data 只读，工作流只使用独立 `PROFILE_DIR`；`x-unfollow` 默认 `--headless=new`，只有 `XU_HEADLESS=0` 可见。

账号配置默认位于 `~/.config/x-browser/account.json`。`configure-account.cjs set --email=...` 会先读取系统 Chrome `Local State.profile.info_cache`，要求邮箱唯一匹配一个 profile，再以原子替换和 `0600` 权限保存。优先级为 `X_CHROME_ACCOUNT_EMAIL` → 本地配置；`X_BROWSER_CONFIG_PATH` 可改配置路径。源码和日志不保存完整私人邮箱。

CDP 启动后先通过 Cookie API 检查 `auth_token`、`ct0`。缺失时不访问 X，最多从选中系统 profile 刷新一次 Cookie、IndexedDB、Local/Session Storage、Preferences、Network/WebStorage 等认证数据；History、Cache、Extensions 不复制。刷新用 staging 和临时备份替换，认证失败回滚并退出 12。两个账号 Skill 对同一 canonical `PROFILE_DIR` 共用 `${PROFILE_DIR}.cdp.lock`；只终止本次或失效锁精确记录的子进程，不使用广域进程匹配，也不删除 `Singleton*`。

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

已观察到 Bottom cursor 后，如果连续 8 轮无分页响应且 DOM 无进展，只有网络集合覆盖上一完整基线至少 95%，且未超过“基线 + max(10 条, 2%)”时，扫描才使用 `baseline_coverage_stable` 完成。这不会伪称 cursor 已耗尽；覆盖不足则以 `CURSOR_STALLED_WITH_BOTTOM_CURSOR` 失败，清理 staging 并保留旧 current。

## 关键模块

- `scripts/list-snapshot.cjs`：被动响应监听、页面滚动、URL/异常防护、DOM 兜底。
- `scripts/lib/cdp-browser.cjs`：账号配置、Chrome profile 唯一匹配、认证存储事务刷新、CDP 子进程和跨 Skill profile 锁。
- `scripts/lib/browser-launch.cjs`：扫描和取关共用的 headless 策略；默认无头，只有 `XU_HEADLESS=0` 才进入可见调试，且无头失败不自动回退。
- `scripts/lib/nav-helper.cjs`：只根据导航或相关 X API/Timeline 响应的 HTTP 状态识别 429；通用错误页单独归类。
- `scripts/lib/capture-source.cjs`：网络响应优先与 DOM fallback 数据源选择。
- `scripts/lib/timeline-response.cjs`：TimelineUser 提取、cursor 链、重复页与断链校验。
- `scripts/lib/current-store.cjs`：current/latest 原子写入与旧污染基线重建。
- `scripts/lib/relationship-state.cjs`：关系并集、单次粉丝差异与证据冲突。
- `run.sh`：模式编排、互斥锁、staging 清理和安全退出。

## 离线测试

```bash
node tests/run-tests.cjs
node tests/cdp-browser.test.cjs
node tests/v3-current-state.test.cjs
node tests/v4-pagination.test.cjs
bash -n run.sh
node --check scripts/list-snapshot.cjs
node --check scripts/lib/timeline-response.cjs
node --check scripts/lib/cdp-browser.cjs
```

测试不访问 X，覆盖账号配置与权限、邮箱 0/1/多 profile 匹配、选择性认证复制与失败回滚、CDP 参数和 profile 锁、Cookie 前置门禁、真实 HTTP 429/通用错误页分类、50 用户＋2 cursor、末页、重复页、断链、网络/DOM 隔离、单次粉丝变化报告、污染基线重建、原子晋升和取关安全。
