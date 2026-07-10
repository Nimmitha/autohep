---
name: review-board
description: Convene the multi-agent review board on a phase artifact and return the arbiter's verdict. Used by run-phase; can also be invoked standalone to re-review an artifact.
---

# review-board

Reviews one phase artifact and produces a single arbiter verdict.

## Steps

1. Identify the artifact and its phase from the caller (or `manifest.json`).
2. Run the programmatic validators FIRST (they are cheap and their red flags are
   non-negotiable):
   - `python tools/plot_validator.py <all figures of the phase> --json`
     (add `--unblinded` only if manifest says the study is past 4b)
   - `python tools/shape_validator.py <fit records>` for phases with fits
   - `python tools/experiment_log.py verify studies/<name>`
3. Launch reviewer agents **in parallel** (single message, multiple Agent calls):
   - **reviewer-physics** — give it ONLY the artifact, figures, study code, and
     `PHYSICS_GOAL.md`. Never give it methodology.md (its independence is the point).
   - **reviewer-critical** — artifact + methodology + conventions + log access.
   - **reviewer-constructive** — artifact + methodology + conventions + corpus.
   - Phases 4a/5 additionally: **reviewer-rendering** (compiled PDF + build log)
     and **validator-bibtex** (.bib + sources).
4. Log each reviewer's findings (`review_finding` entries, one per reviewer, with
   the full findings block in detail).
5. Launch the **arbiter** with: all findings blocks verbatim + the raw validator
   JSON. Do not editorialize or filter before the arbiter sees them.
6. Log the verdict (`review_verdict`) and return the arbiter's output block
   verbatim to the caller.

Red-flag rule (enforced here as well as in the arbiter): if step 2 produced any
R-check finding, the verdict cannot be PASS regardless of what reviewers say.
