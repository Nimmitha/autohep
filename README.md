# autohep

An autonomous rare-decay analysis framework for high energy physics, modeled on
**JFC** ("Just Furnish Context", [arXiv:2603.20179](https://arxiv.org/abs/2603.20179)):
Claude Code executes complete searches — data reconnaissance, autonomous
cut/feature discovery, ML discriminants, blinded statistical inference, paper
drafting — given only a minimal physics goal and data locations. The framework
carries no channel-specific physics; each analysis lives in its own git repo
under `studies/`.

## How it works

| JFC layer | here |
|---|---|
| Methodology | `framework/methodology.md` — 7-phase gated workflow with a hard human unblinding gate |
| Domain conventions | `framework/conventions.md`, `framework/scaling.md` |
| Agent behavior | `.claude/agents/` — orchestrator, analyst, 4 reviewers, BibTeX validator, arbiter |
| Programmatic validation | `tools/plot_validator.py` (35 checks), `shape_validator.py`, `stat_toolkit.py` |
| Literature RAG | `corpus/ingest.py` + `corpus/search.py` over arXiv LaTeX sources |
| Audit trail | hash-chained `EXPERIMENT_LOG.jsonl` per study (`tools/experiment_log.py`) |

Phases: 1 Strategy → 2 Exploration → 3 Processing → 4a Expected results →
**4b Partial unblinding (human gate)** → 4c Full unblinding → 5 Documentation.
Each phase artifact must pass the review board (physics / critical / constructive
reviewers + validators, synthesized by an arbiter into PASS / ITERATE / ESCALATE).

## Quick start

```bash
# environment (pixi.toml is the portable spec; local conda equivalent:)
mamba create -n autohep python=3.11 pip
~/miniconda3/envs/autohep/bin/pip install uproot awkward hist matplotlib mplhep \
    pyhf iminuit xgboost scikit-learn scipy jinja2 pytest requests

# trusted-tools test suite
~/miniconda3/envs/autohep/bin/python -m pytest tests/ -q

# build the literature corpus (rate-limited; ~1 h for the full seed list)
~/miniconda3/envs/autohep/bin/python corpus/ingest.py --id-file corpus/papers/seed_papers.txt
~/miniconda3/envs/autohep/bin/python corpus/search.py "rare Higgs decay quarkonium"

# start a study (in Claude Code)
#   /init-study     — scaffold a new study repo; supply goal + data paths
#   /run-phase      — advance the study one gated phase
#   /acquire-data   — open-data download / CRAB config generation
```

## Data routes

- **User-provided ntuples** (collaboration data, signal MC): drop under
  `studies/<name>/data/user/`; the agent infers branch semantics itself
  (`tools/ntuple_probe.py`) — no schema is given by design.
- **CMS Open Data**: `tools/opendata.py` searches/downloads 2016 UL NanoAOD
  (uproot-readable, no CMSSW) and applies golden-JSON lumi filtering.
- **CRAB**: `tools/crab_configgen.py` emits ready-to-submit configs for the
  human to run on LPC/lxplus — the framework never authenticates to the grid.

## Guarantees

- Blinding is structural: plot manifests are validated against the frozen
  blinded window; violations are non-downgradable Category A findings.
- Every number is traceable: append-only, hash-chained experiment log.
- Statistics only via `stat_toolkit` (pyhf CLs limits, Asimov bands, saturated
  GoF, signal-injection tests) — never ad hoc.
