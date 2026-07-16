# AC-06 — Explicit Custom Style

Status: PASS

Codex task or thread: `/root/ac06_custom`

Input fixture: `targets/codex/x-image/tests/fixtures/tech-article.md`

Exact Codex prompt:

```text
Use the native x-image skill. Read targets/codex/x-image/tests/fixtures/tech-article.md and generate exactly one 3:2 article illustration. Override automatic technology styling with a custom monochrome linocut editorial style: warm cream paper, black carved lines, one vermilion accent, flat light, no terminal motifs. Show one independent maker building an open-source tool. Use no visible text. Save the original output under targets/codex/x-image/tests/acceptance/output/ac-06-custom.png. Do not generate any other asset.
```

Expected style: task-local `custom-monochrome-linocut`

Expected ratio: `3:2`

Maximum permitted tool calls: 1 generation, 0 edits, 0 image modification commands

Final prompt:

```text
Use case: stylized-concept
Asset type: inline explainer
Primary request: Create one editorial illustration showing a single independent maker actively building an open-source research-organizing tool.
Source-derived content: One solo developer builds a modular tool that gathers scattered research fragments and organizes them into a searchable local archive; communicate this without text and without terminal imagery. Depict the concept metaphorically as one maker at a workbench assembling one open-frame, visibly modular indexing machine that receives loose unmarked paper fragments and sorts them into neat archive compartments.
Exact visible text: "" (none). Render no visible text of any kind.
Aspect ratio and target dimensions: 3:2 landscape composition, prompt target 1536 × 1024 pixels.
Style ID: custom-monochrome-linocut
Full Style Spec: id: custom-monochrome-linocut; use-for: editorial inline illustrations about independent open-source making; background: warm cream uncoated paper; palette: black ink and warm cream only, plus exactly one small vermilion accent; accent: a single vermilion-red component on the tool, used once as the only colored area; medium: monochrome linocut editorial print with bold hand-carved black lines, irregular carved hatching, flat ink shapes, and subtle natural paper grain; lighting: flat, even light with no modeled illumination, gradients, glow, bloom, or atmospheric effects; composition: asymmetric editorial composition with one clear focal interaction between the maker's hands and the modular machine, restrained density, generous cream negative space; text-rules: no words, letters, numbers, code, glyphs, labels, logos, signatures, or watermarks; avoid: terminal motifs, screens, command prompts, cursors, keyboards as focal motifs, code walls, fake interfaces, photorealism, smooth vector polish, 3D rendering, gradients, multiple focal points, multiple people, extra hands, corporate branding.
Layout pattern: symbolic scene.
Composition and safe margins: Show exactly one human maker, clearly working alone, in a three-quarter seated or standing workbench pose. Make the maker and the open-frame modular tool the single dominant focal group. Loose blank paper fragments enter from one side and resolve into orderly blank archive cards or compartments within the tool, making the organizing relationship unmistakable. Keep all essential content at least 8% inside every edge, with generous open cream space and no cropped hands or tool parts.
Data and reference accuracy: Exactly one maker represents the single core maintainer. The machine must read as inspectable, modular, and hand-built, conveying an open-source tool without logos or text. Show the relationship scattered research fragments -> organized local archive through physical arrangement only. Do not depict or imply additional people, teams, funding, charts, numerical values, or extra project data.
Global constraints: Preserve one primary focal point, strong ratio-safe composition, factual object relationships, and full compliance with the no-text requirement. No logo, watermark, signature, border caption, pseudo-text, or invented symbols.
Avoid: Any visible text; terminal or command-line motifs; monitors with interfaces; readable papers; logos; watermarks; more than one human; extra limbs; multiple vermilion areas; colors other than black, warm cream, and the single vermilion accent; glossy lighting; deep shadows; gradients; decorative clutter.
Single-call instruction: Generate the entire final raster asset in exactly one built-in image_gen call.
Do not generate intermediate assets.
Use no retry, no edit, and no post-processing.
Do not crop, resize, pad, overlay, composite, repair, or re-encode the result.
Render all requested text and visual elements inside this single generation.
```

Style ID: `custom-monochrome-linocut`

image_gen call count: 1

ImageGen edit call count: 0

Image modification command count: 0

Saved output path: `targets/codex/x-image/tests/acceptance/output/ac-06-custom.png`

Actual dimensions: `1536 × 1024`, exact `3:2`

Content QA: PASS — exactly one maker builds a modular, inspectable tool that transforms scattered blank fragments into organized archive compartments; no visible text, data, logo, or additional person.

Style QA: PASS — warm cream paper, black carved linocut lines, flat light, and exactly one vermilion gear accent; no terminal motifs, screen, fake UI, or default technology styling.

P0 checklist: PASS — one generation, zero edits, zero modification commands, byte-identical original, no invented text, watermark, or prompt leakage.

P1 checklist: PASS — explicit task-local style override is unmistakable, maker and machine form one focal group, and the composition is exact 3:2.

P2 checklist: A peripheral parts tray is slightly clipped by the bottom edge; the focal subject and meaning remain intact.
