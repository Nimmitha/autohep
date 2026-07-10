---
name: init-study
description: Create a new per-study repository from templates/study/ — one fresh, isolated git repo per physics question. Use when the user asks to start a new analysis/search/measurement.
---

# init-study

Creates `studies/<study-name>/` as an independent git repository.

## Steps

1. Ask the user (if not provided): study name (kebab-case), the physics goal
   (1–3 sentences: process, dataset, deliverable), and data locations.
2. Copy `templates/study/` to `studies/<study-name>/`. Do NOT symlink the
   template — copy, so studies never share mutable state.
3. Fill `PHYSICS_GOAL.md`: the goal verbatim, √s and luminosity if known, data
   paths, and the optional one-paragraph provenance note the user supplies.
   Do not add analysis hints — the whole point is that strategy is derived
   autonomously.
4. Initialize `manifest.json`:
   ```json
   {"study": "<name>", "created": "<ISO date>", "phase": "phase1",
    "iteration": 0, "blinded": true, "blinded_window": null,
    "frozen": {}, "framework_commit": "<git rev-parse HEAD of autohep>"}
   ```
5. Write clean-room deny rules so the study cannot read external analysis code.
   Sessions load settings from the directory they start in, so the rules must be
   in BOTH `<autohep>/.claude/settings.json` (sessions start at the framework
   root) and the study's own `.claude/settings.json` (defense in depth), e.g.:
   ```json
   {"permissions": {"deny": [
       "Read(//home/nimmitha/LPCfiles/run2/**)",
       "Read(//home/nimmitha/.claude/projects/**)",
       "Read(//home/nimmitha/.claude/plans/**)"
   ]}}
   ```
   Add any extra paths the user names as prior-knowledge sources to exclude.
   Also verify no ancestor directory of the framework carries a CLAUDE.md that
   describes the analysis being reproduced (ancestor CLAUDE.md files are
   auto-loaded into every session).
6. `git init` inside the study dir, first commit ("study scaffold"), and log the
   creation: `python tools/experiment_log.py append studies/<name> --kind note
   --agent orchestrator --summary "study initialized"`.
7. Report the study path and remind the user data payloads are gitignored.

Data files (`*.root`) go under `studies/<name>/data/` — either copied by the user
or acquired via the acquire-data skill. Never modify `templates/`.
