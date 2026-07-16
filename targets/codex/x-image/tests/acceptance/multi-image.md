# AC-07 — Two Consistent Illustrations

Status: NOT RUN

Codex task or thread: [PENDING]

Input fixture: `targets/codex/x-image/tests/fixtures/explainer-article.md`

Exact Codex prompt:

```text
Use the native x-image skill. Read targets/codex/x-image/tests/fixtures/explainer-article.md and generate exactly two 3:2 article illustrations with a locked editorial-material style. Asset 1 is the exact four-step pipeline「捕获」「澄清」「连接」「表达」. Asset 2 is a layer-stack explanation showing raw fragments becoming a coherent article, with no visible text. Save original outputs under targets/codex/x-image/tests/acceptance/output/ac-07-illustration-01.png and targets/codex/x-image/tests/acceptance/output/ac-07-illustration-02.png. Use exactly one generation call per asset and stop if either asset fails.
```

Expected style: locked `editorial-material` across both assets

Expected ratio: `3:2` for both assets

Maximum permitted tool calls: 2 generations total, 0 edits, 0 image modification commands

Final prompt: [PENDING — record both prompts]

Style ID: [PENDING — record both and confirm equality]

image_gen call count: [PENDING]

ImageGen edit call count: [PENDING]

Image modification command count: [PENDING]

Saved output path: [PENDING — record both paths]

Actual dimensions: [PENDING — record both dimensions]

Content QA: [PENDING — asset 1 exact labels/order; asset 2 fragment-to-article concept]

Style QA: [PENDING — same accent, materials, lighting, label treatment, and density]

P0 checklist: [PENDING — two calls total, originals, exact labels, no watermark or prompt leakage]

P1 checklist: [PENDING — both readable, distinct cognitive jobs, consistent batch style]

P2 checklist: [PENDING — minor cross-asset spacing or decorative observations]
