# FitCoach AI assembly guide

English source and compiled PDF: `fitcoach-user-manual.tex` and `fitcoach-user-manual.pdf`.

Build from this directory, twice:

```powershell
xelatex -interaction=nonstopmode -halt-on-error fitcoach-user-manual.tex
xelatex -interaction=nonstopmode -halt-on-error fitcoach-user-manual.tex
```

Keep `../assets/fitcoach-ui-en-16x9.png` available. All diagrams are native TikZ and remain editable.

Baseline: integration commit 9152fe896a05b066cb573930419bf128e4f6158e. Dedicated local branch: Docs-Assembly-Guide-Yancheng. The separate integration checkout was not modified.

Version 1.1 follows the FitCoach application design: cream surfaces, sky-blue module cards, terracotta accents, rounded status chips, the existing FitCoach athlete symbol and italic wordmark, and the product tagline. The requested A4 template remains a structural reference. The document uses original page/diagram code and contains no team logos, wordmarks or sample robotics program. External component reference photographs are bundled with source attribution in parts/SOURCES.md.

Validation: XeLaTeX twice; no overfull boxes; PDF pages rendered and inspected. Hardware was not connected or retested for this documentation task.

## Integration note

Merged from `Docs-Assembly-Guide-Yancheng` into the integrated application without rewriting its source commit. The bundled PDF is version 1.2 (12 November 2026), rebuilt with verified live IMU acquisition results. See the [current project README](../../README.md) and [unified application guide](../../app/UNIFIED_APP.md) for the six-movement library, live page and module/session controls. Rebuilding the source uses the current dashboard screenshot from `../assets/`. No hardware acceptance is implied by this merge.
