# Style Policy

Compile a complete Style Spec before compiling the final image prompt.

## Merge order

Use this precedence exactly:

`explicit user request > asset intent > content semantics > default preset`

An explicit request may select a built-in preset or create a custom Style Spec. Asset intent selects cover versus explanatory treatment. Content semantics selects technology, general editorial, data-led, tactile-system, or spatial-mechanism emphasis. The default preset is `editorial-material`.

Global hard constraints are non-overridable. They apply after the style merge as a final validation layer. A custom style cannot disable legibility, factual accuracy, one-call generation, no retry, no post-processing, ratio safety, exact visible text, one primary focal point, or the ban on extra logos and watermarks.

## Built-in routing

- `terminal-tech`: technology covers, open-source projects, product engineering, developer tools.
- `editorial-material`: explainers, processes, education, humanities, and general article illustrations.
- `data-editorial`: rankings, trends, metrics, comparisons, and chart-led visuals.
- `tactile-systems`: causal loops, operating models, relationship-dense process maps, and systems whose topology should feel physically constructed.
- `isometric-systems`: pipelines, architectures, mechanisms, and operational flows where spatial structure explains how the system works.

Use `editorial-material` for a general process illustration with one focal object or flow. Use `tactile-systems` when the complete network, loop, branch, or phased model is the focal point. Use `isometric-systems` only when spatial or mechanical relationships materially improve the explanation. Use content semantics to choose among the five presets unless the user explicitly requests another style.

The default preset remains `editorial-material`.

## Natural-language aliases

- `纸张材料风` and `纸片系统图` route to `tactile-systems`.
- `等距机械装置` and `等距机械风` route to `isometric-systems`.

Treat these aliases as explicit built-in style selections, not task-local custom styles.

## Consistency for multiple assets

Use a locked style across a set. Lock the following before the first call:

- Style ID
- accent color
- material and lighting
- label treatment
- composition density

Change only the layout pattern and source-derived content needed for each asset.

## Custom styles

Normalize an explicit custom request into the same fields used by a built-in preset:

`id`, `use-for`, `background`, `palette`, `accent`, `medium`, `lighting`, `composition`, `text-rules`, and `avoid`.

Name it `custom-<short-slug>`. It is a task-local Style Spec and does not modify the built-in presets. Validate it against global hard constraints before use.
