# Study repository

Created by autohep `init-study`. Layout:

- `PHYSICS_GOAL.md` — the study's only analysis-specific input
- `manifest.json` — phase state, blinding definition, frozen decisions
- `EXPERIMENT_LOG.jsonl` — append-only audit trail (hash-chained; verify with
  `python <autohep>/tools/experiment_log.py verify .`)
- `phases/phase1..phase5/` — gated artifacts (STRATEGY.md, EXPLORATION.md,
  SELECTION.md, analysis notes, paper)
- `code/` — study-local analysis code, one runnable entry script per phase
- `data/` — user/, opendata/, derived/ (all gitignored)
- `.claude/settings.json` — clean-room deny rules

Process rules live in the framework repo: `framework/methodology.md`.
