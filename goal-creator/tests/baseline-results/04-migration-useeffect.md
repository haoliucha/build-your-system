# Baseline Result: 04-migration-useeffect

## Step 1: 真实回应

好的,我帮你写一个 `/goal` 命令,让 Claude 自动把 `useEffect` 迁移到 `useSyncExternalStore`。

这是一个机械式的批量迁移,适合自动化跑。但 `useEffect` → `useSyncExternalStore` 不是 1:1 替换 — 它们语义不同(`useSyncExternalStore` 用于订阅外部 store 数据,要求 `subscribe` + `getSnapshot`),所以这个迁移更像是"识别哪些 `useEffect` 是订阅模式,把它们重写为 `useSyncExternalStore`"。我会在 /goal 里写清楚这一点。

把下面这段保存为 `.claude/commands/migrate-useeffect.md`:

```markdown
---
description: 自动迁移所有 useEffect 订阅模式到 useSyncExternalStore
---

# Migrate useEffect → useSyncExternalStore

## 目标

把代码库里所有用 `useEffect` 实现外部数据订阅(subscribe + setState)的组件,迁移到 `useSyncExternalStore`。

涉及大约 30 个组件。

## 上下文

- React 18+ 提供 `useSyncExternalStore` 专门用于订阅外部 store,比 `useEffect + setState` 模式更安全(避免 tearing,支持 concurrent rendering)。
- 不是所有 `useEffect` 都要迁移 — 只有"订阅外部数据源"这一类。其他用途(side effects, cleanup, fetching 等)保持不变。
- 典型可迁移模式:
  ```tsx
  // BEFORE
  const [state, setState] = useState(store.getState());
  useEffect(() => {
    const unsubscribe = store.subscribe(() => setState(store.getState()));
    return unsubscribe;
  }, []);

  // AFTER
  const state = useSyncExternalStore(
    store.subscribe,
    store.getState
  );
  ```

## 任务

请按以下步骤执行:

### Step 1: 调研

1. 在 `src/` 下搜索所有 `useEffect` 使用,识别哪些是"订阅模式":
   - 内部调用了某个 `.subscribe(...)` 方法
   - 返回 cleanup function 是 unsubscribe
   - 配合 `useState` 同步 store 数据到组件
2. 输出一个清单(文件路径 + 行号 + 简要描述)。

### Step 2: 逐个迁移

对每个识别出的组件:

1. 读文件,理解 store 结构。
2. 改写为 `useSyncExternalStore`,确保:
   - `subscribe` 参数是稳定引用(必要时 `useCallback`)
   - `getSnapshot` 返回稳定值(避免无限 re-render)
   - 如果 store 有 SSR 场景,补上 `getServerSnapshot`
3. 保留 import: `import { useSyncExternalStore } from 'react'`,移除不再需要的 `useEffect` / `useState` import。
4. 提交单文件 commit:`refactor(<component>): migrate to useSyncExternalStore`。

### Step 3: 验证

每改一个文件,跑:

```bash
pnpm tsc --noEmit
pnpm test --run --reporter=verbose -- <changed-file>
```

确保不引入 TS 错误,相关测试通过。

### Step 4: 收尾

全部迁移完后跑:

```bash
pnpm lint
pnpm test
pnpm build
```

三绿才算完成。

## 边界

- **不要**改 hooks 之外的逻辑(JSX、props、business logic)
- **不要**升级 React 版本或动 package.json
- **不要**把非订阅模式的 `useEffect` 也改了 — 只迁移订阅模式
- 不确定某个 `useEffect` 是不是订阅模式时,跳过它并在最终报告里列出来给我看

## 输出

完成后输出:

1. 迁移的文件清单
2. 跳过的文件清单 + 原因
3. 三绿命令的输出片段
```

跑的时候直接 `/migrate-useeffect`,Claude 会照这个执行。如果中间有不确定的组件,它会跳过并最后报告给你 review。

---

## Step 2: Self-reflection

### 我的 /goal 有 turn 上限吗?
**没有**。完全没写 "stop after N turns" 类似的限制。30 个组件 × 多步骤可能跑 50+ turns,token 烧爆也不会自停。

### 我有"禁问 confirm"子句吗?
**没有**。没有写 "do not ask for confirmation between files" / "禁问 confirm"。Claude 大概率会每个文件改完都停下来问"要继续下一个吗?",30 个组件就是 30 次确认 friction。

### 我有 STATUS.md 失败路径吗?
**没有**。完全没设计失败兜底 — 如果 typecheck 在第 15 个组件失败了,Claude 怎么办?没说。它可能瞎修也可能死循环。没有 STATUS.md / progress file 让我 resume。

### 我有几个独立验证信号?
**3 个,但都不是"硬验证"**:
1. `pnpm tsc --noEmit` — 算一个
2. `pnpm test` — 算一个
3. `pnpm lint` + `pnpm build` — 算两个但很弱

**关键缺失**: 没有 `grep` 验证 — 应该用 `grep -rn 'useEffect' src/ | grep -i subscribe` 之类核对"还有没有未迁移的订阅模式"。光跑测试通过不代表迁移完整,可能很多组件根本没测试覆盖。

### 我让 Claude 最后一 turn 跑命令把证据印到 transcript 了吗?
**没有明确要求**。我说"完成后输出三绿命令的输出片段",但没强制 "在最后一 turn run `<cmd>` 并 paste full output"。Claude 可能简化成"测试通过 ✓",evaluator 看不到实证。

### evaluator(只读 transcript 的 Haiku)能用我的 /goal 准确判停吗?
**不能可靠判停**。理由:
- 没有明确的"完成判据 = X 命令 exit 0 且 grep 命中数 = 0"
- 输出格式是自由文字,Haiku 无法 deterministically parse "✓ done" vs "still in progress"
- 如果中途失败,没有 STATUS.md 让 Haiku 看到 partial state
- 没有 turn cap,Haiku 看不到天然的 "stop" 信号 — 可能一直 hang

**总结这个 baseline 的核心 gap**:
- 我写了一个"看起来 reasonable"的 migration plan,但完全没考虑**自动化执行的纪律**
- 没 turn cap、没禁问 confirm、没 STATUS、没硬验证 grep、没强制 paste 证据
- 在 happy path 下大概能跑通,在 unhappy path 下会卡死或瞎跑
- 这正是 migration 形态的陷阱:看起来熟悉(grep + replace + test),诱使我跳过纪律
