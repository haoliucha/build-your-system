# Final Prompt Contract

Compile the complete prompt before making the tool call. Do not improvise missing style, text, ratio, or data requirements after generation.

## Required schema

```text
Use case: <cover or illustration taxonomy>
Asset type: <X cover, article hero, inline explainer, vertical illustration, or share image>
Primary request: <one-sentence visual objective>
Source-derived content: <only facts and concepts supported by the source>
Exact visible text: "<every requested string quoted verbatim>"
Aspect ratio and target dimensions: <ratio plus prompt target>
Style ID: <built-in or task-local ID>
Full Style Spec: <background, palette, accent, medium, lighting, composition, text rules, avoid list>
Layout pattern: <one approved pattern>
Composition and safe margins: <focal point, hierarchy, whitespace, edge safety>
Data and reference accuracy: <values, units, category order, axis semantics, object relationships>
Global constraints: <non-overridable constraints>
Avoid: <asset-specific negative constraints>
Single-call instruction: <complete final raster in one call>
```

## Text and factual accuracy

Exact visible text must be quoted verbatim. Repeat tricky names character-by-character when useful. Do not add extra text.

Never place long article paragraphs inside the image. A cover uses one short title or hook and, only when useful, one short supporting line.

For data-led images, list every required category, all exact values, units, category order, and axis semantics. Do not invent missing values or imply precision absent from the source.

## Single-call instruction

Include this instruction verbatim in every final prompt:

```text
Generate the entire final raster asset in exactly one built-in image_gen call.
Do not generate intermediate assets.
Use no retry, no edit, and no post-processing.
Do not crop, resize, pad, overlay, composite, repair, or re-encode the result.
Render all requested text and visual elements inside this single generation.
```

After the call, copy or move the original generated file to the resolved collision-safe destination. Reading metadata and visually inspecting the original are allowed. Do not alter image bytes.

If the built-in tool is unavailable, stop and report the failure. Do not switch execution modes.
