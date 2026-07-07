---
description: "一键给 X 文章生成 2.5:1 封面:读文章蒸馏画面 prompt → codex imagegen(gpt-image-2)整张直出(含中文文字)→ 比例门禁 + 375px 缩略图 + QC。详见 skill x-cover"
argument-hint: "<文章.md 或文章目录> [风格/版式备注]"
---

# /x:cover — X 文章封面一键生成

**$ARGUMENTS**

## 执行流程

1. **激活 skill** `x-cover`,把上面的参数透传给它。
2. **定位文章**:md 文件 → 其所在目录为文章目录;目录 → 优先 publish.md/draft.md;无参数 → 从会话上下文推断,推不出才问。
3. **蒸馏画面 prompt**(skill 内部):主标题 ≤7 字 + 副标 + 主数字带单位 + 单一图形钩子 + 版式(8 类速查)+ 配色(用户备注优先)。**prompt 只写画面内容,纪律句由脚本注入。**
4. **生成**:`cover-gen.sh gen`(codex headless 直出 2.5:1,2-5 分钟)→ 自动门禁/缩略图/留档。
5. **QC**:Read thumb-375.png 逐字核对(生成有方差);硬伤重跑一次,微瑕如实报告。
6. **交付**:cover.png 路径 + QC 结论 + 提醒"X 上传后点『应用』"。

## 常用用法

| 场景 | 命令 |
|---|---|
| 给文章目录出封面 | `/x:cover articles/2026-06-12-fanqiang` |
| 给单个 md 出封面 | `/x:cover ~/notes/my-post.md` |
| 指定风格/版式 | `/x:cover draft.md 暗色玻璃拟态,用对比表版式` |
| 当前正在写的文章 | `/x:cover` |

## 安全保证

skill 内部强制护栏:
- **绝不发布/上传**,只产出本地图片(cover.png + thumb-375.png,旧封面自动留档)
- codex 用量上限 → 立即 STOP 报告,不空转烧配额;整体失败最多重试 1 次
- headless 不可用 → 给出桌面 app 手动兜底(`cover-gen.sh from`)指引
