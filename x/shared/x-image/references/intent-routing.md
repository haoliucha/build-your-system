# Intent Routing and Output Contract

Resolve the request before compiling a prompt or calling any image tool.

## Accepted source types

- File: read the named Markdown, text, or data file.
- Directory: choose `publish.md`, then `draft.md`, then the only Markdown file. If multiple candidates remain, ask one concise source-location question.
- Direct text: use the supplied article or passage.
- Data: preserve the named categories, exact values, units, order, and axis meaning.
- Brief: treat the user's description as the source.

## Intent and count

Path-only requests default to exactly one cover.

Explicit cover or illustration language overrides the path-only default. Cover terms include `封面` and `cover`. Illustration terms include `插图`, `配图`, `解释图`, and `illustration`.

Illustration requests without a count default to exactly one strongest cognitive anchor. Select the concept that most improves understanding; do not create a generic decorative scene.

An explicit count creates one independent asset plan per requested image. Keep one locked style across the set and give every asset a distinct cognitive job.

## Destination resolution

A user-provided destination wins.

File sources save to a sibling `images/` directory.

Directory sources save to `<source-directory>/images/`.

Direct text, data, and brief inputs save to `<current-working-directory>/images/`.

Default filenames:

- Cover: `cover.png`
- Illustration: `illustration-01-<short-slug>.png`
- Further illustrations: increment the two-digit index.

Never overwrite an existing asset. Probe the full destination path before copying. If the name exists, try `-v2`, then `-v3`, and continue until the first unused filename is found.

Only create the selected final output directory. Do not create raw, thumbnail, crop, intermediate, or repair directories.

## Failure and multi-image behavior

Plan all requested assets before the first call, then execute them in order.

Stop remaining calls after the first failed asset. A tool failure, unavailable output, P0 finding, or P1 finding counts as a failed asset.

Preserve every completed original asset. Also preserve the failed original when a file exists, report its QA failure, and do not repair or regenerate it.

Never upload, publish, modify the source article, or perform X account actions.
