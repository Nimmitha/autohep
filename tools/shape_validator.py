#!/usr/bin/env python3
"""Fit/shape-model validation — encodes the acceptance criteria a human analyst
would apply: convergence, covariance behavior, parameter health, pull
distributions, goodness of fit, and stability under refits.

Input is a fit record (dict / JSON):
{
  "model_name": str,
  "converged": bool,
  "n_data": int,                      # events (unbinned) or bins (binned)
  "params": [{"name": str, "value": f, "error": f,
              "limit_lo": f, "limit_hi": f}, ...],   # limits optional
  "covariance": [[...], ...],         # optional but strongly recommended
  "gof": {"method": str, "pvalue": f},# optional; method must not be naive chi2/ndf
  "pulls": [...],                     # optional per-bin (data-fit)/sigma
  "refits": [{"label": str, "params": [{"name","value"}...]}, ...]  # optional
}

Categories follow the review scheme: A blocking, B important, C minor.
CLI: shape_validator.py record.json [record2.json ...] [--json]
"""
from __future__ import annotations

import argparse
import json
import sys

import numpy as np

COND_WARN = 1e8
COND_FAIL = 1e12


def _f(check, cat, msg):
    return {"check": check, "category": cat, "message": msg}


def validate_fit(rec: dict) -> list[dict]:
    fnd = []
    name = rec.get("model_name", "?")

    # --- convergence & dof -------------------------------------------------
    if not rec.get("converged", False):
        fnd.append(_f("S1", "A", f"{name}: fit did not converge"))
    params = rec.get("params", [])
    n_data = rec.get("n_data", 0)
    if params and n_data and n_data <= len(params):
        fnd.append(_f("S2", "A",
                      f"{name}: {len(params)} parameters vs {n_data} data points — "
                      "over-parameterized"))

    # --- covariance --------------------------------------------------------
    cov = rec.get("covariance")
    if cov is None:
        fnd.append(_f("S3", "B", f"{name}: no covariance matrix provided"))
    else:
        c = np.asarray(cov, float)
        if c.shape[0] != c.shape[1] or (params and c.shape[0] != len(params)):
            fnd.append(_f("S4", "A", f"{name}: covariance shape {c.shape} inconsistent "
                                     f"with {len(params)} parameters"))
        else:
            eig = np.linalg.eigvalsh(0.5 * (c + c.T))
            if eig.min() <= 0:
                fnd.append(_f("S5", "A",
                              f"{name}: covariance not positive definite "
                              f"(min eigenvalue {eig.min():.3g}) — rank-deficient fit"))
            elif eig.min() > 0:
                cond = eig.max() / eig.min()
                if cond > COND_FAIL:
                    fnd.append(_f("S6", "A",
                                  f"{name}: covariance condition number {cond:.2g} — "
                                  "degenerate parameters"))
                elif cond > COND_WARN:
                    fnd.append(_f("S6", "B",
                                  f"{name}: large covariance condition number {cond:.2g}"))
            # correlations
            d = np.sqrt(np.diag(c))
            with np.errstate(invalid="ignore", divide="ignore"):
                corr = c / np.outer(d, d)
            hi = np.argwhere(np.triu(np.abs(corr), 1) > 0.98)
            for i, j in hi:
                pi = params[i]["name"] if i < len(params) else str(i)
                pj = params[j]["name"] if j < len(params) else str(j)
                fnd.append(_f("S7", "B",
                              f"{name}: |corr({pi},{pj})| > 0.98 — redundant parameter"))

    # --- parameter health ----------------------------------------------------
    for prm in params:
        pn, v, e = prm.get("name", "?"), prm.get("value"), prm.get("error")
        if e is not None and e <= 0:
            fnd.append(_f("S8", "A", f"{name}: parameter {pn} has error {e} <= 0"))
        lo, hiL = prm.get("limit_lo"), prm.get("limit_hi")
        for lim, side in ((lo, "lower"), (hiL, "upper")):
            if lim is not None and v is not None and e is not None and e > 0:
                if abs(v - lim) < 1.0 * e and abs(v - lim) < 0.01 * max(abs(v), abs(lim), 1e-12):
                    fnd.append(_f("S9", "B",
                                  f"{name}: parameter {pn}={v:.4g} pinned at {side} "
                                  f"limit {lim:.4g}"))
        if v is not None and e is not None and e > 0 and abs(v) > 0 and e / abs(v) > 2.0:
            fnd.append(_f("S10", "C",
                          f"{name}: parameter {pn} consistent with zero "
                          f"(error/|value| = {e/abs(v):.1f}) — consider simpler model"))

    # --- goodness of fit -----------------------------------------------------
    gof = rec.get("gof")
    if gof is None:
        fnd.append(_f("S11", "B", f"{name}: no goodness-of-fit result"))
    else:
        method = str(gof.get("method", "")).lower()
        pv = gof.get("pvalue")
        if "chi2/ndf" in method or method in ("chi2", "chisq"):
            fnd.append(_f("S12", "B",
                          f"{name}: GoF method '{gof.get('method')}' — use the "
                          "saturated-model likelihood ratio, not naive chi2 on sparse bins"))
        if pv is not None:
            if pv < 1e-3:
                fnd.append(_f("S13", "A", f"{name}: GoF p-value {pv:.2g} — model rejected"))
            elif pv > 0.999:
                fnd.append(_f("S14", "A",
                              f"{name}: GoF p-value {pv:.4g} suspiciously close to 1 — "
                              "likely mis-implemented test or overfit (known failure mode)"))

    # --- pulls ---------------------------------------------------------------
    pulls = rec.get("pulls")
    if pulls is not None and len(pulls) >= 5:
        pl = np.asarray(pulls, float)
        pl = pl[np.isfinite(pl)]
        if pl.size:
            if abs(pl.mean()) > 3.0 / np.sqrt(pl.size):
                fnd.append(_f("S15", "B",
                              f"{name}: pull mean {pl.mean():.2f} — systematic bias"))
            if pl.std() > 1.5:
                fnd.append(_f("S16", "B",
                              f"{name}: pull std {pl.std():.2f} > 1.5 — model too rigid "
                              "or errors underestimated"))
            if np.abs(pl).max() > 5:
                fnd.append(_f("S17", "B",
                              f"{name}: max |pull| = {np.abs(pl).max():.1f}"))

    # --- refit stability -------------------------------------------------------
    refits = rec.get("refits") or []
    if not refits:
        fnd.append(_f("S18", "C", f"{name}: no stability refits provided"))
    else:
        base = {p["name"]: p for p in params}
        for rf in refits:
            for prm in rf.get("params", []):
                b = base.get(prm["name"])
                if b and b.get("error"):
                    drift = abs(prm["value"] - b["value"]) / b["error"]
                    if drift > 1.0:
                        fnd.append(_f("S19", "B",
                                      f"{name}: {prm['name']} drifts {drift:.1f}σ under "
                                      f"refit '{rf.get('label', '?')}' — unstable"))
    return fnd


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("records", nargs="+", help="fit-record JSON files")
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    worst = 0
    out = {}
    for path in a.records:
        with open(path) as f:
            rec = json.load(f)
        fnd = validate_fit(rec)
        out[path] = fnd
        for x in fnd:
            worst = max(worst, {"A": 2, "B": 1, "C": 0}[x["category"]])
    if a.json:
        print(json.dumps(out, indent=1))
    else:
        for path, fnd in out.items():
            print(f"{path}: {'CLEAN' if not fnd else str(len(fnd)) + ' finding(s)'}")
            for x in fnd:
                print(f"  [{x['category']}] {x['check']}: {x['message']}")
    return worst


if __name__ == "__main__":
    sys.exit(main())
