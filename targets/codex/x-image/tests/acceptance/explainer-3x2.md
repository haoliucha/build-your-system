# AC-03 — 3:2 Labeled Explainer

Status: FAIL

Codex task or thread: `/root/ac03_explainer`

Input fixture: `targets/codex/x-image/tests/fixtures/explainer-article.md`

Exact Codex prompt:

```text
Use the native x-image skill. Read targets/codex/x-image/tests/fixtures/explainer-article.md and generate exactly one 3:2 inline explainer in editorial-material style. Show a four-step pipeline in this exact order with the exact labels「捕获」「澄清」「连接」「表达」and unambiguous arrows. Save the original output under targets/codex/x-image/tests/acceptance/output/ac-03-explainer.png. Do not generate any other asset.
```

Expected style: `editorial-material`

Expected ratio: `3:2`

Maximum permitted tool calls: 1 generation, 0 edits, 0 image modification commands

Final prompt:

```text
Use case: infographic-diagram
Asset type: inline explainer
Primary request: Create one polished editorial explainer showing a single four-step article-making pipeline from fragmented ideas to a finished article, with an unmistakable left-to-right reading direction.
Source-derived content: The process has exactly four consecutive steps. Step 1 captures raw fragments without classifying them; step 2 clarifies the question each fragment answers; step 3 connects related fragments into an argument; step 4 expresses the argument as a complete article for readers. Visually distinguish the four stages with restrained tactile objects: loose paper fragments entering the first stage, a focused question-card motif at the second, visibly linked paper pieces at the third, and one clean finished article sheet at the fourth.
Exact visible text: "捕获" "澄清" "连接" "表达". Render these four Chinese labels verbatim, clearly legible, and in exactly this left-to-right order. Do not add any other text, letters, numbers, punctuation, captions, headings, or symbols that resemble text.
Aspect ratio and target dimensions: exact 3:2 landscape composition; target 1536 × 1024 pixels.
Style ID: editorial-material
Full Style Spec: background warm off-white #F5F2EA; palette neutral gray and charcoal with one saturated accent; accent IKB blue #2447FF; medium restrained soft 3D material objects using tactile paper, clay, and matte surfaces; lighting soft studio light with short soft shadows and no dramatic bloom; composition asymmetric Swiss editorial grid organized around one focal flow; text rules exact high-contrast Chinese labels, 2 characters each, attached directly to their stage, four labels total; avoid glow, gradient blobs, watermark, fake interface chrome, paragraph text, multiple focal points.
Layout pattern: Pipeline, strictly left-to-right.
Composition and safe margins: Place four clearly separated stage modules across one horizontal band, evenly progressing from left to right. Use one continuous cognitive flow. Connect stage 1 to stage 2, stage 2 to stage 3, and stage 3 to stage 4 using three bold, clean IKB-blue right-pointing arrows with unmistakable arrowheads. No bidirectional arrows, curved-back arrows, cycles, branches, crossings, or ambiguous connectors. Keep every label, object, and arrow comfortably inside generous safe margins; preserve whitespace; make the four-step pipeline the single primary focal point.
Data and reference accuracy: Preserve exactly four stages and only four stages. Preserve exact order: 捕获 → 澄清 → 连接 → 表达. The arrows must explicitly encode this order and direction. The final sheet belongs only to 表达; linked fragments belong only to 连接; do not swap, merge, add, or omit stages.
Global constraints: Exact requested text and relationships are non-overridable. Maintain legibility, factual accuracy, ratio safety, one primary focal point, and no extra logos or watermarks. Complete the entire asset as a coherent final raster in one generation.
Avoid: extra text of any kind; misspelled, altered, duplicated, or reordered labels; extra steps; missing arrowheads; ambiguous arrow direction; circular layout; vertical sequence; decorative dashboard; UI panels; dense detail; edge clipping; logos; signatures; watermarks; photographic people; neon glow; gradients; dramatic shadows.
Single-call instruction: Generate the entire final raster asset in exactly one built-in image_gen call.
Do not generate intermediate assets.
Use no retry, no edit, and no post-processing.
Do not crop, resize, pad, overlay, composite, repair, or re-encode the result.
Render all requested text and visual elements inside this single generation.
```

Style ID: `editorial-material`

image_gen call count: 1

ImageGen edit call count: 0

Image modification command count: 0

Saved output path: `targets/codex/x-image/tests/acceptance/output/ac-03-explainer.png`

Actual dimensions: `1536 × 1024`

Content QA: FAIL — the four required labels and arrows are correct, but the image also contains a large question mark, ruled/grid fragments, and paragraph-like lines that violate the exhaustive visible-text allowlist.

Style QA: PASS — warm off-white background, tactile paper/clay materials, charcoal typography, IKB-blue arrows, generous whitespace, and one horizontal focal flow.

P0 checklist: PASS — one generation, zero edits, zero modification commands, byte-identical original, exact labels/order, no watermark or prompt leakage.

P1 checklist: FAIL — forbidden extra glyphs and pseudo-writing appear on material surfaces.

P2 checklist: None; the finding is P1.

## Attempt history

- Attempt 1: initially recorded PASS, then changed to FAIL during independent code review after visual inspection found a question mark, ruled/grid paper, and paragraph-like lines.
- Regression: `test_editorial_material_cannot_imply_extra_writing` and expanded exact-text prompt assertions.
