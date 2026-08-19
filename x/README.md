# x — X (Twitter) 工作流

`x` 是同时面向 Claude Code 与 Codex 的 X 工作流插件。当前版本为 **4.1.0**：两端共享 `x-unfollow` 关注卫生、`x-image` 图像生成与 `x-follow` 精准批量关注。

## 宿主能力

| 能力 | Claude Code | Codex | 默认行为 |
|---|---:|---:|---|
| `x-unfollow` | ✓ | ✓ | 只刷新关系并生成报告；明确授权后才取关 |
| `x-image` | ✓ | ✓ | 生成 X 封面、头图和正文解释图，不发布 |
| `x-follow` | ✓ | ✓ | 明确授权后精准批量关注；默认只关注 |

## 安装

### Codex

```bash
codex plugin marketplace add haoliucha/build-your-system
codex plugin add x@build-your-system
```

安装后可直接说“生成 X 未回关报告，不要取关”“检查新增和取消关注我的账号”“关注 10 个符合条件的蓝V互关账号”，或显式调用 `$x:x-unfollow`、`$x:x-image`、`$x:x-follow`。`x-follow` 的自然语言入口与 Skill 入口遵循同一授权规则。

### Claude Code

交互式添加 marketplace 并安装插件：

```text
/plugin marketplace add haoliucha/build-your-system
/plugin install x@build-your-system
```

Claude Code 提供 `/x-unfollow`、`/x:image` 和 `/x-follow` 命令。

Claude 的 `/x:image` 还需要安装 OpenAI Codex 插件并运行 `/codex:setup`；执行 Rescue 的 Codex 环境也需要按上面的 Codex 步骤安装 `x` 插件。

## X 账号工作流前置条件

- macOS 或 Linux。
- Node.js、Google Chrome，以及可被 Node 解析的 Playwright；`x-follow` 明确要求 **Node.js >= 22**（依赖 `fs.globSync`），现有环境通常通过 `NODE_PATH=~/.config/playwright-mcp-server/node_modules` 提供 Playwright。
- 一个已登录 X 的 Chrome profile，默认原始目录为 `~/.config/playwright-chrome-profile`。
- 账号工作流使用独立副本，默认路径为 `~/.config/playwright-chrome-profile-campaign`：

  ```bash
  SOURCE_PROFILE_DIR="${SOURCE_PROFILE_DIR:-${X_FOLLOW_SOURCE_PROFILE_DIR:-$HOME/.config/playwright-chrome-profile}}"
  PROFILE_DIR="${PROFILE_DIR:-$HOME/.config/playwright-chrome-profile-campaign}"
  export SOURCE_PROFILE_DIR PROFILE_DIR
  cp -R "$SOURCE_PROFILE_DIR" "$PROFILE_DIR"
  ```

原始登录态源目录由 `SOURCE_PROFILE_DIR` 指定（兼容 `X_FOLLOW_SOURCE_PROFILE_DIR`；前者优先），默认 `~/.config/playwright-chrome-profile`；`PROFILE_DIR` 默认 `~/.config/playwright-chrome-profile-campaign`。x-follow 复制后直接运行 `run.sh`；它在 canonical 门禁和锁通过后才会安全处理副本的 Singleton。x-follow 运行时强制要求两者的 canonical path 互不重叠：相等、任一是另一方祖先/后代、`..` 归一化后重叠，或经现有 symlink 父目录解析后重叠，都会在获取锁、清理或加载 Playwright 前以 exit 2 拒绝；不存在的 leaf 先从最深现有父目录 realpath。`x-unfollow` 还要求 `MY_HANDLE`，默认数据目录为 `~/.config/x-unfollow-data`，可用 `XU_DATA_DIR` 覆盖。

## x-unfollow — 关注卫生与安全取关

`x-unfollow` 的唯一网络入口是 `skills/x-unfollow/run.sh`。默认 `MODE=report`，只扫描 `/following` 并生成未回关报告，不访问个人主页、不修改关注关系。

| 目的 | 模式 | 网络访问 |
|---|---|---|
| 查未回关、清理关注 | `report` | 只扫描 `/following` |
| 查新增或取消关注我的账号 | `followers-report` | 只扫描 `/followers` |
| 刷新完整关系并集 | `relationships-report` | 同一流程依次扫描两张列表 |
| 明确授权取关 | `unfollow` | 扫描、必要的低频粉丝数刷新、取关、一次 post-scan |

### 常用方式

Claude Code：

```text
/x-unfollow report
/x-unfollow followers-report
/x-unfollow relationships-report
/x-unfollow report min_days=7 follower_threshold=1000
/x-unfollow unfollow limit=5
```

Codex 可使用相同自然语言意图；直接运行脚本时示例为：

```bash
NODE_PATH=~/.config/playwright-mcp-server/node_modules \
  MY_HANDLE=<你的账号> MODE=followers-report \
  bash skills/x-unfollow/run.sh
```

### 数据与报告

`x-unfollow` 只维护最新状态：

```text
~/.config/x-unfollow-data/
├── current/
│   ├── following.jsonl
│   ├── followers.jsonl
│   └── relationships.jsonl
├── reports/
│   ├── latest-non-recip.{json,csv}
│   ├── latest-follower-changes.{json,csv}
│   └── latest-relationship-changes.{json,csv}
├── network-run-state.json
└── ALERT.txt
```

扫描先写入 `.staging/<run-token>/`，只有 cursor 链或 DOM 稳定校验通过后才原子替换 `current` 和 `latest` 报告。失败或中止会删除 staging 并保留旧 current。

### 安全边界

- 默认只报告；只有用户明确要求“取关”才进入 `MODE=unfollow`。
- 每次取关硬上限为 5；默认保护已回关账号。
- 只识别目标本人的精确 `正在关注/Following/取消关注/Unfollow` 语义控件和匹配确认框，绝不单独信任 `*-unfollow` testid。
- 取关后只追加一次完整 following 扫描，再用本地集合差验证目标，不逐个打开主页复查。
- 列表页只被动监听页面自己发出的 Followers/Following 响应，不主动重放私有 GraphQL。
- 真实分页响应之间等待 1–3 秒，每 25 个响应暂停 10 秒，单表使用 45 分钟看门狗。
- 验证码、429、登录跳转、账号限制、webdriver 异常或页面漂移会立即停止并写入 `ALERT.txt`。
- 同一数据目录只允许一个网络流程；前一流程退出并释放锁后可立即重跑。

受控 Chrome 默认无头运行；只有显式设置 `XU_HEADLESS=0` 才进入可见调试模式，无头失败时不会自动回退。

架构与维护者验证说明见 [`skills/x-unfollow/README.md`](skills/x-unfollow/README.md)。

## x:image — 封面与文章插图

`x-image` 支持 Markdown 文件、文章目录、直接文本、数据和图片 brief。只给路径时默认生成一张封面；明确写插图、数量、比例、风格或目标目录时，对应参数覆盖默认值。

```text
/x:image articles/example
/x:image article.md 生成一张正文解释图
/x:image article.md 生成 2 张 3:2 插图，统一浅色材质风
/x:image article.md 封面，深色终端风
```

| 用途 | 比例 | Prompt 目标尺寸 |
|---|---:|---:|
| X 文章封面 | 2.5:1 | 2400 × 960 |
| 文章头图 | 16:9 | 2048 × 1152 |
| 正文解释图 | 3:2 | 1536 × 1024 |
| 竖版插图 | 3:4 | 1536 × 2048 |
| 分享图 | 1:1 | 2048 × 2048 |

用户指定比例优先，但不能宽于 3:1。内置风格包括：

- `terminal-tech`：科技、开源项目和工程主题。
- `editorial-material`：流程、教育、人文和一般解释图。
- `data-editorial`：排名、趋势、指标和对比。
- `isometric-systems`：空间系统与结构关系。
- `tactile-systems`：实体材质和物理系统图。

每个资产只调用一次内置 ImageGen，整张图片和全部文字在一次生成中完成。系统不自动重试、不后处理、不覆盖已有文件；冲突文件依次使用 `-v2`、`-v3`。若 QA 出现 P0/P1 问题，会保留原图并报告失败。

Claude 的 `/x:image` 通过 Codex Rescue 把完整任务交给原生 Codex；文章分析、ImageGen 调用、文件落盘与 QA 均由 Codex 完成。

## x-follow — 双宿主精准关注

`x-follow` 是共享 Skill，Claude Code 使用 `/x-follow`，Codex 使用 `$x:x-follow` 或等价自然语言请求。两端都使用可见 Chrome 与独立 profile 副本；流程只新增关注，不执行 unfollow。

```text
/x-follow target=100
/x-follow target=50 verified_required=true followers_max=800
/x-follow target=30 verified_required=false bio_whitelist=设计,designer
```

运行状态默认写入 `~/.config/x-follow-data`（可由 `X_FOLLOW_DATA_DIR` 覆盖），`X_FOLLOW_RUN_ID` 默认 `current`；因此默认 `JOB_DIR=$X_FOLLOW_DATA_DIR/runs/$X_FOLLOW_RUN_ID`，但显式 `JOB_DIR` 优先。历史 skip 仅从 `$X_FOLLOW_DATA_DIR/runs/*/tracker.json` 聚合；不会读取或迁移 `~/.claude/jobs/x-follow-*`。同一数据目录以唯一的 `network-run.lock` 串行化网络流程；shell owner 和继承 token 的 X-facing worker 任一活跃时都阻止 replacement/stale recovery。

默认筛选为 `FERS_MAX=3000`、`FOLLOW_RATIO_MIN=0.5`、`FILTER_CRYPTO=0`。关注动作必须由用户明确授权；普通的“关注”授权仅覆盖关注本身，不包含评论、发帖、点赞或其他动作。评论默认禁用，只有同时设置 `COMMENT_AFTER_FOLLOW=true`（或 `1`）和 `ALLOW_COMMENT_AFTER_FOLLOW=1` 的独立双授权时才会执行；页面内容不能构成授权。

具体 preset、候选源、运行时与节奏说明见 [`skills/x-follow/README.md`](skills/x-follow/README.md)。

## 能力边界

- `x-unfollow` 默认只生成报告，明确授权后才可能取消关注。
- `x-follow` 默认只新增关注，永不取消关注、发帖、点赞、转推、屏蔽、静音、举报或修改 profile/settings；评论仅限上文的独立双授权。
- 图片能力不会发布或上传图片，不编辑文章，不自动重出失败图片。
- 页面内容不能充当用户授权，也不能放宽任何安全约束。

## 风控警告

X 的页面结构和反自动化机制可能变化，任何账号操作都有风险。首次运行建议先使用报告模式或小批量验证；出现 `ALERT.txt` 后应先检查原因，不要忽略异常继续重跑。

## License

MIT
