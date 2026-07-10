#!/usr/bin/env python3
"""Reproducible cut scans: figures of merit vs cut value, and N-1 tables.

Trusted instrument for the Phase-3 cut-discovery protocol: the analyst picks the
variables; this tool makes every scan reproducible and reviewable. Results are
returned as dicts and (optionally) written as JSON + a standard scan plot with the
plot-manifest sidecar required by plot_validator.

Figures of merit (signal counts s, background counts b, both weighted):
    punzi        s_eff / (a/2 + sqrt(b)), a = 3 (Punzi, discovery-oriented)
    s_sqrt_sb    s / sqrt(s + b)
    s_sqrt_b     s / sqrt(b)            (guard: requires b >= 3 to be quoted)
    sig_asimov   sqrt(2*((s+b)*ln(1+s/b) - s))

Library:
    scan_cut(sig, bkg, direction=">", fom="punzi", ...) -> dict
    n_minus_one(sig_arrays, bkg_arrays, cuts) -> dict
"""
from __future__ import annotations

import argparse
import json
import sys

import numpy as np

FOMS = ("punzi", "s_sqrt_sb", "s_sqrt_b", "sig_asimov")


def _fom(name: str, s: np.ndarray, b: np.ndarray, s_tot: float, a: float = 3.0):
    s = np.asarray(s, float)
    b = np.asarray(b, float)
    with np.errstate(divide="ignore", invalid="ignore"):
        if name == "punzi":
            eff = s / s_tot if s_tot > 0 else np.zeros_like(s)
            v = eff / (a / 2.0 + np.sqrt(b))
        elif name == "s_sqrt_sb":
            v = np.where(s + b > 0, s / np.sqrt(s + b), 0.0)
        elif name == "s_sqrt_b":
            v = np.where(b >= 3.0, s / np.sqrt(np.maximum(b, 1e-9)), np.nan)
        elif name == "sig_asimov":
            ratio = np.where(b > 0, s / b, 0.0)
            v = np.sqrt(np.maximum(
                2.0 * ((s + b) * np.log1p(ratio) - s), 0.0))
            v = np.where(b > 0, v, np.nan)
        else:
            raise ValueError(f"unknown fom {name!r}; allowed {FOMS}")
    return v


def scan_cut(sig: np.ndarray, bkg: np.ndarray, direction: str = ">",
             fom: str = "punzi", n_points: int = 100,
             sig_w: np.ndarray | None = None, bkg_w: np.ndarray | None = None,
             quantile_range: tuple = (0.001, 0.999)) -> dict:
    """Scan a threshold cut `x {>,<} c` on one variable.

    Returns dict with grid, per-point s, b, signal efficiency, background
    rejection, fom values, the optimum, and a plateau-stability measure
    (width of the cut interval whose FoM is within 5% of the optimum —
    narrow plateau == unstable optimum).
    """
    if direction not in (">", "<"):
        raise ValueError("direction must be '>' or '<'")
    sig = np.asarray(sig, float)
    bkg = np.asarray(bkg, float)
    sw = np.ones_like(sig) if sig_w is None else np.asarray(sig_w, float)
    bw = np.ones_like(bkg) if bkg_w is None else np.asarray(bkg_w, float)
    ok_s, ok_b = np.isfinite(sig), np.isfinite(bkg)
    sig, sw, bkg, bw = sig[ok_s], sw[ok_s], bkg[ok_b], bw[ok_b]
    s_tot, b_tot = sw.sum(), bw.sum()
    if s_tot <= 0 or b_tot <= 0:
        raise ValueError("empty signal or background sample")

    both = np.concatenate([sig, bkg])
    lo, hi = np.quantile(both, quantile_range)
    grid = np.linspace(lo, hi, n_points)

    # cumulative weighted counts via sorting (O(n log n), not O(n*grid))
    def _passing(x, w):
        order = np.argsort(x)
        xs, ws = x[order], w[order]
        cum = np.concatenate([[0.0], np.cumsum(ws)])
        idx = np.searchsorted(xs, grid, side="left")
        below = cum[idx]                # weight with x < c
        return (w.sum() - below) if direction == ">" else below

    s_pass = _passing(sig, sw)
    b_pass = _passing(bkg, bw)
    v = _fom(fom, s_pass, b_pass, s_tot)
    finite = np.isfinite(v)
    if not finite.any():
        raise ValueError(f"FoM {fom} undefined everywhere (background too sparse?)")
    i_best = int(np.nanargmax(v))
    plateau = grid[finite & (v >= 0.95 * v[i_best])]
    result = {
        "direction": direction, "fom": fom,
        "grid": grid.tolist(),
        "s": s_pass.tolist(), "b": b_pass.tolist(),
        "sig_eff": (s_pass / s_tot).tolist(),
        "bkg_rej": (1.0 - b_pass / b_tot).tolist(),
        "fom_values": [None if not np.isfinite(x) else float(x) for x in v],
        "best_cut": float(grid[i_best]),
        "best_fom": float(v[i_best]),
        "sig_eff_at_best": float(s_pass[i_best] / s_tot),
        "bkg_rej_at_best": float(1.0 - b_pass[i_best] / b_tot),
        "plateau_width_frac": float(
            (plateau.max() - plateau.min()) / (hi - lo)) if plateau.size else 0.0,
        "n_sig": int(ok_s.sum()), "n_bkg": int(ok_b.sum()),
    }
    result["warnings"] = []
    if result["sig_eff_at_best"] < 0.5:
        result["warnings"].append(
            f"optimum keeps only {result['sig_eff_at_best']:.1%} of signal — "
            "check for over-tight cut")
    if result["plateau_width_frac"] < 0.03:
        result["warnings"].append("narrow FoM plateau — optimum may be unstable")
    return result


def apply_cuts(arrays: dict, cuts: list[dict]) -> np.ndarray:
    """cuts: [{'var': name, 'direction': '>'|'<', 'value': c}, ...] -> bool mask."""
    mask = None
    for c in cuts:
        x = np.asarray(arrays[c["var"]], float)
        m = (x > c["value"]) if c["direction"] == ">" else (x < c["value"])
        m &= np.isfinite(x)
        mask = m if mask is None else (mask & m)
    if mask is None:
        raise ValueError("no cuts given")
    return mask


def n_minus_one(sig_arrays: dict, bkg_arrays: dict, cuts: list[dict],
                fom: str = "punzi") -> dict:
    """For each cut: FoM/efficiency with that cut removed vs full selection."""
    def _counts(arrs, cs):
        m = apply_cuts(arrs, cs)
        return float(m.sum())

    s_tot = float(len(next(iter(sig_arrays.values()))))
    full_s = _counts(sig_arrays, cuts)
    full_b = _counts(bkg_arrays, cuts)
    full_fom = float(_fom(fom, np.array([full_s]), np.array([full_b]), s_tot)[0])
    rows = []
    for i, c in enumerate(cuts):
        rest = cuts[:i] + cuts[i + 1:]
        if not rest:
            continue
        s = _counts(sig_arrays, rest)
        b = _counts(bkg_arrays, rest)
        rows.append({
            "cut": c,
            "s_without": s, "b_without": b,
            "marginal_sig_eff": full_s / s if s > 0 else None,
            "marginal_bkg_rej": 1.0 - full_b / b if b > 0 else None,
            "fom_without": float(_fom(fom, np.array([s]), np.array([b]), s_tot)[0]),
        })
    return {"fom": fom, "full": {"s": full_s, "b": full_b, "fom": full_fom},
            "n_minus_one": rows}


def plot_scan(result: dict, var_name: str, out_png: str, title: str = ""):
    """Standard scan figure + plot-manifest sidecar for plot_validator."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    grid = np.array(result["grid"])
    fom = np.array([np.nan if v is None else v for v in result["fom_values"]])
    fig, ax1 = plt.subplots(figsize=(7, 5))
    ax1.plot(grid, result["sig_eff"], label="signal efficiency", color="#0072B2")
    ax1.plot(grid, result["bkg_rej"], label="background rejection", color="#E69F00")
    ax1.set_xlabel(f"{var_name} cut value ({result['direction']})")
    ax1.set_ylabel("efficiency / rejection")
    ax1.set_ylim(0, 1.05)
    ax2 = ax1.twinx()
    ax2.plot(grid, fom, label=result["fom"], color="#009E73", ls="--")
    ax2.set_ylabel(result["fom"])
    ax1.axvline(result["best_cut"], color="gray", ls=":",
                label=f"best cut = {result['best_cut']:.4g}")
    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc="lower left", fontsize=8)
    if title:
        ax1.set_title(title)
    fig.tight_layout()
    fig.savefig(out_png, dpi=120)
    plt.close(fig)
    manifest = {
        "kind": "cut_scan", "title": title or f"cut scan {var_name}",
        "x_label": f"{var_name} cut value ({result['direction']})",
        "x_unit": "", "y_label": "efficiency / rejection / FoM", "y_unit": "",
        "series": [
            {"name": "sig_eff", "role": "efficiency", "values": result["sig_eff"]},
            {"name": "bkg_rej", "role": "efficiency", "values": result["bkg_rej"]},
        ],
        "blinded_region_shown": False,
        "lumi_stamp": "n/a (MC/SB optimization plot)",
    }
    with open(out_png.replace(".png", "") + ".plot.json", "w") as f:
        json.dump(manifest, f, indent=1)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sig-npz", required=True, help=".npz with array under --var")
    p.add_argument("--bkg-npz", required=True)
    p.add_argument("--var", required=True)
    p.add_argument("--direction", default=">", choices=[">", "<"])
    p.add_argument("--fom", default="punzi", choices=list(FOMS))
    p.add_argument("--out-json", default=None)
    p.add_argument("--out-png", default=None)
    a = p.parse_args(argv)
    sig = np.load(a.sig_npz)[a.var]
    bkg = np.load(a.bkg_npz)[a.var]
    res = scan_cut(sig, bkg, a.direction, a.fom)
    if a.out_png:
        plot_scan(res, a.var, a.out_png)
    text = json.dumps({k: v for k, v in res.items()
                       if k not in ("grid", "s", "b", "sig_eff", "bkg_rej",
                                    "fom_values")}, indent=1)
    if a.out_json:
        with open(a.out_json, "w") as f:
            json.dump(res, f, indent=1)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
