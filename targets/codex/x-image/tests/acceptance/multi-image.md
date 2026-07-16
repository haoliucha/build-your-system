# AC-07 — Two Consistent Illustrations

Status: PASS

Codex task or thread: `/root/ac07_multi_v3`

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
Asset type: inline explainer article illustration
Primary request: Create an exact four-step left-to-right pipeline that explains how scattered ideas become an article, with four clearly separate tactile material stations connected by one continuous physical flow moving unambiguously from left to right.
Source-derived content: The source defines exactly four consecutive stages in this order: capture raw fragments, clarify what question each fragment answers, connect related fragments into an argument, and express the result as a complete article. Represent those semantics only through the four ordered stations and their material progression. Station 1 contains a few loose blank paper fragments; station 2 organizes those blank fragments into one compact group; station 3 physically joins the organized blank pieces into one continuous layered structure; station 4 resolves into one coherent blank article sheet or slim blank folio. Keep the transformation readable without adding any other concepts.
Exact visible text: "捕获" "澄清" "连接" "表达". This is an exhaustive allowlist. Render each label exactly once, in this exact left-to-right order, attached directly to its corresponding station. Character-by-character: 捕-获; 澄-清; 连-接; 表-达. No other readable text or text-like marks anywhere.
Aspect ratio and target dimensions: exact 3:2 landscape composition; prompt target 1536 × 1024 pixels.
Style ID: editorial-material
Full Style Spec: Background is uniform warm off-white #F5F2EA. Palette is neutral gray and charcoal with exactly one saturated accent, IKB blue #2447FF, locked for this batch. Medium is restrained soft 3D editorial material objects with tactile paper, clay, and matte surfaces. Lighting is soft studio light with short soft shadows and no dramatic bloom. Composition is a sparse asymmetric Swiss editorial arrangement with one dominant left-to-right flow. Labels use exact high-contrast Chinese sans-serif typography, crisp and readable, 2 characters per station. Avoid glow, gradients, gradient blobs, watermark, fake interface chrome, paragraphs, decorative dashboards, multiple focal points, and visual clutter.
Layout pattern: Pipeline, exactly four steps, strictly left to right.
Composition and safe margins: One primary focal point is the complete four-stage pipeline across the horizontal center. Use generous warm off-white negative space and at least 10% clear safe margin on every edge. Four stations have equal visual weight and clear separation. Connect them through a single continuous tangible IKB-blue material ribbon or track whose physical continuity and progressive left-to-right staging make direction unmistakable without arrowheads or symbols. No extra station, branch, loop, legend, title, caption, border, or footer.
Data and reference accuracy: Preserve exactly four stages, exact stage order 捕获 → 澄清 → 连接 → 表达 in semantic left-to-right reading order, while rendering only the four allowed Chinese labels and not rendering the arrow glyph shown in this instruction. Do not exchange, omit, duplicate, add, or rewrite labels. The physical material progression must accurately move from loose raw fragments to clarification, connected argument structure, and a coherent final article.
Global constraints: Exact visible text is an exhaustive allowlist. Every paper, card, page, screen-like slab, folio, material panel, and document-shaped surface other than the four label-bearing station faces must stay completely blank. The label-bearing faces contain only their single allowed label and nothing else. No logos, trademarks, signature, watermark, fake UI, or invented text. One primary focal flow. Maintain ratio-safe composition and legibility.
Avoid: Any question mark; any punctuation mark; any numeral; any Latin letter; any extra Chinese character; ruled lines; grids; body-copy bars; placeholder blocks; bullets; dots used as writing; scribbles; pseudo-writing; random strokes that resemble writing; abstract glyphs; icons; symbols; arrowheads; chevrons; decorative marks; interface chrome; charts; legends; tiny captions; page numbers; stamps; seals; logos; watermark. Do not place text-like texture on any surface. Do not use decorative paper marks that could be mistaken for writing. Keep every non-label surface completely blank.
Single-call instruction: Generate the entire final raster asset in exactly one built-in image_gen call.
Do not generate intermediate assets.
Use no retry, no edit, and no post-processing.
Do not crop, resize, pad, overlay, composite, repair, or re-encode the result.
Render all requested text and visual elements inside this single generation.
```

Asset 2:

```text
Use case: infographic-diagram
Asset type: inline explainer article illustration
Primary request: Create a tactile layer-stack explainer showing raw blank fragments progressively becoming one coherent article, using a single ordered physical stack with a clear transformation from loose fragmented pieces at the lower-left base through increasingly aligned and connected layers to one complete blank article sheet or slim blank folio at the upper-right top.
Source-derived content: The source explains that scattered raw fragments are clarified, connected into an argument, and rewritten as one complete article. Represent this transformation without labels: several irregular blank paper fragments at the lowest layer; a middle layer where the same blank pieces align and overlap into a coherent structure; an upper layer where they merge into one unified page assembly; and one dominant final blank article sheet or slim blank folio at the top. The transformation must be visually understandable through containment, alignment, continuity, and increasing coherence only.
Exact visible text: empty allowlist. Render absolutely no readable text and no text-like marks anywhere.
Aspect ratio and target dimensions: exact 3:2 landscape composition; prompt target 1536 × 1024 pixels.
Style ID: editorial-material
Full Style Spec: Background is uniform warm off-white #F5F2EA. Palette is neutral gray and charcoal with exactly one saturated accent, IKB blue #2447FF, locked for this batch. Medium is restrained soft 3D editorial material objects with tactile paper, clay, and matte surfaces. Lighting is soft studio light with short soft shadows and no dramatic bloom. Composition is a sparse asymmetric Swiss editorial arrangement with one dominant material transformation. There are no labels. Avoid glow, gradients, gradient blobs, watermark, fake interface chrome, paragraphs, decorative dashboards, multiple focal points, and visual clutter.
Layout pattern: Layer stack, ordered from raw fragments at the lower-left base to one coherent article at the upper-right top.
Composition and safe margins: One primary focal point is a single ascending diagonal layer stack centered within generous warm off-white negative space. Keep at least 10% clear safe margin on every edge. Use a few large tactile layers rather than many small pieces. At the base, show several irregular blank fragments that physically belong to the same stack. In the middle, show those forms progressively aligned and joined. At the top, resolve them into one unmistakably complete blank article sheet or slim blank folio with a clean silhouette. Use restrained IKB-blue material only as one continuous binding seam or structural connector through the stack, never as a symbol, arrow, character, or writing mark. No separate panels, branch, loop, legend, title, caption, border, footer, UI frame, or competing object.
Data and reference accuracy: The causal relationship must read as many raw fragments becoming one coherent article. Do not reverse the transformation. Do not introduce categories, metrics, screens, writing instruments, people, icons, or unrelated objects. The final object must be singular and visibly coherent; the raw inputs must remain visibly fragmented at the base.
Global constraints: Exact visible text is an empty exhaustive allowlist. Every paper, card, page, screen-like slab, folio, material panel, layer, and document-shaped surface must stay completely blank. No logos, trademarks, signature, watermark, fake UI, invented text, or text-like texture. One primary focal transformation. Maintain ratio-safe composition and legibility.
Avoid: Any question mark; any punctuation mark; any numeral; any Latin letter; any Chinese character; any readable text; ruled lines; grids; body-copy bars; placeholder blocks; bullets; dots used as writing; scribbles; pseudo-writing; random strokes that resemble writing; abstract glyphs; icons; symbols; arrowheads; chevrons; decorative marks; interface chrome; charts; legends; tiny captions; page numbers; stamps; seals; logos; watermark. Do not place text-like texture on any surface. Do not use decorative paper marks that could be mistaken for writing. Keep every surface completely blank.
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

Atomic placement helper call count: 2

Saved output path:

- `targets/codex/x-image/tests/acceptance/output/ac-07-illustration-01-v2.png`
- `targets/codex/x-image/tests/acceptance/output/ac-07-illustration-02-v2.png`

Requested bases preserved:

- `targets/codex/x-image/tests/acceptance/output/ac-07-illustration-01.png`
- `targets/codex/x-image/tests/acceptance/output/ac-07-illustration-02.png`

Actual dimensions: `1536 × 1024` for both, exact `3:2`

Output SHA-256:

- Asset 1: `ea9c065e67293536ec28ad38516125673a5cb1c2c145f9fa353ad19077f65d59`
- Asset 2: `b986be63c0d45fbf2a3df686a714faaf97dcac31da65e2dca17da6d5dda4e1fe`

Content QA: PASS — Asset 1 contains exactly the four required labels once each in order with a clear left-to-right material progression; Asset 2 shows blank fragments aligning and resolving into one coherent article object; neither contains extra text, pseudo-writing, punctuation, ruled lines, grids, body-copy bars, glyphs, watermark, or fake UI.

Style QA: PASS — both share the locked warm off-white ground, neutral tactile paper/clay materials, IKB-blue structural accent, soft studio light, restrained shadows, and sparse editorial density.

P0 checklist: PASS — two generations total, zero edits, zero modification commands, two atomic byte-identical placements, existing bases preserved, exact labels where required, and no watermark or prompt leakage.

P1 checklist: PASS — exhaustive visible-text rules, blank surfaces, distinct cognitive jobs, exact ratios, correct causal relationships, and locked batch style.

P2 checklist:

- Asset 1's outer stations and blue track sit closer to the side edges than the requested 10% safe margin, but nothing is clipped and labels remain legible.
- Asset 1 is more regular than strongly asymmetric, without affecting meaning.
- Asset 2's final folio approaches the top edge more closely than requested but remains unclipped and clear.

## Attempt history

- Attempt 1: initially recorded PASS, then changed to FAIL during independent code review because Asset 1 used body-copy bars to imply writing.
- The retrospective Asset 1 failure also meant the batch should have stopped before Asset 2 under the stop-after-first-failure contract.
- Regression: `test_editorial_material_cannot_imply_extra_writing` and expanded exact-text prompt assertions.
- Attempt 2: a fresh task stopped correctly after Asset 1's sole tool invocation failed input validation because `num_last_images_to_include: 0` is invalid; Asset 2 remained unattempted and there was no retry.
- Attempt 3: PASS in a new fresh task; both new-image calls omitted image reference parameters, passed sequential QA, and atomically selected `-v2` siblings.
