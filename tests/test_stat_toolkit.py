import numpy as np
import pytest

pyhf = pytest.importorskip("pyhf")

import stat_toolkit as st


def test_expected_limit_counting_experiment():
    # s=10, b=100 per unit mu: sigma_b = sqrt(100) = 10, so the 95% CL limit on
    # mu should sit near 1.96*10/10 ~ 2 (CLs pushes it slightly higher).
    res = st.upper_limit(signal=[10.0], background=[100.0])
    med = res["expected"][2]
    assert 1.5 < med < 3.5
    # bands ordered
    e = res["expected"]
    assert e[0] < e[1] < e[2] < e[3] < e[4]
    assert res["observed"] is None  # blinded


def test_observed_limit_with_data():
    res = st.upper_limit(signal=[10.0], background=[100.0], data=[100.0])
    assert res["observed"] == pytest.approx(res["expected"][2], rel=0.15)
    # upward fluctuation weakens the limit
    res_up = st.upper_limit(signal=[10.0], background=[100.0], data=[130.0])
    assert res_up["observed"] > res["observed"]


def test_limit_scales_with_signal_efficiency():
    res1 = st.upper_limit(signal=[10.0], background=[100.0])
    res2 = st.upper_limit(signal=[20.0], background=[100.0])
    assert res2["expected"][2] == pytest.approx(res1["expected"][2] / 2, rel=0.1)


def test_asimov_significance_known_value():
    # s=10, b=100: Z = sqrt(2*((110)*ln(1.1)-10)) ~ 0.983
    z = st.asimov_significance([10.0], [100.0])
    assert z == pytest.approx(0.983, abs=0.01)


def test_saturated_gof():
    e = np.full(20, 50.0)
    assert st.saturated_gof(e, e)["pvalue"] == pytest.approx(1.0)
    rng = np.random.default_rng(11)
    o = rng.poisson(e)
    res = st.saturated_gof(o, e)
    assert 0.0 < res["pvalue"] < 1.0
    assert res["method"] == "saturated"
    # grossly wrong model rejected
    bad = st.saturated_gof(o, e * 3)
    assert bad["pvalue"] < 1e-6


def test_saturated_gof_guards():
    with pytest.raises(ValueError):
        st.saturated_gof([1.0], [0.0])
    with pytest.raises(ValueError):
        st.saturated_gof([1.0, 2.0], [1.0, 2.0], n_fitted_params=2)


def test_signal_injection_unbiased():
    res = st.signal_injection(signal=[50.0], background=[100.0],
                              mu_true_values=(0.0, 1.0), n_toys=80)
    assert res["passed"], res
    for pt in res["points"]:
        assert abs(pt["bias"]) < 0.2


def test_unbinned_fit_recovers_gaussian():
    from shape_validator import validate_fit

    rng = np.random.default_rng(5)
    data = rng.normal(3.1, 0.05, 4000)

    def nll(mean, sigma):
        return float(np.sum(0.5 * ((data - mean) / sigma) ** 2
                            + np.log(sigma)))

    rec = st.unbinned_fit(nll, start={"mean": 3.0, "sigma": 0.1},
                          limits={"sigma": (1e-3, 1.0)}, n_data=data.size,
                          model_name="gauss",
                          stability_starts=[{"mean": 3.3, "sigma": 0.2}])
    assert rec["converged"]
    vals = {p["name"]: p for p in rec["params"]}
    assert vals["mean"]["value"] == pytest.approx(3.1, abs=0.01)
    assert vals["sigma"]["value"] == pytest.approx(0.05, abs=0.005)
    # record integrates with shape_validator; only minor findings allowed
    findings = validate_fit({**rec, "gof": {"method": "saturated", "pvalue": 0.5},
                             "pulls": list(rng.normal(0, 1, 30))})
    assert not [f for f in findings if f["category"] == "A"]
