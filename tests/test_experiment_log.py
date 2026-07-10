import json

import pytest

from experiment_log import ExperimentLog


def test_append_and_verify(tmp_path):
    log = ExperimentLog(str(tmp_path))
    e0 = log.append("phase_start", "orchestrator", "Phase 1 begins", phase="phase1")
    e1 = log.append("decision", "analyst", "chose Punzi FoM", phase="phase1",
                    detail={"alternatives": ["s_sqrt_sb"]})
    assert e0["id"] == 0 and e1["id"] == 1
    assert log.verify() == []


def test_artifact_hashing_and_change_detection(tmp_path):
    art = tmp_path / "STRATEGY.md"
    art.write_text("strategy v1")
    log = ExperimentLog(str(tmp_path))
    log.append("artifact", "analyst", "strategy written", phase="phase1",
               artifacts=["STRATEGY.md"])
    assert log.verify() == []
    art.write_text("strategy v2 -- silently changed")
    problems = log.verify()
    assert any("changed since logging" in p for p in problems)


def test_tamper_detection(tmp_path):
    log = ExperimentLog(str(tmp_path))
    log.append("note", "analyst", "a")
    log.append("note", "analyst", "b")
    lines = open(log.path).read().splitlines()
    entry = json.loads(lines[0])
    entry["summary"] = "a EDITED"
    lines[0] = json.dumps(entry, sort_keys=True)
    open(log.path, "w").write("\n".join(lines) + "\n")
    assert any("chain hash mismatch" in p for p in log.verify())


def test_unknown_kind_rejected(tmp_path):
    log = ExperimentLog(str(tmp_path))
    with pytest.raises(ValueError):
        log.append("banana", "analyst", "nope")
