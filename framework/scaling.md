# Compute scaling rules

This framework runs on a single WSL2 machine (no SLURM, no batch tier). Size all
work accordingly.

1. **Prototype first.** Develop every processing step on a ~1000-event slice
   (`uproot.iterate` with `entry_stop`) before touching the full dataset. Phase 2
   runs entirely on slices.
2. **Single core** for anything expected under ~2 minutes.
3. **`concurrent.futures.ProcessPoolExecutor`** (≤ physical cores − 2) for jobs of
   2–15 minutes: per-file candidate building, toy ensembles, cut-scan grids.
4. Anything projected beyond ~30 minutes on this machine: reduce scope (fewer toys,
   coarser scan, event subsample) and state the reduction in the artifact, or
   ESCALATE to the human with a cost estimate. Never silently run multi-hour jobs.
5. **Toys budget.** Expected-limit bands via Asimov (cheap) by default; toy-based
   confirmation limited to ≤1000 toys unless the human approves more.
6. **XGBoost** training capped at `n_jobs = cores − 2`; datasets above ~5M rows are
   subsampled for hyperparameter search, full-fit only for the final model.
7. **Memory**: stream files with `uproot.iterate`; never materialize full datasets
   with all branches. Read only needed branches.
8. Intermediate arrays cached as `.npz` under the study's `data/derived/` (gitignored),
   keyed by a hash of selection version — recompute, don't trust stale caches after
   selection changes.
