#!/usr/bin/env python3
"""Trusted statistical instruments. All inference in a study goes through here —
never re-implement limits, significances, or GoF ad hoc.

Binned path (primary): pyhf models, CLs upper limits with Asimov expected bands,
saturated-model goodness of fit, signal-injection bias tests.
Unbinned path: thin iminuit wrapper that returns a fit record in the
shape_validator schema.

Conventions: limits at 95% CL with the CLs criterion; expected bands are the
(-2σ, -1σ, median, +1σ, +2σ) quantiles.
"""
from __future__ import annotations

import json
import math

import numpy as np


# ---------------------------------------------------------------------------
# binned models (pyhf)
# ---------------------------------------------------------------------------

def _pyhf():
    try:
        import pyhf
    except ImportError as e:
        raise ImportError(
            "pyhf is required for binned inference; install the autohep env "
            "(see pixi.toml)") from e
    pyhf.set_backend("numpy")
    return pyhf


def build_model(signal, background, bkg_uncert=None):
    """One-channel model: signal (mu-scaled) + background with optional
    per-bin uncorrelated background uncertainty (shapesys)."""
    pyhf = _pyhf()
    signal = list(map(float, signal))
    background = list(map(float, background))
    bkg_modifiers = [{"name": "mu", "type": "normfactor", "data": None}]
    bkg_sample = {"name": "background", "data": background, "modifiers": []}
    if bkg_uncert is not None:
        bkg_sample["modifiers"].append(
            {"name": "bkg_uncert", "type": "shapesys",
             "data": list(map(float, bkg_uncert))})
    spec = {"channels": [{
        "name": "sr",
        "samples": [
            {"name": "signal", "data": signal, "modifiers": bkg_modifiers},
            bkg_sample,
        ]}]}
    return pyhf.Model(spec)


def upper_limit(signal, background, data=None, bkg_uncert=None,
                mu_max=None, n_scan=61) -> dict:
    """95% CL CLs upper limit on mu.

    data=None -> blinded: expected limits from the background-only Asimov.
    Returns {"expected": [-2s,-1s,median,+1s,+2s], "observed": float|None,
             "scan_max": float}.
    """
    pyhf = _pyhf()
    model = build_model(signal, background, bkg_uncert)
    bkg = np.asarray(background, float)
    sig = np.asarray(signal, float)
    if mu_max is None:
        # heuristic scan ceiling: mu at which s ~ 5*sqrt(b+1) in the best bin
        with np.errstate(divide="ignore", invalid="ignore"):
            r = np.where(sig > 0, 5.0 * np.sqrt(bkg + 1.0) / np.maximum(sig, 1e-12), np.inf)
        mu_max = float(min(max(2.0 * np.nanmin(r), 1.0), 1e4))
    observed_data = (list(map(float, data)) if data is not None
                     else list(bkg)) + model.config.auxdata
    scan = np.linspace(0.0, mu_max, n_scan)
    # widen the POI bound: pyhf's default normfactor bound (0, 10) must not
    # clip the scan or the MLE
    bounds = [list(b) for b in model.config.suggested_bounds()]
    bounds[model.config.poi_index] = [0.0, float(mu_max) * 2.0]
    obs, exp = pyhf.infer.intervals.upper_limits.upper_limit(
        observed_data, model, scan, level=0.05, par_bounds=bounds)
    result = {
        "expected": [float(x) for x in exp],
        "observed": float(obs) if data is not None else None,
        "scan_max": mu_max,
        "cl": 0.95, "criterion": "CLs",
    }
    # warn if the limit railed against the scan ceiling
    if result["expected"][2] > 0.95 * mu_max:
        result["warning"] = "expected limit at scan ceiling — increase mu_max"
    return result


def asimov_significance(s, b) -> float:
    """Median discovery significance, Cowan et al. Asimov formula (per-bin sum
    in quadrature)."""
    s = np.asarray(s, float)
    b = np.asarray(b, float)
    ok = (b > 0) & (s > 0)
    z2 = 2.0 * ((s[ok] + b[ok]) * np.log1p(s[ok] / b[ok]) - s[ok])
    return float(np.sqrt(z2.sum()))


def saturated_gof(observed, expected, n_fitted_params=0) -> dict:
    """Saturated-model likelihood-ratio GoF for binned Poisson counts.

    -2 ln λ = 2 Σ [ e_i - o_i + o_i ln(o_i/e_i) ]  (o_i ln term -> 0 when o_i = 0)
    p-value from chi2 with ndof = nbins - n_fitted_params.
    """
    from scipy.stats import chi2 as _chi2

    o = np.asarray(observed, float)
    e = np.asarray(expected, float)
    if o.shape != e.shape:
        raise ValueError("observed/expected shape mismatch")
    if np.any(e <= 0):
        raise ValueError("expected counts must be positive in every bin")
    with np.errstate(divide="ignore", invalid="ignore"):
        term = np.where(o > 0, o * np.log(o / e), 0.0)
    tstat = float(2.0 * np.sum(e - o + term))
    ndof = int(o.size - n_fitted_params)
    if ndof <= 0:
        raise ValueError("non-positive ndof — model has too many parameters")
    return {"method": "saturated", "tstat": tstat, "ndof": ndof,
            "pvalue": float(_chi2.sf(tstat, ndof))}


def signal_injection(signal, background, mu_true_values=(0.0, 1.0, 2.0),
                     n_toys=200, bkg_uncert=None, seed=20260709) -> dict:
    """Inject mu_true, fit mu-hat on Poisson toys, report bias and pull width."""
    pyhf = _pyhf()
    model = build_model(signal, background, bkg_uncert)
    sig = np.asarray(signal, float)
    bkg = np.asarray(background, float)
    rng = np.random.default_rng(seed)
    init = model.config.suggested_init()
    bounds = [list(b) for b in model.config.suggested_bounds()]
    mu_idx = model.config.poi_index
    bounds[mu_idx] = [-10.0, 100.0]  # allow negative mu-hat: unbiased estimator
    out = {"seed": seed, "n_toys": n_toys, "points": []}
    for mu_t in mu_true_values:
        lam = mu_t * sig + bkg
        mu_hats = []
        for _ in range(n_toys):
            toy = rng.poisson(lam)
            data = list(map(float, toy)) + model.config.auxdata
            try:
                best = pyhf.infer.mle.fit(data, model, init_pars=init,
                                          par_bounds=bounds)
                mu_hats.append(float(best[mu_idx]))
            except Exception:
                continue
        mh = np.asarray(mu_hats)
        pt = {"mu_true": float(mu_t), "n_ok": int(mh.size)}
        if mh.size:
            pt.update({"mu_hat_mean": float(mh.mean()),
                       "mu_hat_std": float(mh.std()),
                       "bias": float(mh.mean() - mu_t),
                       "bias_err": float(mh.std() / math.sqrt(mh.size))})
            pt["bias_significant"] = bool(
                abs(pt["bias"]) > 3.0 * max(pt["bias_err"], 1e-12))
        out["points"].append(pt)
    out["passed"] = all(not p.get("bias_significant", True) for p in out["points"])
    return out


# ---------------------------------------------------------------------------
# unbinned path (iminuit) — returns shape_validator-compatible fit records
# ---------------------------------------------------------------------------

def unbinned_fit(nll, start: dict, limits: dict | None = None,
                 n_data: int = 0, model_name: str = "unbinned",
                 stability_starts: list | None = None) -> dict:
    """Minimize a user-supplied negative log-likelihood with iminuit.

    nll: callable taking keyword parameters named as in `start`.
    Returns a fit record consumable by shape_validator.validate_fit, including
    optional stability refits from alternative start points.
    """
    from iminuit import Minuit

    def _run(init):
        m = Minuit(nll, name=list(init), **init)
        m.errordef = Minuit.LIKELIHOOD
        for k, v in (limits or {}).items():
            m.limits[k] = v
        m.migrad()
        m.hesse()
        return m

    m = _run(start)
    names = list(start)
    params = []
    for k in names:
        prm = {"name": k, "value": float(m.values[k]), "error": float(m.errors[k])}
        if limits and k in limits:
            lo, hi = limits[k]
            if lo is not None:
                prm["limit_lo"] = float(lo)
            if hi is not None:
                prm["limit_hi"] = float(hi)
        params.append(prm)
    rec = {
        "model_name": model_name,
        "converged": bool(m.fmin.is_valid),
        "n_data": int(n_data),
        "params": params,
        "nll": float(m.fmin.fval),
    }
    if m.covariance is not None:
        rec["covariance"] = [[float(m.covariance[a, b]) for b in names] for a in names]
    refits = []
    for i, alt in enumerate(stability_starts or []):
        try:
            m2 = _run(alt)
            refits.append({"label": f"altstart_{i}",
                           "params": [{"name": k, "value": float(m2.values[k])}
                                      for k in names]})
        except Exception:
            refits.append({"label": f"altstart_{i}", "params": [],
                           "failed": True})
    if refits:
        rec["refits"] = refits
    return rec


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--demo", action="store_true",
                   help="run a small counting-experiment demo")
    a = p.parse_args()
    if a.demo:
        res = upper_limit(signal=[5.0], background=[10.0], bkg_uncert=[3.0])
        print(json.dumps(res, indent=1))
