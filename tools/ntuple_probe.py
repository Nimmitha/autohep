#!/usr/bin/env python3
"""Ntuple reconnaissance: introspect a ROOT file with no prior schema.

For each TTree branch reports: dtype, jaggedness, entry count, NaN/inf fraction,
range, moments, quantiles, distinct-value count (flag-like branches), and candidate
resonance peaks in mass-like branches (compared against a small PDG table).
Also reports pairwise |Pearson r| > threshold among flat numeric branches, and
duplicate-event checks when run/lumi/event-like branches are present.

Output is a JSON report — the raw material for the Phase-2 inferred data dictionary.
The tool never interprets physics; inference of branch *meaning* is the analyst's
job, grounded in this report.

CLI:
    ntuple_probe.py file.root [--tree NAME] [--entries 1000] [--out report.json]
"""
from __future__ import annotations

import argparse
import json
import math
import sys

import numpy as np

PDG_PEAKS = {  # GeV; used only to annotate candidate peaks, not to decide anything
    "J/psi(1S)": 3.0969, "psi(2S)": 3.6861, "Upsilon(1S)": 9.4603,
    "Z": 91.1876, "W": 80.377, "H": 125.25, "phi(1020)": 1.0195,
    "K0S": 0.4976, "Lambda": 1.1157, "D0": 1.8648, "B+/B0": 5.279,
    "top": 172.7, "pi0": 0.1350, "eta": 0.5479,
}
PEAK_MATCH_REL = 0.02  # annotate if within 2% of a PDG mass


def _stats(x: np.ndarray) -> dict:
    x = np.asarray(x, dtype=np.float64)
    n = x.size
    finite = np.isfinite(x)
    xf = x[finite]
    out = {
        "n": int(n),
        "n_nonfinite": int(n - xf.size),
        "frac_nonfinite": float((n - xf.size) / n) if n else 0.0,
    }
    if xf.size == 0:
        return out
    q = np.quantile(xf, [0.0, 0.01, 0.25, 0.5, 0.75, 0.99, 1.0])
    out.update({
        "min": float(q[0]), "q01": float(q[1]), "q25": float(q[2]),
        "median": float(q[3]), "q75": float(q[4]), "q99": float(q[5]),
        "max": float(q[6]),
        "mean": float(xf.mean()), "std": float(xf.std()),
        "frac_zero": float((xf == 0).mean()),
        "frac_negative": float((xf < 0).mean()),
    })
    uniq = np.unique(xf[: min(xf.size, 200_000)])
    out["n_distinct_sampled"] = int(uniq.size)
    out["looks_flaglike"] = bool(uniq.size <= 10)
    if uniq.size <= 10:
        out["distinct_values"] = [float(v) for v in uniq]
    out["looks_integer"] = bool(np.all(xf == np.floor(xf)))
    return out


def _find_peaks(x: np.ndarray, nbins: int = 200) -> list[dict]:
    """Crude peak finder: local maxima above smooth background in a histogram."""
    xf = x[np.isfinite(x)]
    if xf.size < 200:
        return []
    lo, hi = np.quantile(xf, [0.001, 0.999])
    if not (hi > lo):
        return []
    counts, edges = np.histogram(xf, bins=nbins, range=(lo, hi))
    centers = 0.5 * (edges[:-1] + edges[1:])
    # smooth background: broad moving average
    k = max(nbins // 20, 3)
    kern = np.ones(2 * k + 1) / (2 * k + 1)
    bkg = np.convolve(counts, kern, mode="same")
    excess = counts - bkg
    sigma = np.sqrt(np.maximum(bkg, 1.0))
    signif = excess / sigma
    peaks = []
    for i in range(2, nbins - 2):
        if signif[i] > 4.0 and counts[i] == counts[max(0, i - 2): i + 3].max():
            peak = {
                "position": float(centers[i]),
                "local_significance": float(signif[i]),
                "bin_width": float(edges[1] - edges[0]),
            }
            for name, m in PDG_PEAKS.items():
                if abs(centers[i] - m) / m < PEAK_MATCH_REL:
                    peak["pdg_candidate"] = name
                    peak["pdg_mass"] = m
            peaks.append(peak)
    peaks.sort(key=lambda p: -p["local_significance"])
    return peaks[:8]


def probe_arrays(arrays: dict, correlations: bool = True) -> dict:
    """Probe already-loaded {branch: np.ndarray-or-awkward} arrays."""
    import awkward as ak

    report = {"branches": {}, "correlations": [], "peaks": {}}
    flat = {}
    for name, arr in arrays.items():
        entry = {"name": name}
        try:
            if isinstance(arr, np.ndarray) and arr.ndim == 1 and arr.dtype.kind in "fiub":
                vals = arr.astype(np.float64)
                entry["jagged"] = False
            else:
                aka = ak.Array(arr) if not isinstance(arr, ak.Array) else arr
                if aka.ndim > 1:
                    entry["jagged"] = True
                    entry["mean_multiplicity"] = float(ak.mean(ak.num(aka)))
                    vals = ak.to_numpy(ak.flatten(aka, axis=None)).astype(np.float64)
                else:
                    entry["jagged"] = False
                    vals = ak.to_numpy(aka).astype(np.float64)
            entry["stats"] = _stats(vals)
            if not entry["jagged"]:
                flat[name] = vals
            # mass-like heuristic: nonnegative, continuous, not flag-like
            s = entry["stats"]
            if (s.get("n", 0) >= 200 and not s.get("looks_flaglike")
                    and s.get("frac_negative", 1) < 0.01 and not s.get("looks_integer")):
                pk = _find_peaks(vals)
                if pk:
                    report["peaks"][name] = pk
        except Exception as e:  # unreadable branch: report, don't crash the probe
            entry["error"] = f"{type(e).__name__}: {e}"
        report["branches"][name] = entry

    if correlations and len(flat) >= 2:
        names = sorted(flat)
        n = min(min(len(v) for v in flat.values()), 50_000)
        mat = np.vstack([flat[k][:n] for k in names])
        ok = np.isfinite(mat).all(axis=0)
        if ok.sum() > 100:
            cc = np.corrcoef(mat[:, ok])
            for i in range(len(names)):
                for j in range(i + 1, len(names)):
                    r = cc[i, j]
                    if np.isfinite(r) and abs(r) > 0.8:
                        report["correlations"].append(
                            {"a": names[i], "b": names[j], "pearson_r": float(r)})
    return report


def probe_file(path: str, tree: str | None = None, entries: int = 1000,
               correlations: bool = True) -> dict:
    import uproot

    f = uproot.open(path)
    trees = [k.split(";")[0] for k, v in f.classnames().items()
             if v.startswith("TTree") or "RNTuple" in v]
    report = {"file": path, "trees_found": sorted(set(trees))}
    if not trees:
        report["error"] = "no TTree/RNTuple found"
        return report
    tname = tree or max(set(trees), key=lambda t: f[t].num_entries)
    t = f[tname]
    report["tree"] = tname
    report["num_entries"] = int(t.num_entries)
    report["probed_entries"] = int(min(entries, t.num_entries))
    arrays = t.arrays(entry_stop=entries, library="ak")
    arr_dict = {name: arrays[name] for name in arrays.fields}
    report.update(probe_arrays(arr_dict, correlations=correlations))

    # duplicate-event check on run/lumi/event-like triplets
    idlike = [b for b in arr_dict
              if b.lower() in ("run", "event", "evt", "lumi", "luminosityblock", "ls")]
    if idlike:
        import awkward as ak
        cols = [np.asarray(ak.to_numpy(ak.Array(arr_dict[b]))).astype(np.int64)
                for b in idlike if not report["branches"][b].get("jagged")]
        if cols:
            ids = np.vstack(cols).T
            _, counts = np.unique(ids, axis=0, return_counts=True)
            report["duplicate_check"] = {
                "id_branches": idlike,
                "n_duplicate_ids": int((counts > 1).sum()),
            }
    return report


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("file")
    p.add_argument("--tree", default=None)
    p.add_argument("--entries", type=int, default=1000)
    p.add_argument("--no-correlations", action="store_true")
    p.add_argument("--out", default=None)
    a = p.parse_args(argv)
    rep = probe_file(a.file, a.tree, a.entries, correlations=not a.no_correlations)
    text = json.dumps(rep, indent=1)
    if a.out:
        with open(a.out, "w") as f:
            f.write(text)
        print(f"wrote {a.out} ({len(rep.get('branches', {}))} branches, "
              f"{len(rep.get('peaks', {}))} peaked branches)")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
