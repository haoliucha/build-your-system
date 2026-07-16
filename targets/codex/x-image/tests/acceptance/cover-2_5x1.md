# AC-01 — 2.5:1 Technology Cover

Status: PASS

Codex task or thread: `/root/ac01_cover_v2`

Input fixture: `targets/codex/x-image/tests/fixtures/tech-article.md`

Exact Codex prompt:

```text
Use the native x-image skill. Read targets/codex/x-image/tests/fixtures/tech-article.md and generate exactly one X article cover. Use the 2.5:1 recommendation and terminal-tech style. The exact visible text must be「一个人，也能开源」and「48,216 stars」with one primary focal point. Save the original output under targets/codex/x-image/tests/acceptance/output/ac-01-cover.png. Do not generate any other asset.
```

Expected style: `terminal-tech`

Expected ratio: `2.5:1`

Maximum permitted tool calls: 1 generation, 0 edits, 0 image modification commands

Final prompt:

```text
Use case: ads-marketing
Asset type: X article cover
Primary request: Create a polished wide cover for an article about one independent developer building a successful open-source command-line tool, using the exact Chinese title as the single dominant focal point and the exact star count as one compact supporting line.
Source-derived content: The article is about a solo developer who built an open-source command-line tool; the fixed featured metric is 48,216 GitHub stars. Do not show the project name, maintainer count, plugin count, or any other data.
Exact visible text: "一个人，也能开源" and "48,216 stars". Render exactly these two strings, each exactly once, with no other visible text. For accuracy, the title character sequence is 一-个-人-，-也-能-开-源; render it continuously as "一个人，也能开源" with the full-width Chinese comma and no added spaces. Render the metric exactly as "48,216 stars", including the comma, one space, and lowercase letters.
Aspect ratio and target dimensions: 2.5:1 wide landscape composition; prompt target 2400 × 960 pixels.
Style ID: terminal-tech
Full Style Spec: solid deep navy background #0B1322 with generous negative space; white and cool neutral grays on deep navy; one locked gold accent #FFD75E; crisp editorial typography with restrained abstract terminal and engineering motifs; flat high-contrast illumination with sharp edges and no atmospheric haze; one dominant hook, asymmetric technical grid, thumbnail-legible hierarchy; exact solid text, short title, one-line support, no paragraph text; avoid neon glow, fog, bloom, decorative code walls, cursor glyphs, prompt symbols, code characters, pseudo-text, fake interface chrome, watermark, and multiple focal points.
Layout pattern: Hero title.
Composition and safe margins: Make "一个人，也能开源" the one unmistakable primary focal point, large and highly legible at thumbnail scale. Place "48,216 stars" as a clearly subordinate supporting line within the same unified typographic block, not as a competing focal point. Use an asymmetric technical grid and a single restrained symbolic hook suggesting one person connecting to an open-source network: one simple human-scale node or solitary point connected to a few abstract geometric nodes, entirely secondary to the title. Keep all text and meaningful geometry well inside generous safe margins, especially on the far left and right edges. Preserve abundant negative space.
Data and reference accuracy: The only data shown must be the exact metric "48,216 stars". The visual relationship should communicate one independent person enabling an open-source project with broad reach. No axes, charts, extra numbers, project names, labels, code, or invented metrics.
Global constraints: Exact visible text is mandatory and must remain readable. Use exactly one primary focal point. No extra logos, trademarks, watermarks, signatures, captions, decorative letters, pseudo-text, or marks readable as additional text. Use a valid 2.5:1 cover composition. Preserve factual accuracy. Complete the asset in one generation with no follow-up correction.
Avoid: multiple panels; multiple competing focal points; real or fake software screenshots; fake terminal windows or interface chrome; decorative code walls; source-code characters; cursor glyphs; prompt symbols; tiny labels; extra stars as text; badges; logos; mascots; photography; 3D rendering; gradients; glow; fog; bloom; clutter; edge-cropped text; any visible text beyond the two exact required strings.
Single-call instruction: Generate the entire final raster asset in exactly one built-in image_gen call.
Do not generate intermediate assets.
Use no retry, no edit, and no post-processing.
Do not crop, resize, pad, overlay, composite, repair, or re-encode the result.
Render all requested text and visual elements inside this single generation.
```

Style ID: `terminal-tech`

image_gen call count: 1

ImageGen edit call count: 0

Image modification command count: 0

Saved output path: `targets/codex/x-image/tests/acceptance/output/ac-01-cover-v2.png`

Actual dimensions: `1983 × 793`, ratio `2.500631:1`

Content QA: PASS — both exact strings appear once, the star value and unit are correct, no extra project data or visible text appears, and the lone-person-to-network relationship matches the fixture.

Style QA: PASS — deep navy, white/gray, one gold accent, clear hero hierarchy, abstract technical geometry, no terminal glyphs, no watermark, and no competing focal point.

P0 checklist: PASS — one generation, zero edits, zero modification commands, byte-identical original copy, exact text/data, no watermark or prompt leakage.

P1 checklist: PASS — readable at cover scale, single focal point, correct wide composition, and terminal-tech adherence.

P2 checklist: One advisory finding: secondary network strokes continue through the far-right edge without affecting meaning or text legibility.

## Attempt history

- Attempt 1: `FAIL` in `/root/ac01_cover`; output `ac-01-cover.png` contained forbidden `>_` glyphs.
- Regression: added `test_terminal_motifs_cannot_create_extra_glyphs`.
- Contract correction: commit `75d07a0 fix(x-image): prevent extra glyphs in terminal motifs`.
- Attempt 2: `PASS` in a fresh task; collision-safe output selected `ac-01-cover-v2.png`.
