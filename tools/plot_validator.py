#!/usr/bin/env python3
"""Programmatic plot validation — 35 checks over figure + sidecar manifest.

Every figure `<name>.png|.pdf` must ship a sidecar manifest `<name>.plot.json`
(see SCHEMA below). Checks are grouped as in arXiv:2603.20179:
  - 8 formatting checks        (Category B/C findings)
  - 11 physics sanity checks   (Category B findings)
  - 6 consistency checks       (Category B findings)
  - 10 red-flag detections     (Category A — the arbiter may NOT downgrade these)

SCHEMA (sidecar JSON):
{
  "kind": "histogram|cut_scan|fit|ratio|scatter|other",
  "title": str,
  "x_label": str, "x_unit": str, "y_label": str, "y_unit": str,
  "lumi_stamp": str,                      # e.g. "59.7 fb^-1 (13 TeV)" or "n/a (...)"
  "series": [{"name": str,
              "role": "data|mc|model|signal|background|efficiency|ratio|other",
              "values": [...],
              "yerr": [...],              # optional
              "bin_edges": [...]          # optional (len(values)+1)
            }, ...],
  "blinded_region_shown": bool,
  "blinded_window": [lo, hi],             # optional
  "legend": bool,                         # optional
  "log_y": bool                           # optional
}

CLI:
    plot_validator.py fig.png [fig2.png ...] [--blinded] [--json]
exit code 2 if any Category A finding, 1 if any B, else 0.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

YIELD_ROLES = ("data", "mc", "model", "signal", "background")
REQUIRED_KEYS = ("kind", "title", "x_label", "y_label", "series")
PLACEHOLDERS = {"", "x", "y", "axis", "value", "values", "none", "label"}
MAGIC = {b"\x89PNG": "png", b"%PDF": "pdf"}


def _f(check, cat, msg):
    return {"check": check, "category": cat, "message": msg}


def _arr(x):
    return np.asarray(x, dtype=np.float64)


def validate_manifest(manifest: dict, image_path: str | None = None,
                      blinded: bool = True) -> list[dict]:
    """Return findings for one figure. Empty list == clean."""
    fnd = []
    series = manifest.get("series", []) or []

    # ---------------- formatting (F1–F8) ----------------
    if image_path is not None:
        if not (os.path.exists(image_path) and os.path.getsize(image_path) > 0):
            fnd.append(_f("F1", "A", f"image file missing or empty: {image_path}"))
        else:
            with open(image_path, "rb") as fp:
                head = fp.read(4)
            if head not in MAGIC:
                fnd.append(_f("F2", "B", "image is not a valid PNG/PDF"))
    missing = [k for k in REQUIRED_KEYS if k not in manifest]
    if missing:
        fnd.append(_f("F3", "B", f"manifest missing required keys: {missing}"))
    if str(manifest.get("x_label", "")).strip().lower() in PLACEHOLDERS:
        fnd.append(_f("F4", "B", "x axis label empty or placeholder"))
    if str(manifest.get("y_label", "")).strip().lower() in PLACEHOLDERS:
        fnd.append(_f("F5", "B", "y axis label empty or placeholder"))
    if not str(manifest.get("title", "")).strip():
        fnd.append(_f("F6", "C", "figure has no title"))
    has_data = any(s.get("role") == "data" for s in series)
    if has_data and not str(manifest.get("lumi_stamp", "")).strip():
        fnd.append(_f("F7", "B", "data shown without a luminosity stamp"))
    if len(series) > 1 and not manifest.get("legend", False):
        fnd.append(_f("F8", "C", "multiple series but no legend"))

    # ---------------- physics sanity (P1–P11) ----------------
    for s in series:
        name, role = s.get("name", "?"), s.get("role", "other")
        v = _arr(s.get("values", []))
        if v.size == 0:
            fnd.append(_f("P1", "B", f"series '{name}' has no values"))
            continue
        if role in YIELD_ROLES and np.nanmin(v) < 0:
            fnd.append(_f("P2", "B", f"negative yields in '{name}' (role {role})"))
        if role == "efficiency" and ((np.nanmin(v) < -1e-9) or (np.nanmax(v) > 1 + 1e-9)):
            fnd.append(_f("P3", "B", f"efficiency series '{name}' outside [0,1]"))
        if role == "ratio":
            fin = v[np.isfinite(v)]
            if fin.size and np.nanmin(fin) <= 0:
                fnd.append(_f("P4", "B", f"non-positive values in ratio '{name}'"))
        if not np.isfinite(v).all():
            fnd.append(_f("P5", "B", f"NaN/inf in series '{name}'"))
        ye = s.get("yerr")
        if ye is not None:
            ye = _arr(ye)
            if ye.size and np.nanmin(ye) < 0:
                fnd.append(_f("P6", "B", f"negative error bars in '{name}'"))
            if role == "data" and v.size == ye.size and np.all(v == np.floor(v)):
                nz = v > 0
                if nz.any() and np.median(
                        np.abs(ye[nz] - np.sqrt(v[nz])) / np.sqrt(v[nz])) > 0.5:
                    fnd.append(_f("P7", "C",
                                  f"data errors in '{name}' far from sqrt(N); "
                                  "verify weighted-data treatment"))
        be = s.get("bin_edges")
        if be is not None:
            be = _arr(be)
            if be.size != v.size + 1:
                fnd.append(_f("P8", "B",
                              f"'{name}': {v.size} values vs {be.size} bin edges"))
        if role in YIELD_ROLES and np.nansum(np.abs(v)) == 0:
            fnd.append(_f("P9", "B", f"series '{name}' (role {role}) is all zeros"))
    bw = manifest.get("blinded_window")
    if bw and has_data and not manifest.get("blinded_region_shown", False):
        fnd.append(_f("P10", "B",
                      "data plot with a blinded window must indicate the blinded region"))
    ymax = max((np.nanmax(_arr(s["values"])) for s in series
                if len(s.get("values", []))), default=0)
    ymin_pos = min((np.nanmin(_arr(s["values"])[_arr(s["values"]) > 0])
                    for s in series
                    if len(s.get("values", [])) and (_arr(s["values"]) > 0).any()),
                   default=1)
    if ymax > 0 and ymin_pos > 0 and ymax / ymin_pos > 1e4 and not manifest.get("log_y"):
        fnd.append(_f("P11", "C", "y spans >4 decades on a linear scale"))

    # ---------------- consistency (X1–X6) ----------------
    edges = [tuple(s["bin_edges"]) for s in series if s.get("bin_edges")]
    if len(set(edges)) > 1:
        fnd.append(_f("X1", "B", "series have inconsistent bin edges"))
    data_tot = sum(np.nansum(_arr(s["values"])) for s in series
                   if s.get("role") == "data")
    model_tot = sum(np.nansum(_arr(s["values"])) for s in series
                    if s.get("role") in ("mc", "model", "background", "signal"))
    if data_tot > 0 and model_tot > 0:
        pull = abs(data_tot - model_tot) / max(np.sqrt(data_tot), 1.0)
        if pull > 5:
            fnd.append(_f("X2", "B",
                          f"data total ({data_tot:.4g}) vs model total "
                          f"({model_tot:.4g}) differ by {pull:.1f}σ(stat)"))
    names = [s.get("name") for s in series]
    if len(names) != len(set(names)):
        fnd.append(_f("X3", "B", "duplicate series names"))
    for s in series:
        if s.get("role") == "ratio" and data_tot > 0 and model_tot > 0:
            med = np.nanmedian(_arr(s["values"]))
            glob = data_tot / model_tot
            if np.isfinite(med) and abs(med - glob) > 0.5:
                fnd.append(_f("X4", "B",
                              f"ratio panel median {med:.2f} inconsistent with "
                              f"global data/model {glob:.2f}"))
    if manifest.get("legend") and len(series) < 2:
        fnd.append(_f("X5", "C", "legend declared for a single-series figure"))
    if bw is not None and (len(bw) != 2 or not bw[1] > bw[0]):
        fnd.append(_f("X6", "B", f"malformed blinded_window {bw}"))

    # ---------------- red flags (R1–R10, Category A) ----------------
    for s in series:
        name, role = s.get("name", "?"), s.get("role", "other")
        v = _arr(s.get("values", []))
        if v.size == 0:
            continue
        if role in YIELD_ROLES and np.nanmin(v) < -1e-6 * max(np.nanmax(np.abs(v)), 1):
            if np.nanmin(v) < -np.sqrt(max(np.nanmax(v), 1.0)):
                fnd.append(_f("R1", "A",
                              f"strongly negative yields in '{name}': min={np.nanmin(v):.4g}"))
        if role == "efficiency" and (np.nanmin(v) < -0.01 or np.nanmax(v) > 1.01):
            fnd.append(_f("R2", "A", f"efficiency '{name}' grossly outside [0,1]"))
        if role == "data" and not np.isfinite(v).all():
            fnd.append(_f("R3", "A", f"NaN/inf in DATA series '{name}'"))
        if role == "data" and np.nansum(np.abs(v)) == 0:
            fnd.append(_f("R4", "A", f"data series '{name}' is empty on a data plot"))
        ye = s.get("yerr")
        if (role == "data" and ye is not None and np.nansum(np.abs(_arr(ye))) == 0
                and np.nansum(v) > 0):
            fnd.append(_f("R8", "A", f"data '{name}' has nonzero counts but zero errors"))
        be = s.get("bin_edges")
        if be is not None and _arr(be).size > 1 and not np.all(np.diff(_arr(be)) > 0):
            fnd.append(_f("R9", "A", f"non-monotonic bin edges in '{name}'"))
    # blinding violation
    if blinded and bw and len(bw) == 2:
        for s in series:
            if s.get("role") != "data" or not s.get("bin_edges"):
                continue
            v, be = _arr(s["values"]), _arr(s["bin_edges"])
            centers = 0.5 * (be[:-1] + be[1:])
            inside = (centers > bw[0]) & (centers < bw[1])
            if inside.any() and np.nansum(v[inside]) > 0:
                fnd.append(_f("R5", "A",
                              f"BLINDING VIOLATION: data series '{s.get('name')}' has "
                              f"{np.nansum(v[inside]):.0f} counts inside blinded window {bw}"))
    if data_tot > 0 and model_tot > 0:
        r = data_tot / model_tot
        if r < 0.2 or r > 5.0:
            fnd.append(_f("R6", "A",
                          f"data/model normalization off by x{max(r, 1/r):.1f}"))
    vals = {}
    for s in series:
        key = tuple(np.round(_arr(s.get("values", [])), 12))
        if len(key) > 3 and key in vals and s.get("role") != vals[key]:
            fnd.append(_f("R7", "A",
                          f"series '{s.get('name')}' identical to a series of different "
                          f"role ('{vals[key]}') — likely copy-paste bug"))
        elif len(key) > 3:
            vals[key] = s.get("role")
    return fnd


def validate_figure(image_path: str, blinded: bool = True) -> list[dict]:
    base, _ = os.path.splitext(image_path)
    mpath = base + ".plot.json"
    if not os.path.exists(mpath):
        return [_f("R10", "A", f"missing plot manifest {mpath} — cannot validate")]
    try:
        with open(mpath) as f:
            manifest = json.load(f)
    except Exception as e:
        return [_f("R10", "A", f"unreadable plot manifest {mpath}: {e}")]
    return validate_manifest(manifest, image_path, blinded=blinded)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("figures", nargs="+")
    p.add_argument("--unblinded", action="store_true",
                   help="phase >= 4b: suppress blinding-violation red flag")
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    all_findings = {}
    worst = 0
    for fig in a.figures:
        fnd = validate_figure(fig, blinded=not a.unblinded)
        all_findings[fig] = fnd
        for x in fnd:
            worst = max(worst, {"A": 2, "B": 1, "C": 0}[x["category"]])
    if a.json:
        print(json.dumps(all_findings, indent=1))
    else:
        for fig, fnd in all_findings.items():
            status = "CLEAN" if not fnd else f"{len(fnd)} finding(s)"
            print(f"{fig}: {status}")
            for x in fnd:
                print(f"  [{x['category']}] {x['check']}: {x['message']}")
    return worst


if __name__ == "__main__":
    sys.exit(main())
