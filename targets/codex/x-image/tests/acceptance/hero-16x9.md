# AC-02 — 16:9 Article Hero

Status: PASS

Codex task or thread: `/root/ac02_hero`

Input fixture: `targets/codex/x-image/tests/fixtures/humanities-article.md`

Exact Codex prompt:

```text
Use the native x-image skill. Read targets/codex/x-image/tests/fixtures/humanities-article.md and generate exactly one 16:9 article hero in editorial-material style. Use one illuminated garden path as the primary focal point and render the exact title「注意力是一座花园」. Save the original output under targets/codex/x-image/tests/acceptance/output/ac-02-hero.png. Do not generate any other asset.
```

Expected style: `editorial-material`

Expected ratio: `16:9`

Maximum permitted tool calls: 1 generation, 0 edits, 0 image modification commands

Final prompt:

```text
Use case: cover — hero title
Asset type: article hero
Primary request: Create one quiet, restrained 16:9 editorial hero whose single primary focal point is one illuminated garden path, expressing attention as a garden shaped by care and choice.
Source-derived content: Attention is not a container waiting to be filled; it is like a garden that needs continual care. What receives repeated attention grows, while what is ignored gradually recedes from view. Show a calm garden where one soft directional beam of light illuminates exactly one small path; the surrounding garden remains present and materially visible but subdued so it does not compete for attention. No people, names, dates, quote sources, or historical events.
Exact visible text: "注意力是一座花园". Render these Chinese characters verbatim and exactly once, in this exact order: 注 意 力 是 一 座 花 园. Do not add any other text or punctuation.
Aspect ratio and target dimensions: strict 16:9 landscape composition; prompt target 2048 × 1152 pixels.
Style ID: editorial-material
Full Style Spec: warm off-white background #F5F2EA; neutral gray and charcoal palette with one restrained saturated accent, IKB blue #2447FF; restrained soft 3D material objects with tactile paper, clay, and matte surfaces; soft studio lighting with short soft shadows and no dramatic bloom; asymmetric Swiss editorial grid with one focal object or flow; exact high-contrast Chinese title typography; avoid glow, gradient blobs, watermark, fake interface chrome, paragraph text, and multiple focal points.
Layout pattern: Hero title — one short exact title plus one symbolic material visual hook.
Composition and safe margins: The illuminated garden path is the sole dominant visual hook. Use exactly one path, beginning near the lower foreground and leading gently into the garden, with one controlled pool or beam of soft light defining the chosen route. Keep all flowers, leaves, beds, and garden forms secondary, sparse, matte, and low-contrast. Place the exact title in a clean high-contrast editorial text block integrated into the asymmetric grid, with generous negative space and at least 8% safe margin from every edge. Maintain strong thumbnail legibility and an uncluttered hierarchy. Use IKB blue only as a small disciplined accent on or beside the focal path, not as a competing object.
Data and reference accuracy: Preserve the relationship that repeated attention nourishes growth and ignored elements recede. The scene must contain one and only one illuminated garden path; all other garden regions remain visible but do not compete. There are no numeric values, units, categories, or axes.
Global constraints: One primary focal point; exact readable visible title; no invented text; no extra logos or watermarks; ratio-safe composition; preserve factual and metaphorical relationships; complete final raster only.
Avoid: multiple paths, branching paths, multiple beams of light, competing bright flowers, people, animals, buildings, containers, dramatic fantasy glow, lens flare, neon effects, gradients or gradient blobs, dense botanical clutter, photorealistic stock-photo styling, fake UI, logos, signatures, watermarks, paragraph text, subtitles, captions, English text, extra Chinese characters, cropped title, illegible typography.
Generate the entire final raster asset in exactly one built-in image_gen call.
Do not generate intermediate assets.
Use no retry, no edit, and no post-processing.
Do not crop, resize, pad, overlay, composite, repair, or re-encode the result.
Render all requested text and visual elements inside this single generation.
```

Style ID: `editorial-material`

image_gen call count: 1

ImageGen edit call count: 0

Image modification command count: 0

Saved output path: `targets/codex/x-image/tests/acceptance/output/ac-02-hero.png`

Actual dimensions: `1672 × 941`, approximately `16:9`

Content QA: PASS — exact title appears once, one illuminated garden path is the focal point, surrounding garden stays subdued, and no names, dates, people, historical claims, logos, or extra text appear.

Style QA: PASS — warm off-white field, tactile neutral garden, restrained IKB-blue accent, soft lighting, asymmetric editorial composition, and generous negative space.

P0 checklist: PASS — one generation, zero edits, zero modification commands, byte-identical original copy, exact title, no watermark or prompt leakage.

P1 checklist: PASS — clear hero composition, single focal point, readable title, correct ratio intent, and editorial-material adherence.

P2 checklist: PASS — no advisory findings.
