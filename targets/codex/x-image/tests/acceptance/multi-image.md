# AC-07 — Two Consistent Illustrations

Status: PASS

Codex task or thread: `/root/ac07_multi`

Input fixture: `targets/codex/x-image/tests/fixtures/explainer-article.md`

Exact Codex prompt:

```text
Use the native x-image skill. Read targets/codex/x-image/tests/fixtures/explainer-article.md and generate exactly two 3:2 article illustrations with a locked editorial-material style. Asset 1 is the exact four-step pipeline「捕获」「澄清」「连接」「表达」. Asset 2 is a layer-stack explanation showing raw fragments becoming a coherent article, with no visible text. Save original outputs under targets/codex/x-image/tests/acceptance/output/ac-07-illustration-01.png and targets/codex/x-image/tests/acceptance/output/ac-07-illustration-02.png. Use exactly one generation call per asset and stop if either asset fails.
```

Expected style: locked `editorial-material` across both assets

Expected ratio: `3:2` for both assets

Maximum permitted tool calls: 2 generations total, 0 edits, 0 image modification commands

Final prompt:

Asset 1:

```text
Use case: infographic-diagram
Asset type: inline explainer
Primary request: Create a clear editorial illustration of the exact four-step process that turns scattered thoughts into an article, shown as one continuous left-to-right pipeline.
Source-derived content: Four consecutive steps only: first capture raw fragments without classifying them; second clarify the question each fragment answers; third connect related fragments into one argument; fourth express or rewrite that argument as a complete article for readers. Represent the process through tactile material objects: a small cluster of loose paper fragments entering step 1, increasingly ordered paper/card forms through steps 2 and 3, and a single coherent finished article sheet emerging at step 4. Clear directional arrows must connect every adjacent step. Do not swap, omit, duplicate, or add steps.
Exact visible text: "捕获" "澄清" "连接" "表达". Render these four labels verbatim, character-for-character, in this exact left-to-right order. No other visible text, letters, numbers, pseudo-text, marks resembling writing, or captions anywhere.
Aspect ratio and target dimensions: exact 3:2 landscape composition; prompt target 1536 × 1024 pixels.
Style ID: editorial-material
Full Style Spec: warm off-white background #F5F2EA; neutral gray and charcoal palette with one saturated IKB blue accent #2447FF, locked for this batch; restrained soft 3D material objects with tactile paper, clay, or matte surfaces; soft studio light with short soft shadows and no dramatic bloom; asymmetric Swiss editorial grid with one focal flow; exact high-contrast Chinese labels, 2 characters each, attached to their corresponding step; composition density is restrained and airy; avoid glow, gradient blobs, watermark, fake interface chrome, paragraph text, and multiple focal points.
Layout pattern: Pipeline.
Composition and safe margins: One dominant horizontal flow spanning the central band. Four distinct, evenly sequenced material stations with generous whitespace, clear IKB-blue arrows pointing only left-to-right between adjacent stations, strong hierarchy, and at least 8% safe margin on every edge. Keep every label large, unobstructed, upright, and visually attached to its own station. No decorative element may compete with the pipeline.
Data and reference accuracy: Preserve exactly four steps and exactly this semantic and visual order: 捕获 → 澄清 → 连接 → 表达. The arrow direction must be unambiguous from left to right. Raw fragments must visibly become progressively structured and end as one coherent article sheet.
Global constraints: Exact required text and order are non-overridable. One primary focal point. No extra logos or watermarks. Maintain legibility, factual accuracy, ratio safety, and safe margins.
Avoid: Any extra text or pseudo-writing, wrong Chinese glyphs, swapped labels, missing or duplicated labels, reversed or ambiguous arrows, cycles, branching, more or fewer than four stations, screens, dashboards, fake UI, book-cover framing, photorealistic people, decorative clutter, gradients, glow, dramatic shadows, logos, signatures, watermarks, edge clipping.
Single-call instruction: Generate the entire final raster asset in exactly one built-in image_gen call.
Do not generate intermediate assets.
Use no retry, no edit, and no post-processing.
Do not crop, resize, pad, overlay, composite, repair, or re-encode the result.
Render all requested text and visual elements inside this single generation.
```

Asset 2:

```text
Use case: infographic-diagram
Asset type: inline explainer
Primary request: Create a text-free editorial layer-stack explanation showing raw thought fragments progressively becoming one coherent finished article.
Source-derived content: The visual transformation must be ordered and understandable without labels: a lowest input layer of irregular loose paper fragments; an upper clarification layer where fragments are selected and aligned into meaningful groups; a connection layer where related cards are visibly linked into one continuous argument path; and a top output layer consisting of one clean, coherent finished article sheet. The layers must read as a single upward transformation from fragmented inputs to unified output, with clear containment and dependency.
Exact visible text: "". No visible text of any kind: no words, Chinese characters, Latin letters, numbers, captions, labels, icons containing text, pseudo-writing, line-like body copy, or typographic marks anywhere.
Aspect ratio and target dimensions: exact 3:2 landscape composition; prompt target 1536 × 1024 pixels.
Style ID: editorial-material
Full Style Spec: warm off-white background #F5F2EA; neutral gray and charcoal palette with one saturated IKB blue accent #2447FF, locked for this batch; restrained soft 3D material objects with tactile paper, clay, or matte surfaces; soft studio light with short soft shadows and no dramatic bloom; asymmetric Swiss editorial grid with one focal flow; no labels for this asset; composition density is restrained and airy; avoid glow, gradient blobs, watermark, fake interface chrome, paragraph text, and multiple focal points.
Layout pattern: Layer stack.
Composition and safe margins: One dominant stepped stack centered slightly off-axis on an asymmetric Swiss editorial grid. Show four clearly separated but interdependent tactile layers rising from lower-left toward upper-right: loose fragments at the bottom, ordered groups above, a visibly connected argument path above that, and one unified finished paper object at the top. Use small IKB-blue connectors or structural edges to make the upward dependency unmistakable. Generous whitespace and at least 8% safe margin on every edge. The finished article sheet is the single focal object; all lower layers support it.
Data and reference accuracy: Preserve the causal order raw fragments → clarified groups → connected argument → coherent article. The final state must be a single unified article object, not another pile. No textual explanation may be used.
Global constraints: No visible text is non-overridable. One primary focal point. No extra logos or watermarks. Maintain factual accuracy, ratio safety, and safe margins.
Avoid: Any visible or pseudo text, glyphs, numbers, ruled writing lines, gray body-copy bars, captions, labels, screens, dashboards, fake UI, books with titles, people, unrelated decorative objects, unordered piles in the final layer, ambiguous progression, branching, cycles, gradients, glow, dramatic shadows, logos, signatures, watermarks, edge clipping.
Single-call instruction: Generate the entire final raster asset in exactly one built-in image_gen call.
Do not generate intermediate assets.
Use no retry, no edit, and no post-processing.
Do not crop, resize, pad, overlay, composite, repair, or re-encode the result.
Render all requested text and visual elements inside this single generation.
```

Style ID: `editorial-material` for both assets; equality confirmed.

image_gen call count: 2 total, exactly 1 per asset

ImageGen edit call count: 0

Image modification command count: 0

Saved output path:

- `targets/codex/x-image/tests/acceptance/output/ac-07-illustration-01.png`
- `targets/codex/x-image/tests/acceptance/output/ac-07-illustration-02.png`

Actual dimensions: `1536 × 1024` for both, exact `3:2`

Content QA: PASS — Asset 1 contains exactly the legible ordered labels `捕获 → 澄清 → 连接 → 表达` with a clear left-to-right transformation; Asset 2 clearly shows loose fragments becoming grouped cards, a connected argument, and one coherent article without visible text.

Style QA: PASS — both share the same warm off-white field, neutral tactile paper/clay materials, IKB-blue accent, soft studio light, short shadows, editorial grid language, and restrained density.

P0 checklist: PASS — two generations total, zero edits, zero modification commands, byte-identical originals, exact labels where required, and no watermark or prompt leakage.

P1 checklist: PASS — both are readable and exact 3:2; the first explains a sequence and the second explains dependency layers while remaining visibly one batch.

P2 checklist: Abstract gray and blue blocks on Asset 1's final article suggest page structure but contain no readable or invented text.
