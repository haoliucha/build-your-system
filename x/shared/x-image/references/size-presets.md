# Size Advisor

Treat ratio as a composition instruction and pixels as a target written into the prompt.

| Intended use | Ratio | Prompt target |
|---|---:|---:|
| X article cover | 2.5:1 | 2400 × 960 |
| Article hero | 16:9 | 2048 × 1152 |
| Inline explainer | 3:2 | 1536 × 1024 |
| Vertical illustration | 3:4 | 1536 × 2048 |
| Share image | 1:1 | 2048 × 2048 |

Selection order:

1. A valid explicit user ratio.
2. The intent preset.
3. Inline explainer `3:2` when the intent remains ambiguous after source analysis.

A user ratio overrides the intent preset when it is at most 3:1.

Reject ratios wider than 3:1 and recommend the nearest valid alternative. Do not spend an image call until the ratio is valid.

The ratio is a composition requirement.

The pixel dimensions are prompt targets, not guaranteed built-in ImageGen output.

Never crop, resize, pad, or re-encode the result to force dimensions.

Always report actual dimensions when available. If dimensions cannot be read without modifying the file, report them as unavailable.
