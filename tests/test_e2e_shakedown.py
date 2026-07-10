"""End-to-end framework shakedown on a synthetic study: scaffold -> probe ->
cut scan -> blinded-plot validation -> expected limit -> hash-chained log.
Mimics what the analyst/orchestrator agents do in Phases 1-4a."""
import json
import os
import shutil
import subprocess

import numpy as np
import pytest

uproot = pytest.importorskip("uproot")
pytest.importorskip("pyhf")

from cut_scan import plot_scan, scan_cut
from experiment_log import ExperimentLog
from ntuple_probe import probe_file
from plot_validator import validate_figure, validate_manifest
import stat_toolkit as st

AUTOHEP = os.path.join(os.path.dirname(__file__), "..")


def test_full_chain(tmp_path):
    rng = np.random.default_rng(20260709)
    study = str(tmp_path / "shakedown-demo")

    # ---- init-study equivalent ---------------------------------------------
    shutil.copytree(os.path.join(AUTOHEP, "templates", "study"), study)
    subprocess.run(["git", "init", "-q"], cwd=study, check=True)
    log = ExperimentLog(study)
    log.append("note", "orchestrator", "shakedown study initialized", "phase1")
    man = json.load(open(os.path.join(study, "manifest.json")))
    man.update({"study": "shakedown-demo", "blinded_window": [120.0, 130.0]})
    json.dump(man, open(os.path.join(study, "manifest.json"), "w"), indent=1)

    # ---- synthetic inputs: toy H->Z+X four-lepton search ---------------------
    n_sig, n_dat = 20000, 50000
    datadir = os.path.join(study, "data", "user")
    with uproot.recreate(os.path.join(datadir, "signal_mc.root")) as f:
        f["ntuple"] = {
            "fourL_mass": rng.normal(125.0, 1.8, n_sig),
            "dimu_mass": rng.normal(3.097, 0.035, n_sig),
            "lep_iso": rng.exponential(0.05, n_sig),
            "run": np.full(n_sig, 1, np.int64),
            "event": np.arange(n_sig, dtype=np.int64),
        }
    # data: combinatorial bkg + hidden 40-event signal; dimu has a prominent
    # J/psi peak as in real preselection ntuples
    n_jpsi = int(n_dat * 0.4)
    with uproot.recreate(os.path.join(datadir, "data.root")) as f:
        f["ntuple"] = {
            "fourL_mass": np.concatenate([110.0 + rng.exponential(25.0, n_dat),
                                          rng.normal(125.0, 1.8, 40)]),
            "dimu_mass": np.concatenate([
                rng.normal(3.097, 0.035, n_jpsi),
                2.9 + rng.uniform(0, 0.6, n_dat - n_jpsi),
                rng.normal(3.097, 0.035, 40)]),
            "lep_iso": np.concatenate([rng.exponential(0.4, n_dat),
                                       rng.exponential(0.05, 40)]),
            "run": np.full(n_dat + 40, 273158, np.int64),
            "event": np.arange(n_dat + 40, dtype=np.int64),
        }

    # ---- Phase 2: reconnaissance (no schema given) ---------------------------
    ph2 = os.path.join(study, "phases", "phase2")
    rep_dat = probe_file(os.path.join(datadir, "data.root"), entries=5000)
    json.dump(rep_dat, open(os.path.join(ph2, "probe_data.json"), "w"), indent=1)
    peaks = {b: [p.get("pdg_candidate") for p in pk]
             for b, pk in rep_dat["peaks"].items()}
    assert "J/psi(1S)" in (peaks.get("dimu_mass") or []), peaks
    log.append("tool_run", "analyst", f"probe found data peaks: {peaks}",
               "phase2", artifacts=["phases/phase2/probe_data.json"])

    # ---- Phase 3: cut discovery with scan evidence ---------------------------
    sig_iso = uproot.open(os.path.join(datadir, "signal_mc.root"))["ntuple"][
        "lep_iso"].array(library="np")
    dat = uproot.open(os.path.join(datadir, "data.root"))["ntuple"].arrays(
        library="np")
    sb = (dat["fourL_mass"] < 120.0) | (dat["fourL_mass"] > 130.0)  # blinding
    res = scan_cut(sig_iso, dat["lep_iso"][sb], direction="<", fom="punzi")
    assert res["sig_eff_at_best"] > 0.5
    png = os.path.join(study, "phases", "phase3", "scan_lep_iso.png")
    plot_scan(res, "lep_iso", png, title="isolation cut scan (SB background)")
    assert validate_figure(png, blinded=True) == []
    log.append("decision", "analyst",
               f"cut lep_iso < {res['best_cut']:.3f}", "phase3",
               detail={"fom": "punzi", "best_cut": res["best_cut"]},
               artifacts=["phases/phase3/scan_lep_iso.png"])

    # ---- blinding guard: leaky data plot must raise R5 -----------------------
    edges = np.linspace(110, 160, 26)
    mask = dat["lep_iso"] < res["best_cut"]
    counts, _ = np.histogram(dat["fourL_mass"][mask], bins=edges)
    centers = 0.5 * (edges[:-1] + edges[1:])
    counts_blinded = counts.copy()
    counts_blinded[(centers > 120) & (centers < 130)] = 0
    manifest = {
        "kind": "histogram", "title": "four-lepton mass after selection",
        "x_label": "m(4l)", "x_unit": "GeV", "y_label": "Events / 2 GeV",
        "y_unit": "", "lumi_stamp": "toy dataset", "legend": False,
        "blinded_window": [120.0, 130.0], "blinded_region_shown": True,
        "series": [{"name": "data", "role": "data",
                    "values": counts_blinded.tolist(),
                    "yerr": np.sqrt(counts_blinded).tolist(),
                    "bin_edges": edges.tolist()}],
    }
    assert validate_manifest(manifest, blinded=True) == []
    leaky = json.loads(json.dumps(manifest))
    leaky["series"][0]["values"] = counts.tolist()
    assert any(f["check"] == "R5"
               for f in validate_manifest(leaky, blinded=True))

    # ---- Phase 4a: blinded expected limit + injection ------------------------
    sb_rate = np.sum(sb & mask) / np.ptp(dat["fourL_mass"][sb & mask])
    b_sr = float(sb_rate * 10.0)
    s_sr = float(res["sig_eff_at_best"] * 100.0 * 0.99)
    lim = st.upper_limit(signal=[s_sr], background=[b_sr],
                         bkg_uncert=[0.1 * b_sr])
    assert lim["expected"][0] < lim["expected"][2] < lim["expected"][4]
    inj = st.signal_injection([s_sr], [b_sr], mu_true_values=(0.0, 1.0),
                              n_toys=60)
    assert inj["passed"]
    # saturated GoF must REJECT a deliberately wrong (flat) background model
    gof = st.saturated_gof(
        np.histogram(dat["fourL_mass"][sb & mask], bins=10)[0],
        np.full(10, np.sum(sb & mask) / 10.0), n_fitted_params=1)
    assert gof["pvalue"] < 1e-3
    log.append("artifact", "analyst",
               f"expected limit mu < {lim['expected'][2]:.2f}", "phase4a",
               detail={"limit": lim, "injection_passed": inj["passed"]})

    # ---- log integrity --------------------------------------------------------
    assert log.verify() == []
    assert len(log._entries()) == 4
