import numpy as np
import pytest

uproot = pytest.importorskip("uproot")

from ntuple_probe import probe_arrays, probe_file, _find_peaks


@pytest.fixture
def toy_root(tmp_path):
    rng = np.random.default_rng(42)
    n = 5000
    jpsi = rng.normal(3.0969, 0.03, int(n * 0.3))
    comb = rng.uniform(2.5, 3.7, n - jpsi.size)
    path = tmp_path / "toy.root"
    with uproot.recreate(path) as f:
        f["ntuple"] = {
            "dimu_mass": np.concatenate([jpsi, comb]),
            "pt": rng.exponential(20.0, n),
            "charge": rng.choice([-1.0, 1.0], n),
            "run": np.full(n, 316000, dtype=np.int64),
            "event": np.arange(n, dtype=np.int64),
        }
    return str(path)


def test_peak_finder_annotates_jpsi():
    rng = np.random.default_rng(1)
    x = np.concatenate([rng.normal(3.0969, 0.03, 3000), rng.uniform(2.5, 3.7, 7000)])
    peaks = _find_peaks(x)
    assert peaks, "peak not found"
    assert peaks[0]["pdg_candidate"] == "J/psi(1S)"


def test_probe_file_report(toy_root):
    rep = probe_file(toy_root, entries=5000)
    assert rep["tree"] == "ntuple"
    assert rep["num_entries"] == 5000
    assert "dimu_mass" in rep["peaks"]
    assert rep["branches"]["charge"]["stats"]["looks_flaglike"]
    assert not rep["branches"]["pt"]["stats"]["looks_flaglike"]
    assert rep["duplicate_check"]["n_duplicate_ids"] == 0


def test_probe_arrays_handles_jagged_and_nan():
    import awkward as ak

    arrays = {
        "jagged_pt": ak.Array([[1.0, 2.0], [3.0], [], [4.0, 5.0, 6.0]] * 100),
        "with_nan": np.array(([1.0, np.nan] * 200)),
    }
    rep = probe_arrays(arrays, correlations=False)
    assert rep["branches"]["jagged_pt"]["jagged"]
    assert rep["branches"]["jagged_pt"]["mean_multiplicity"] == pytest.approx(1.5)
    assert rep["branches"]["with_nan"]["stats"]["frac_nonfinite"] == pytest.approx(0.5)


def test_correlation_detection():
    rng = np.random.default_rng(3)
    x = rng.normal(size=2000)
    rep = probe_arrays({"a": x, "b": 2 * x + 0.01 * rng.normal(size=2000),
                        "c": rng.normal(size=2000)})
    pairs = {(c["a"], c["b"]) for c in rep["correlations"]}
    assert ("a", "b") in pairs
    assert all("c" not in pr for pr in pairs)
