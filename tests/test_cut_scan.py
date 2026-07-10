import numpy as np
import pytest

from cut_scan import apply_cuts, n_minus_one, scan_cut


@pytest.fixture
def separated_samples():
    rng = np.random.default_rng(7)
    sig = rng.normal(2.0, 0.5, 20000)   # signal high
    bkg = rng.normal(0.0, 0.5, 20000)   # background low
    return sig, bkg


def test_scan_finds_reasonable_optimum(separated_samples):
    sig, bkg = separated_samples
    res = scan_cut(sig, bkg, direction=">", fom="s_sqrt_sb")
    # optimum should sit between the two population means
    assert 0.0 < res["best_cut"] < 2.0
    assert res["sig_eff_at_best"] > 0.8
    assert res["bkg_rej_at_best"] > 0.8


def test_all_foms_run(separated_samples):
    sig, bkg = separated_samples
    for fom in ("punzi", "s_sqrt_sb", "s_sqrt_b", "sig_asimov"):
        res = scan_cut(sig, bkg, fom=fom)
        assert np.isfinite(res["best_fom"]) and res["best_fom"] > 0


def test_direction_less_than(separated_samples):
    sig, bkg = separated_samples
    # swap roles: now signal is the low population, cut with '<'
    res = scan_cut(bkg, sig, direction="<", fom="s_sqrt_sb")
    assert 0.0 < res["best_cut"] < 2.0
    assert res["sig_eff_at_best"] > 0.8


def test_weights_change_counts(separated_samples):
    sig, bkg = separated_samples
    res1 = scan_cut(sig, bkg)
    res2 = scan_cut(sig, bkg, sig_w=np.full(sig.size, 2.0))
    assert res2["s"][0] == pytest.approx(2 * res1["s"][0])
    # efficiencies are weight-normalized, so the optimum is unchanged
    assert res2["sig_eff_at_best"] == pytest.approx(res1["sig_eff_at_best"], abs=0.02)


def test_overtight_warning():
    rng = np.random.default_rng(8)
    # overlapping populations: punzi with tiny bkg tail forces tight optimum
    sig = rng.normal(0.0, 1.0, 5000)
    bkg = rng.normal(0.0, 1.0, 500000)
    res = scan_cut(sig, bkg, fom="s_sqrt_b")
    if res["sig_eff_at_best"] < 0.5:
        assert any("over-tight" in w for w in res["warnings"])


def test_empty_sample_raises():
    with pytest.raises(ValueError):
        scan_cut(np.array([]), np.array([1.0, 2.0]))


def test_apply_cuts_and_n_minus_one(separated_samples):
    sig, bkg = separated_samples
    rng = np.random.default_rng(9)
    sig_arrays = {"x": sig, "iso": rng.uniform(0, 1, sig.size)}
    bkg_arrays = {"x": bkg, "iso": rng.uniform(0, 2, bkg.size)}
    cuts = [{"var": "x", "direction": ">", "value": 1.0},
            {"var": "iso", "direction": "<", "value": 0.9}]
    mask = apply_cuts(sig_arrays, cuts)
    assert 0 < mask.sum() < sig.size
    res = n_minus_one(sig_arrays, bkg_arrays, cuts, fom="s_sqrt_sb")
    assert len(res["n_minus_one"]) == 2
    for row in res["n_minus_one"]:
        assert row["s_without"] >= res["full"]["s"]
        assert row["b_without"] >= res["full"]["b"]


def test_plot_scan_writes_manifest(tmp_path, separated_samples):
    from cut_scan import plot_scan

    sig, bkg = separated_samples
    res = scan_cut(sig, bkg)
    png = str(tmp_path / "scan_x.png")
    plot_scan(res, "x", png, title="toy scan")
    import json
    import os
    assert os.path.getsize(png) > 0
    man = json.load(open(png.replace(".png", ".plot.json")))
    assert man["kind"] == "cut_scan"
    assert man["series"][0]["role"] == "efficiency"
