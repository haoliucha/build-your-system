# AC-05 — Data Editorial Image

Status: PASS

Codex task or thread: `/root/ac05_data_v2`

Input fixture: `targets/codex/x-image/tests/fixtures/data-article.md`

Exact Codex prompt:

```text
Use the native x-image skill. Read targets/codex/x-image/tests/fixtures/data-article.md and generate exactly one 16:9 data-led article image in data-editorial style. Preserve this exact descending order and exact labels: 阅读 42 分钟, 写作 31 分钟, 研究 18 分钟, 沟通 9 分钟. Data must dominate and total 100 分钟. Save the original output under targets/codex/x-image/tests/acceptance/output/ac-05-data.png. Do not generate any other asset.
```

Expected style: `data-editorial`

Expected ratio: `16:9`

Maximum permitted tool calls: 1 generation, 0 edits, 0 image modification commands

Final prompt:

```text
Use case: productivity-visual
Asset type: article hero
Primary request: Create one polished 16:9 data-led editorial article image showing exactly how a 100-minute focused-work session is divided among four categories; the data must be the dominant visual.
Source-derived content: A fictional 100-minute focused-work record has four categories in strict descending order: reading 42 minutes, writing 31 minutes, research 18 minutes, communication 9 minutes. These values sum exactly to 100 minutes. Do not add a fifth category and do not change the order.
Exact visible text: Render exactly these five strings, each exactly once and with no other visible text: "总计 100 分钟", "阅读 42 分钟", "写作 31 分钟", "研究 18 分钟", "沟通 9 分钟". Preserve every Chinese character, Arabic numeral, space, and the unit "分钟" verbatim. The four combined category-value-unit labels must appear top-to-bottom in exactly this descending order: "阅读 42 分钟", then "写作 31 分钟", then "研究 18 分钟", then "沟通 9 分钟".
Aspect ratio and target dimensions: 16:9 landscape composition, target 2048 × 1152 pixels.
Style ID: data-editorial
Full Style Spec: clean off-white #F7F5EF background; high-contrast deep-navy neutral data marks with one restrained cobalt-blue semantic accent used only for the highest-value bar; precise editorial data graphic with subtle restrained material depth; even, quiet lighting so shadows never alter a mark or baseline; ordered reading path and data-dominant composition; crisp modern sans-serif Chinese typography; exactly one complete combined label per category; no duplicate labeling. Avoid duplicate category labels, distorted axes, occluded marks, unlabeled decoration, fake interface chrome, watermark, multiple focal points.
Layout pattern: Data scene. Use a clean horizontal bar chart as the single focal point. Four bars share one exact zero baseline and encode values by proportional length: 42, 31, 18, 9. Bars run top-to-bottom in strict descending order. Place each required combined label once beside its corresponding bar, never splitting the label into separate category and value text. Place "总计 100 分钟" once as a compact summary above the plot, secondary to the bars.
Composition and safe margins: data occupies most of the canvas; generous outer safe margins of at least 8%; one strong centered chart block; wide readable spacing; no element touches or clips at an edge; labels have ample room and high contrast; secondary scene elements are absent.
Data and reference accuracy: The exact data is 阅读=42分钟, 写作=31分钟, 研究=18分钟, 沟通=9分钟; total=100分钟. Preserve category order top-to-bottom as 阅读, 写作, 研究, 沟通. Use a truthful common zero baseline and strictly proportional bar lengths so 42 > 31 > 18 > 9. No axis is required; if no axis is shown, do not imply any other scale. Do not invent values, percentages, categories, legends, dates, or annotations.
Global constraints: exact required text must be legible and factually correct; exactly four data marks; one primary focal point; no extra logos, branding, watermark, signatures, interface controls, decorative dashboard panels, fake UI chrome, people, objects, icons, paragraphs, title, subtitle, legend, axis labels, or extra text. The 16:9 ratio is a composition requirement. Do not obscure, distort, tilt, curve, or apply perspective to any bar or label.
Avoid: duplicate text; split or repeated labels; a fifth category; wrong characters; wrong digits; missing spaces; missing units; wrong order; equal-length or inaccurately scaled bars; 3D perspective; gradients that change perceived bar lengths; clutter; tiny typography; clipped text; decorative illustrations.
Single-call instruction: Generate the entire final raster asset in exactly one built-in image_gen call.
Do not generate intermediate assets.
Use no retry, no edit, and no post-processing.
Do not crop, resize, pad, overlay, composite, repair, or re-encode the result.
Render all requested text and visual elements inside this single generation.
```

Style ID: `data-editorial`

image_gen call count: 1

ImageGen edit call count: 0

Image modification command count: 0

Saved output path: `targets/codex/x-image/tests/acceptance/output/ac-05-data-v2.png`

Actual dimensions: `1672 × 941`, approximately `16:9`

Content QA: PASS — the five allowed strings appear exactly once; four categories, values, units, descending order, shared baseline, and total 100 are correct; no fifth category or extra labeling appears.

Style QA: PASS — off-white editorial field, deep-navy bars, cobalt accent on the leading category, restrained depth, strong typography, and data-dominant composition.

P0 checklist: PASS — one generation, zero edits, zero modification commands, byte-identical original, exact data, no invention, watermark, or prompt leakage.

P1 checklist: PASS — readable honest chart, correct order and proportionality, correct ratio intent, and data-editorial adherence.

P2 checklist: Actual output is `1672 × 941` rather than the prompt target, while remaining effectively 16:9 and fully legible.

## Attempt history

- Attempt 1: `FAIL` in `/root/ac05_data`; `ac-05-data.png` duplicated each category as a standalone axis label.
- Regression: added `test_data_labels_use_one_nonduplicated_labeling_method`.
- Contract correction: commit `c946236 fix(x-image): prevent duplicate data labels`.
- Attempt 2: `PASS` in a fresh task; collision-safe output selected `ac-05-data-v2.png`.
