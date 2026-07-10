# Methodology — the phase-gated analysis workflow

This document encodes how a rare-decay search is conducted, mirroring the institutional
knowledge normally transmitted verbally to graduate students. Every study follows these
phases in order. A phase is complete only when (a) its written artifact exists in the
study repo, (b) the review board has issued PASS via the arbiter, and (c) the experiment
log records the verdict. The orchestrator never advances past an incomplete phase.

Throughout: "SR" = signal region, "SB" = sideband/control regions. All work before
Phase 4b is **blinded** — the SR in data is never inspected.

---

## Phase 1 — Strategy → `phases/phase1/STRATEGY.md`

Inputs: `PHYSICS_GOAL.md` only (plus the literature corpus).

1. **Literature survey.** Query `corpus/search.py` for reference analyses of the same
   or adjacent final states (same resonances, similar topology, analogous rare-decay
   limits). Produce a reference-analysis table: experiment, dataset, selection
   philosophy, background strategy, statistical method, result.
2. **Signal & background hypotheses.** State the decay chain, expected final-state
   objects, dominant backgrounds (combinatorial, resonant, mis-ID) and how each is
   expected to be constrained.
3. **Region plan.** Define, in terms of physics variables (not yet branch names):
   the SR (e.g. a window in the candidate invariant mass), SBs for background
   modeling, and validation regions. **Freeze the blinding definition here** and
   record it in `manifest.json`.
4. **Selection strategy sketch.** Which classes of variables will be considered for
   cuts and for the multivariate discriminant, and the optimization figure of merit
   (default: Punzi significance for discovery-style, expected-limit for limit-style).
5. **Systematics program.** Enumerate anticipated systematic uncertainties and how
   each will be evaluated or bounded.
6. **Conventions compliance table.** One row per item of `framework/conventions.md`,
   stating how the study will comply.

## Phase 2 — Exploration → `phases/phase2/EXPLORATION.md`

Inputs: the data paths in `PHYSICS_GOAL.md`. Work on ~1000-event slices
(`framework/scaling.md`).

1. **Ntuple reconnaissance.** Run `tools/ntuple_probe.py` on every input file class
   (data, signal MC, any others). No branch schema is provided — infer branch
   semantics from names, types, ranges, and distributions. Record the inferred data
   dictionary (branch → meaning, unit, confidence) in the artifact. Mark
   low-confidence inferences explicitly; they are review items.
2. **Peak finding.** Locate expected resonances (probe reports candidate peaks).
   Verify masses against known values; discrepancies are red flags (mis-inferred
   units or branches).
3. **Region feasibility.** Check the Phase-1 region plan against reality: SB
   populations, SR width vs resolution, signal MC coverage.
4. **Candidate discriminating variables.** Rank branches by separation between
   signal MC and data SB (never data SR). Record the ranked list with plots.
5. **Data-quality checks.** NaN/inf rates, out-of-range values, duplicate events,
   year/era consistency if applicable.

## Phase 3 — Processing → `phases/phase3/SELECTION.md`

1. **Candidate building.** Implement the event/candidate selection in study-local
   code (uproot/awkward). If multiple candidates per event are possible, choose and
   justify a per-event candidate policy (e.g. best-χ² or all-candidates) and check
   its bias on signal MC.
2. **Cut discovery protocol (mandatory).** For every proposed cut:
   - a literature-grounded or physics-grounded rationale (cite corpus hits);
   - a `tools/cut_scan.py` scan: figure of merit vs cut value, plus N-1 efficiency;
   - the chosen value with signal efficiency and SB rejection at that value;
   - stability note: does the optimum move under reasonable variations?
   **A cut asserted without scan evidence is a Category A review finding.** Beware
   the documented failure mode of over-tight cuts: report signal efficiency of the
   full selection and flag any single cut costing >20% signal efficiency.
3. **Multivariate discriminant.** Train XGBoost (or justify an alternative) with
   signal MC vs data SB. Requirements: train/test split or k-fold with overtraining
   check (test-vs-train score distributions), feature-importance table, and a score
   mapped to [0, 1]. The discriminant must not use the blinded variable (or anything
   trivially correlated with it) unless the strategy explicitly fits the score
   dimension — in that case demonstrate decorrelation or model the correlation.
4. **Background estimation.** Data-driven from SBs where possible. Closure test on
   a validation region or on MC. Document the extrapolation assumption SB → SR.
5. **Stress tests.** Vary SB definitions, candidate policy, and binning; show the
   background estimate is stable within quoted uncertainties.

## Phase 4a — Expected results → `phases/phase4/ANALYSIS_NOTE_v1.pdf` (+ `.md` source)

Still fully blinded.

1. **Shape models.** Scan candidate signal and background parameterizations; every
   kept fit must pass `tools/shape_validator.py` (convergence, covariance quality,
   pulls, refit stability). Record rejected models and why.
2. **Statistical model.** Build the likelihood in `tools/stat_toolkit.py` primitives
   (pyhf binned, or scipy/iminuit unbinned). Include systematics as nuisances with
   the Phase-1 program; document any dropped systematic.
3. **Expected sensitivity.** Asimov expected 95% CL upper limit with ±1σ/±2σ bands.
4. **Signal injection.** Inject known signal strengths, verify unbiased recovery.
5. **Goodness of fit.** Saturated-model GoF on SBs (never a naive χ²/ndf on sparse
   bins — this is a known failure mode).
6. **Fit diagnostics.** Nuisance pulls and impacts on an Asimov fit.
7. Assemble the first complete analysis note (all sections, all plots validated by
   `tools/plot_validator.py`).

## Phase 4b — Partial unblinding (HUMAN GATE)

The orchestrator **stops** and presents the human with a structured approval request:

**Unblinding checklist** (all items must be answered in the request):
1. Background model validated in SBs with closure and GoF results attached.
2. Expected limit and bands frozen and logged before any data SR access.
3. Selection, discriminant, shape models, and binning frozen in `manifest.json`
   (hash logged); no further tuning permitted after unblinding.
4. Signal-injection tests passed.
5. All review-board Category A findings resolved.
6. Statement of what will be looked at first (the 10% subsample) and the criteria
   for proceeding to 4c (e.g. observed within expected bands or a documented plan).

Upon written human approval (logged), unblind a **10% random, reproducibly seeded
subsample** of the SR. Compare with expectation; report in `phases/phase4/PARTIAL_UNBLINDING.md`.

## Phase 4c — Full unblinding

Only after 4b results are reviewed and the human approves continuation. Full-dataset
observed result, consistency check against the 4b subsample and the expected bands.
Any post-unblinding change to selection or models is forbidden; if something is broken,
document it, revert to blinded state, and ESCALATE.

## Phase 5 — Documentation → `phases/phase5/paper/main.pdf`

Journal-letter format LaTeX (build with tectonic, or latexmk fallback). Passes:
rendering reviewer (compiled-PDF inspection), BibTeX validator (citations resolve on
INSPIRE-HEP), plot validator on all final figures. Includes: abstract with the numeric
result, analysis strategy, selection with efficiency table, background model,
systematics table, statistical procedure, result with expected/observed comparison.

---

## The review loop (all phases)

1. Analyst produces the phase artifact.
2. The review board convenes (see `.claude/skills/review-board/`): physics reviewer,
   critical reviewer, constructive reviewer run in parallel; plot validator runs
   programmatically on every figure; rendering reviewer and BibTeX validator join in
   Phase 4a/5.
3. Findings are classified: **Category A** (blocking — wrong physics, blinding
   violation, missing scan evidence, validator red flag), **Category B** (important,
   fix before next phase), **Category C** (minor).
4. The **arbiter** synthesizes and issues one of:
   - **PASS** — no open A findings; B findings have committed fixes; advance.
   - **ITERATE** — bounded at 3 iterations per phase; each iteration addresses
     findings and re-reviews.
   - **ESCALATE** — pause for the human: unresolved A findings after 3 iterations,
     any blinding question, any request to alter frozen decisions.
5. Verdict + findings are logged to `EXPERIMENT_LOG.jsonl`.

## Log discipline

Use `tools/experiment_log.py append` for: phase start/end, every decision (with
alternatives considered), every tool invocation that produced an artifact (with file
hash), every review verdict, every human interaction. The log is the audit trail that
makes autonomy verifiable.
