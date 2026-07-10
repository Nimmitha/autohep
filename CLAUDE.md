# autohep — Autonomous Rare-Decay Analysis Framework

autohep is a JFC-style ("Just Furnish Context", arXiv:2603.20179) framework in which
Claude Code autonomously executes rare-decay searches in high energy physics data. The
framework carries **no channel-specific physics**. Each analysis (a "study") is defined
only by a minimal physics goal and data locations, lives in its **own git repository**
under `studies/`, and advances through a phase-gated workflow policed by a multi-agent
review board.

## The three context layers

1. **Methodology** — `framework/methodology.md`. The 7-phase workflow every study
   follows, including the mandatory cut/feature-discovery protocol and the unblinding
   checklist. Read it before doing any analysis work.
2. **Domain conventions** — `framework/conventions.md`. CMS/HEP conventions: plot
   style, units, naming, blinding rules, allowed libraries. `framework/scaling.md`
   sets compute rules for this machine.
3. **Agent behavior** — `.claude/agents/*.md`. Strict specs for what each agent
   receives and must output. The physics reviewer is deliberately denied the
   methodology documents.

## Hard rules (non-negotiable)

- **Blinding**: never look at, plot, count, or fit data in the signal region before
  the human unblinding gate (Phase 4b) is approved. Blinded-region definitions are
  frozen in the study's `STRATEGY.md` and `manifest.json`.
- **Experiment log**: every phase action, decision, review verdict, and artifact is
  appended to the study's `EXPERIMENT_LOG.jsonl` via `tools/experiment_log.py`.
  The log is append-only; never edit or delete existing entries.
- **Trusted tools**: statistical inference, cut scans, and validation run through
  `tools/` — never re-implement a CLs limit, significance scan, or goodness-of-fit
  ad hoc. Analysts may write analysis code freely; they may not bypass validators.
- **Every cut needs scan evidence**: a selection cut without a `cut_scan` study in
  `SELECTION.md` is a Category A (blocking) review finding.
- **Red flags stand**: `plot_validator` red-flag findings are Category A and the
  arbiter is forbidden from downgrading them.
- **Study isolation**: a study reads only its own repo, `framework/`, `tools/`,
  and `corpus/`. It must not read other studies or any external analysis code.
- **Framework changes are human-gated**: `tools/`, `framework/`, `.claude/`,
  `templates/`, `tests/`, and corpus code are under ask-rules — every edit
  requires an interactive human approval. Before requesting one, ESCALATE with
  (a) a minimal reproduction, (b) the proposed patch, and (c) the study-side
  impact, and wait for the human's go-ahead. An approved fix MUST ship with a
  regression test, pass the full suite (`pytest tests/ -q`), be committed to
  the FRAMEWORK repo (never the study repo), and be followed by the study
  re-pinning `framework_commit` in its manifest with the escalation → fix →
  re-pin trail logged. Never weaken a validator or blinding check to make a
  review pass — that is a Category A violation regardless of approval.
- **No pandas.** Arrays are numpy/awkward; histograms are hist/boost-histogram.

## Layout

- `framework/` — methodology, conventions, scaling (the context layers)
- `.claude/agents/` — orchestrator, analyst, 4 reviewers, bibtex validator, arbiter
- `.claude/skills/` — init-study, run-phase, review-board, acquire-data
- `tools/` — trusted instruments (unit-tested; run `pytest tests/ -q`)
- `corpus/` — literature ingestion + hierarchical retrieval (`corpus/search.py`)
- `templates/study/` — scaffold for new study repos
- `studies/<name>/` — per-study git repos (gitignored here; each is its own repo)

## Environment

Declared in `pixi.toml`. On this host use the conda env `autohep`:
`/home/nimmitha/miniconda3/envs/autohep/bin/python`. Stack: uproot/awkward/hist,
XGBoost, pyhf + scipy/iminuit, matplotlib+mplhep, LaTeX. No ROOT, no TMVA, no Combine.

## Starting a study

```
python tools/experiment_log.py --help          # log discipline
.claude/skills/init-study                       # scaffolds studies/<name>/ as a fresh git repo
```
Then follow `framework/methodology.md` Phase 1. Data acquisition options (user-provided
ntuples, CMS Open Data, CRAB config generation for the human) are in the acquire-data
skill and `tools/opendata.py` / `tools/crab_configgen.py`.
