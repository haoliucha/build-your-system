# QA Checklist

Inspect the original generated asset without editing it. QA is a release decision, not a repair loop.

## Required evidence

- Saved path exists and is the original generated file.
- Actual dimensions are reported when available.
- The tool trace shows that generation ran exactly once for this asset and that edit calls stayed at zero.
- The prompt, Style ID, host, and output path are recorded.
- Text, data, composition, style, and avoid constraints are checked.

## Severity

### P0 — Contract or factual failure

- Wrong, missing, invented, or unreadable required text.
- Wrong value, unit, category order, axis semantics, or causal relationship.
- More than one generation call for one asset.
- Any image modification after generation.
- Output file missing, overwritten, or not the selected original.

### P1 — Material visual failure

- Requested subject or intent is not represented.
- Main focal point is unclear.
- Required layout or ratio composition is materially wrong.
- Style ID is visibly violated.
- Data marks are blocked or distorted.
- A forbidden logo, watermark, fake interface, extra text, extra glyph, or pseudo-writing appears.
- A blank material surface contains ruled lines, grids, body-copy bars, placeholder blocks, question marks, or another text-like mark not in the exact visible text allowlist.

### P2 — Advisory issue

- Minor spacing, alignment, label placement, or stylistic imperfection that does not change meaning or legibility.

## Decision

P0 or P1 requires `FAIL without regeneration`. Preserve the asset, report every finding, and stop remaining assets in the same request.

P2 may pass with a documented observation.

Do not retry, edit, or repair inside the task. A new generation requires a new explicit user request.
