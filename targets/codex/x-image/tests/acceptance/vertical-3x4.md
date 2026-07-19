# AC-04 — 3:4 Vertical Illustration

Status: PASS

Codex task or thread: `/root/ac04_vertical`

Input fixture: `targets/codex/x-image/tests/fixtures/humanities-article.md`

Exact Codex prompt:

```text
Use the native x-image skill. Read targets/codex/x-image/tests/fixtures/humanities-article.md and generate exactly one 3:4 vertical article illustration in editorial-material style. Create a quiet symbolic garden scene with one illuminated path, no visible text, and one primary focal point. Save the original output under targets/codex/x-image/tests/acceptance/output/ac-04-vertical.png. Do not generate any other asset.
```

Expected style: `editorial-material`

Expected ratio: `3:4`

Maximum permitted tool calls: 1 generation, 0 edits, 0 image modification commands

Final prompt:

```text
Use case: stylized-concept
Asset type: vertical illustration
Primary request: Create a quiet symbolic garden scene expressing attention as deliberate cultivation and choice, with exactly one softly illuminated garden path as the single primary focal point.
Source-derived content: Attention is like a garden that needs continuing care; what receives repeated attention grows, while neglected things slowly recede from view. The image must feel quiet, restrained, and selective: one beam of light illuminates only one path through the garden, while the rest of the garden remains present but does not compete for attention.
Exact visible text: "" — render no visible text anywhere.
Aspect ratio and target dimensions: 3:4 vertical composition; prompt target 1536 × 2048 pixels.
Style ID: editorial-material
Full Style Spec: warm off-white background #F5F2EA; neutral gray and charcoal palette with one saturated accent, IKB blue #2447FF; restrained soft 3D material illustration using tactile paper, clay, and matte surfaces; soft studio lighting with short soft shadows and no dramatic bloom; asymmetric Swiss editorial grid with one focal object or flow; no labels or text; avoid glow, gradient blobs, watermark, fake interface chrome, paragraph text, and multiple focal points.
Layout pattern: symbolic scene.
Composition and safe margins: Portrait garden viewed from a slightly elevated, gently forward-looking angle. A single narrow path runs clearly from the lower foreground toward the upper middle and is the sole visual anchor. A controlled soft shaft of studio-like light falls only on this path, using the IKB blue accent sparingly along the lit route. Surrounding beds, leaves, and quiet garden forms are simplified tactile paper-and-clay shapes in muted gray, charcoal, and warm off-white; they remain readable but subdued, with some peripheral forms softly receding into low contrast. Keep generous clear margins on all sides, especially at top and bottom. Maintain one unmistakable hierarchy and one primary focal point: the illuminated path.
Data and reference accuracy: No numerical data, categories, units, axes, historical details, people, names, or quotations. Preserve the symbolic relationship: sustained attention corresponds to the one illuminated, cared-for path; ignored areas remain present but visually recede.
Global constraints: Exactly one primary focal point. No visible text. No logos, signatures, brands, watermarks, people, signs, plaques, labels, interface elements, or decorative typography. Keep the scene calm, restrained, materially tactile, and editorial rather than photorealistic or fantastical. Respect the 3:4 portrait composition and safe margins.
Avoid: multiple paths, branching paths, competing bright flowers, central statues, gates, benches, fountains, dramatic sunbeams, luminous glow effects, bloom, neon, gradient blobs, dense clutter, busy botanical detail, high-contrast background objects, photorealism, cinematic fantasy, text-like marks, letters, numbers, logos, and watermarks.
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

Saved output path: `targets/codex/x-image/tests/acceptance/output/ac-04-vertical.png`

Actual dimensions: `1086 × 1448`, exact `3:4`

Content QA: PASS — one illuminated path expresses selective attention, the rest of the garden recedes, and no text, people, history, or additional paths appear.

Style QA: PASS — warm off-white, muted charcoal garden, IKB-blue accents, tactile matte paper/clay rendering, restrained light, and one dominant vertical flow.

P0 checklist: PASS — one generation, zero edits, zero modification commands, byte-identical original copy, no invented text, no watermark or prompt leakage.

P1 checklist: PASS — meaningful symbolic illustration, correct vertical composition, single focal point, and editorial-material adherence.

P2 checklist: Blue flower clusters create minor secondary activity but remain subordinate and reinforce the path.
