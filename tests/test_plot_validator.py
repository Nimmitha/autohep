import json

import numpy as np
import pytest

from plot_validator import validate_figure, validate_manifest


def clean_manifest():
    edges = list(np.linspace(80.0, 100.0, 11))
    bkg = [50, 55, 60, 80, 120, 118, 78, 62, 54, 48]
    data = [52, 51, 63, 84, 115, 122, 74, 65, 50, 47]
    return {
        "kind": "histogram",
        "title": "Z candidate mass",
        "x_label": "m(ll)", "x_unit": "GeV",
        "y_label": "Events / 2 GeV", "y_unit": "",
        "lumi_stamp": "59.7 fb^-1 (13 TeV)",
        "legend": True,
        "series": [
            {"name": "data", "role": "data", "values": data,
             "yerr": [float(np.sqrt(v)) for v in data], "bin_edges": edges},
            {"name": "bkg model", "role": "background", "values": bkg,
             "bin_edges": edges},
        ],
        "blinded_region_shown": False,
    }


def cats(findings):
    return [f["category"] for f in findings]


def checks(findings):
    return {f["check"] for f in findings}


def test_clean_manifest_passes():
    assert validate_manifest(clean_manifest()) == []


def test_missing_axis_labels():
    m = clean_manifest()
    m["x_label"] = ""
    m["y_label"] = "y"
    fnd = validate_manifest(m)
    assert {"F4", "F5"} <= checks(fnd)


def test_data_without_lumi_stamp():
    m = clean_manifest()
    m["lumi_stamp"] = ""
    assert "F7" in checks(validate_manifest(m))


def test_negative_yields_and_red_flag():
    m = clean_manifest()
    m["series"][1]["values"][3] = -40.0
    fnd = validate_manifest(m)
    assert "P2" in checks(fnd)
    assert "R1" in checks(fnd)
    assert "A" in cats(fnd)


def test_efficiency_bounds():
    m = clean_manifest()
    m["series"].append({"name": "eff", "role": "efficiency",
                        "values": [0.5, 1.2, 0.9]})
    fnd = validate_manifest(m)
    assert "P3" in checks(fnd)
    assert "R2" in checks(fnd)


def test_blinding_violation_red_flag():
    m = clean_manifest()
    m["blinded_window"] = [88.0, 94.0]
    m["blinded_region_shown"] = True
    fnd = validate_manifest(m, blinded=True)
    assert "R5" in checks(fnd)
    # after human unblinding the same figure is acceptable
    fnd2 = validate_manifest(m, blinded=False)
    assert "R5" not in checks(fnd2)


def test_blinded_data_ok_when_window_empty():
    m = clean_manifest()
    m["blinded_window"] = [88.0, 94.0]
    m["blinded_region_shown"] = True
    for s in m["series"]:
        if s["role"] == "data":
            s["values"] = [52, 51, 63, 84, 0, 0, 0, 65, 50, 47]
    assert "R5" not in checks(validate_manifest(m, blinded=True))


def test_zero_errors_on_data():
    m = clean_manifest()
    m["series"][0]["yerr"] = [0.0] * 10
    assert "R8" in checks(validate_manifest(m))


def test_normalization_red_flag():
    m = clean_manifest()
    m["series"][1]["values"] = [v * 20 for v in m["series"][1]["values"]]
    fnd = validate_manifest(m)
    assert "R6" in checks(fnd)


def test_copy_paste_detection():
    m = clean_manifest()
    m["series"][1]["values"] = list(m["series"][0]["values"])
    assert "R7" in checks(validate_manifest(m))


def test_nonmonotonic_edges():
    m = clean_manifest()
    e = list(m["series"][0]["bin_edges"])
    e[3], e[4] = e[4], e[3]
    m["series"][0]["bin_edges"] = e
    assert "R9" in checks(validate_manifest(m))


def test_missing_manifest_is_red_flag(tmp_path):
    png = tmp_path / "fig.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n123")
    fnd = validate_figure(str(png))
    assert checks(fnd) == {"R10"}
    assert cats(fnd) == ["A"]


def test_figure_with_sidecar(tmp_path):
    png = tmp_path / "fig.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n123")
    (tmp_path / "fig.plot.json").write_text(json.dumps(clean_manifest()))
    assert validate_figure(str(png)) == []
