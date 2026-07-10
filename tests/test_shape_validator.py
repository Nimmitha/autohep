import numpy as np

from shape_validator import validate_fit


def good_record():
    return {
        "model_name": "sig_gauss_bkg_exp",
        "converged": True,
        "n_data": 5000,
        "params": [
            {"name": "mean", "value": 91.2, "error": 0.05},
            {"name": "sigma", "value": 2.5, "error": 0.04, "limit_lo": 0.1,
             "limit_hi": 10.0},
        ],
        "covariance": [[0.0025, 0.0001], [0.0001, 0.0016]],
        "gof": {"method": "saturated", "pvalue": 0.42},
        "pulls": list(np.random.default_rng(0).normal(0, 1, 40)),
        "refits": [{"label": "altstart_0",
                    "params": [{"name": "mean", "value": 91.21},
                               {"name": "sigma", "value": 2.51}]}],
    }


def checks(fnd):
    return {f["check"] for f in fnd}


def test_good_record_clean():
    assert validate_fit(good_record()) == []


def test_nonconvergence_blocks():
    r = good_record()
    r["converged"] = False
    fnd = validate_fit(r)
    assert "S1" in checks(fnd)
    assert any(f["category"] == "A" for f in fnd)


def test_rank_deficient_covariance():
    r = good_record()
    r["covariance"] = [[0.0025, 0.0021], [0.0021, 0.0016]]  # det < 0: not pos-def
    assert "S5" in checks(validate_fit(r))


def test_suspicious_gof_near_one():
    r = good_record()
    r["gof"]["pvalue"] = 0.9999
    fnd = validate_fit(r)
    assert "S14" in checks(fnd)
    assert any(f["category"] == "A" for f in fnd)


def test_rejected_gof():
    r = good_record()
    r["gof"]["pvalue"] = 1e-5
    assert "S13" in checks(validate_fit(r))


def test_naive_chi2_flagged():
    r = good_record()
    r["gof"] = {"method": "chi2/ndf", "pvalue": 0.5}
    assert "S12" in checks(validate_fit(r))


def test_parameter_at_limit():
    r = good_record()
    r["params"][1]["value"] = 0.1001
    r["params"][1]["error"] = 0.05
    assert "S9" in checks(validate_fit(r))


def test_overparameterized():
    r = good_record()
    r["n_data"] = 2
    fnd = validate_fit(r)
    assert "S2" in checks(fnd)


def test_biased_pulls():
    r = good_record()
    r["pulls"] = list(np.random.default_rng(1).normal(1.5, 1.0, 40))
    assert "S15" in checks(validate_fit(r))


def test_unstable_refit():
    r = good_record()
    r["refits"] = [{"label": "altstart_0",
                    "params": [{"name": "mean", "value": 91.5}]}]  # 6 sigma drift
    assert "S19" in checks(validate_fit(r))


def test_missing_covariance_flagged():
    r = good_record()
    del r["covariance"]
    assert "S3" in checks(validate_fit(r))
