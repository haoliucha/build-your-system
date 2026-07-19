# AC-03 — 3:2 Labeled Explainer

Status: PASS

Codex task or thread: `/root/ac03_explainer_v2`

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
Primary request: Create one polished 3:2 editorial-material inline explainer showing a single four-step pipeline moving clearly from left to right in this exact order: 捕获, 澄清, 连接, 表达.
Source-derived content: The source describes turning scattered ideas into an article through four consecutive stages. Represent only the ordered progression from capturing fragments, to clarifying them, to connecting them, to expressing them. Use four restrained tactile soft-3D stage objects arranged on one horizontal baseline: first, a small open matte clay catch-bowl holding three completely plain pebble-like fragments; second, a simple clear glass lens examining one completely plain clay fragment; third, three completely plain matte clay nodes physically joined by short solid rods; fourth, a small matte clay speaking-horn form projecting only a clean soft blue material shape with no marks. These objects are visual metaphors only and must carry no markings or text-like detail.
Exact visible text: "捕获" "澄清" "连接" "表达". This is an exhaustive allowlist. Render each label exactly once, character-for-character, in the stated left-to-right order. No quotation marks are visible. No other visible or implied text is permitted.
Aspect ratio and target dimensions: 3:2 landscape composition, prompt target 1536 × 1024.
Style ID: editorial-material
Full Style Spec: warm off-white background #F5F2EA; neutral gray and charcoal palette with one saturated IKB blue accent #2447FF; restrained soft 3D material objects with tactile matte clay and limited clear glass; soft studio lighting with short soft shadows and no dramatic bloom; asymmetric Swiss editorial composition organized as one dominant horizontal flow; exact high-contrast Chinese labels, 2 characters each, in a clean bold sans-serif; no more than these four labels; exact visible text is exhaustive. Avoid glow, gradient blobs, watermark, fake interface chrome, paragraph text, pseudo-writing, question marks, punctuation, ruled lines, grids, body-copy bars, placeholder blocks, multiple focal points.
Layout pattern: Pipeline, strictly left-to-right. Four evenly paced stages on one horizontal line. Place the corresponding freestanding label directly beneath each stage object: 捕获 beneath stage one, 澄清 beneath stage two, 连接 beneath stage three, 表达 beneath stage four. Connect stage one to stage two, stage two to stage three, and stage three to stage four using exactly three large, simple, unambiguous solid IKB-blue arrows pointing right. Arrowheads must be unmistakable and all point only right.
Composition and safe margins: One primary focal flow centered across the canvas with generous warm off-white whitespace. Keep all objects, labels, and arrowheads comfortably inside at least 10% safe margins. Maintain strong scan order and separation. Do not add a title, subtitle, legend, caption, border, header, footer, badge, numbering, or decorative annotation.
Data and reference accuracy: Preserve exactly four stages and exactly this order: 捕获, 澄清, 连接, 表达. Do not exchange, omit, duplicate, add, or rewrite any stage. The only relationships are the three consecutive rightward transitions.
Global constraints: Generate a complete final raster asset. The four Chinese labels are the only text or text-like marks anywhere. Every object surface must be clean and plain except for no text at all; the allowed labels must be freestanding directly beneath objects, not printed on any object. Do not include paper, cards, pages, documents, books, notebooks, screens, signs, label plaques, panels, interfaces, sticky notes, or writing surfaces. If any paper/card/page-like surface is nevertheless introduced, its surface must be completely blank. Forbid question marks, all punctuation, ruled lines, grids, body-copy bars, placeholder blocks, abstract glyphs, pseudo-writing, scribbles, symbols resembling text, letters, numbers, logos, signatures, and watermarks. No icons containing interior marks. No additional arrow beyond the three specified rightward arrows.
Avoid: any extra visible or implied text; quotation marks; punctuation; stage numbers; thin ambiguous connectors; leftward, upward, downward, curved, circular, branching, or bidirectional arrows; card UI; diagram boxes; page shapes; text-like texture; random strokes; decorative glyphs; illegible Chinese; repeated labels; clutter; gradients; glow; multiple focal points.
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

Atomic placement helper call count: 1

Saved output path: `targets/codex/x-image/tests/acceptance/output/ac-03-explainer-v2.png`

Requested base preserved: `targets/codex/x-image/tests/acceptance/output/ac-03-explainer.png`

Actual dimensions: `1536 × 1024`, exact `3:2`

Output SHA-256: `a444f9a2a70c04fe44da6128dcc455b787d540ba12b2fd0136c4c6c214241041`

Content QA: PASS — exactly four visible labels appear once each in the required order, with exactly three right-pointing arrows; no extra text, punctuation, question marks, lines, grids, pseudo-writing, placeholder blocks, glyphs, or text-like symbols appear.

Style QA: PASS — warm off-white background, tactile matte clay and limited glass, charcoal neutrals, IKB-blue accent, soft studio lighting, generous margins, and one clear horizontal editorial flow.

P0 checklist: PASS — one generation, zero edits, zero modification commands, atomic byte-identical placement, original base preserved, correct labels/order, no watermark or prompt leakage.

P1 checklist: PASS — exhaustive visible-text allowlist, blank object surfaces, unambiguous direction, exact ratio, and editorial-material adherence.

P2 checklist: None.

## Attempt history

- Attempt 1: initially recorded PASS, then changed to FAIL during independent code review after visual inspection found a question mark, ruled/grid paper, and paragraph-like lines.
- Regression: `test_editorial_material_cannot_imply_extra_writing` and expanded exact-text prompt assertions.
- Attempt 2: PASS in a fresh task; atomic placement preserved the first output and selected `ac-03-explainer-v2.png`.
