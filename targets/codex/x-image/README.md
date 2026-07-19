# X Image for Codex

Native Codex plugin for generating complete X article covers and article illustrations. Each requested asset uses one built-in ImageGen call, retains the original output, and receives a read-only QA decision.

## Install locally

```bash
zsh scripts/install-local-plugin.sh
```

The installer links the source under `~/plugins/x-image`, updates the personal Codex marketplace entry, registers and enables the plugin with Codex, and builds self-contained caches at:

```text
~/.codex/plugins/cache/local-build-your-system/x-image/0.1.0
~/.codex/plugins/cache/local-build-your-system/x-image/local
```

Start a new Codex task after installation so the skill index refreshes.

## Example requests

```text
给 article.md 生成一张 X 封面
为 article.md 生成一张 3:2 正文解释图
根据 data.md 生成 16:9 数据型文章头图
Create two consistent article illustrations from article.md
```

If only a path is supplied, the default is one cover. Explicit intent, count, ratio, style, and destination override their corresponding defaults.

## Boundaries

- One complete generation call per asset.
- No automatic retry or image modification.
- Existing files receive versioned sibling names.
- No publishing, uploading, article editing, or X account action.
