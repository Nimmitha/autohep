import json

import numpy as np
import pytest

from crab_configgen import generate
from opendata import _https, load_lumi_mask, lumi_mask_events


# ---------------------------------------------------------------- opendata --

def test_https_rewrite():
    uri = "root://eospublic.cern.ch//eos/opendata/cms/x.root"
    assert _https(uri) == "https://eospublic.cern.ch/eos/opendata/cms/x.root"
    assert _https("https://a/b.root") == "https://a/b.root"


def test_lumi_mask(tmp_path):
    golden = tmp_path / "golden.json"
    golden.write_text(json.dumps({"273158": [[1, 10], [20, 30]],
                                  "273302": [[5, 5]]}))
    mask = load_lumi_mask(str(golden))
    assert mask[273158] == [(1, 10), (20, 30)]
    runs = np.array([273158, 273158, 273158, 273302, 273302, 999999])
    lumis = np.array([5, 15, 25, 5, 6, 1])
    keep = lumi_mask_events(runs, lumis, mask)
    assert keep.tolist() == [True, False, True, True, False, False]


@pytest.mark.skipif(True, reason="network test — run manually against the "
                    "CERN Open Data portal")
def test_portal_search_live():
    from opendata import search
    hits = search("SingleMuon 2016 NanoAOD", n=3)
    assert hits


# ------------------------------------------------------------------- crab --

def valid_spec():
    return {
        "request_name": "TTree_13TeV_test_2018C",
        "input_dataset": "/EGamma/Run2018C-UL2018_MiniAODv2-v1/MINIAOD",
        "psetname": "run_TTree_cfg.py",
        "lumi_mask": "Cert_314472-325175_Legacy2018.json",
        "out_lfn_base": "/store/user/tester/autohep",
    }


def test_generate_crab_config(tmp_path):
    res = generate(valid_spec(), str(tmp_path))
    cfg = open(res["config"]).read()
    assert "config.Data.inputDataset = '/EGamma/Run2018C-UL2018_MiniAODv2-v1/MINIAOD'" in cfg
    assert "config.Data.splitting = 'LumiBased'" in cfg
    assert "lumiMask" in cfg
    sub = open(res["submit_script"]).read()
    assert "voms-proxy-info" in sub
    assert res["notes"] == []


def test_data_requires_lumi_mask(tmp_path):
    spec = valid_spec()
    spec.pop("lumi_mask")
    with pytest.raises(ValueError, match="lumi_mask"):
        generate(spec, str(tmp_path))


def test_mc_spec_skips_lumi_mask(tmp_path):
    spec = valid_spec()
    spec.pop("lumi_mask")
    spec["is_mc"] = True
    res = generate(spec, str(tmp_path))
    cfg = open(res["config"]).read()
    assert "FileBased" in cfg
    assert "lumiMask" not in cfg


def test_bad_dataset_rejected(tmp_path):
    spec = valid_spec()
    spec["input_dataset"] = "EGamma-2018C"
    with pytest.raises(ValueError, match="DAS path"):
        generate(spec, str(tmp_path))
