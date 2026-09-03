---
name: d-mine
description: 从近期 Inbox、记忆日志、精华模式和外部剪藏中挖掘有短视频潜力的真实素材。
---

> 宿主适配契约见 vault-structure/references/host-adaptation.md；当前目录即 Vault 根目录。

# 选题挖矿

当前目录即 Vault 根目录。默认扫描全部范围；也可指定 `inbox`、`digest`、`patterns` 或 `clippings`。

## 扫描源

- `00-Inbox/` 近 30 天日记与捕获；
- `60-Memory/patterns-digest.md`，优先读取 `status: active` 条目；
- `60-Memory/patterns.md`；
- 根目录 `Clippings/`。

扫描 digest 时把 `predicts` 作为可验证选题线索，不把精华模式当作事实本身。

## 筛选与去重

优先具体经历、数字、转折、反常识、问题和可复述的工作摩擦。记录每条素材的来源文件和原文依据。
去重仍扫描 `20-Areas/media/topics/`，排除已有相似选题和已标记使用过的内容。

## 输出

```markdown
## 选题挖矿报告

扫描范围：{范围}
扫描文件：{N}
发现素材：{M}

### 高潜力素材

#### {标题}
- 来源：{文件}
- 依据：{原文或事实摘要}
- 选题潜力：{理由}
- 建议角度：{角度}
- 可验证问题：{问题}
```

只报告有来源的素材，不把推测写成用户经历。

## 交接

报告结束后交接到 media 插件的 `m-topic`（`/media:m-topic`）评估选题。若 media 未安装，提示安装后停止，不引用已退役工作流。
