# Domain conventions — CMS / HEP

Field-specific conventions the model cannot reliably guess. Every study's Phase-1
artifact includes a compliance table against this list.

## Units, notation, numbers

1. Energies/momenta/masses in **GeV** (label as `GeV` or `GeV/c^2` consistently).
2. Cross sections in pb or fb; luminosity in fb⁻¹, quoted to one decimal.
3. Known resonance masses from PDG (e.g. m_Z = 91.1876 GeV, m_J/ψ = 3.0969 GeV,
   m_H = 125.25 GeV); cite PDG when comparing peaks.
4. Limits quoted at **95% CL** using the **CLs criterion** unless the goal says
   otherwise; always report expected ±1σ/±2σ bands alongside observed.
5. Significances in σ; p-values one-sided unless stated.

## Plotting (matplotlib + mplhep)

6. Use `mplhep.style.CMS`; label `CMS Preliminary` (work-in-progress: add
   `Work in progress`), with √s and integrated luminosity stamp top-right
   (e.g. `59.7 fb⁻¹ (13 TeV)`).
7. Every axis labeled with quantity and unit; histogram y-axes state bin width
   (`Events / 2 GeV`).
8. Data as black points with Poisson (Garwood) error bars; MC/models as filled or
   line histograms; ratio panels where data/model are compared.
9. Uncertainty bands shown and labeled (stat / stat⊕syst).
10. Legends never overlap data; log-scale where distributions span >3 decades.
11. Every figure saved with a **sidecar JSON manifest** (same basename, `.plot.json`)
    conforming to `tools/plot_validator.py` schema — validation is impossible without it.
12. Colorblind-safe palette (Okabe–Ito or petroff10); never red/green as the only
    distinction.

## Analysis practice

13. **Blinding** per methodology; blinded windows shown as hatched/blank regions in
    any data plot spanning the SR.
14. Event weights: apply and document all provided weights; report both raw and
    weighted yields.
15. Multiple candidates per event: policy must be stated and bias-checked.
16. Efficiencies quoted with binomial (Clopper–Pearson) intervals.
17. Training uses signal MC vs **data sidebands** (not MC background) when the
    background is data-driven; document any deviation.
18. BDT/MVA scores reported in [0, 1]; raw margins may be kept internally.
19. Golden-JSON (certified-lumi) filtering applied to collision data when a
    certification mask is available; record which mask.
20. Random seeds fixed and logged for every stochastic step (training, toys,
    partial-unblinding subsample).

## Software

21. Allowed: numpy, scipy, awkward, uproot, hist/boost-histogram, matplotlib,
    mplhep, xgboost, scikit-learn, pyhf, iminuit, jinja2. **pandas is forbidden**
    (memory-hostile on jagged HEP data).
22. Statistical results only through `tools/stat_toolkit.py`; plots validated by
    `tools/plot_validator.py`; fits validated by `tools/shape_validator.py`.
23. ROOT files read with uproot only; never invoke ROOT/CMSSW binaries.
24. Study code lives in the study repo (`code/`), is runnable end-to-end via a
    single entry script per phase, and is committed with each phase artifact.

## Documentation

25. Analysis notes and the final letter in LaTeX (revtex or cms-tdr-like article
    class), built reproducibly (tectonic preferred, latexmk fallback).
26. Every number in the text must be regenerable from logged artifacts — no
    hand-typed results. This traceability is satisfied via the appendix of
    item 29, never via inline process references.
27. Citations resolve on INSPIRE-HEP; arXiv IDs included.
28. **Register**: analysis notes and papers are written for a physicist reader
    in standard collaboration style. Framework/process vocabulary is FORBIDDEN
    in title, abstract, body text, figure captions, and table captions —
    including but not limited to: "Human", "orchestrator", "analyst",
    "arbiter", "reviewer", "Category A/B/C", "iteration N", "verdict",
    "log entry", "chain hash", "manifest", "freeze vN", "obligation",
    "tier-1/tier-2", "work-order", "gate", "escalation". Decisions are stated
    in the collective analysis voice with their physics justification ("we
    adopt X because Y"); human rulings and review outcomes appear as ordinary
    analysis decisions. Standard physics usage of otherwise-reserved words
    (e.g. a "blinded" region, a fit "iteration" in the numerical sense) is
    fine — the test is whether a collaboration reader outside this framework
    would find the sentence normal.
29. **Reproducibility appendix**: the mapping from quoted numbers and
    decisions to experiment-log entries, artifact hashes, and code commits
    lives in one dedicated appendix ("Reproducibility record"), as tables.
    Body text carries no entry ids or hashes.
30. Process history (review iterations, remediations, adjudications) may be
    summarized in that appendix as an analysis-history note; it is never
    woven through the physics narrative.
