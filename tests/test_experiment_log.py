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


def test_unresolvable_artifact_path_fails_loudly(tmp_path):
    """A wrong (e.g. repo-root-relative) artifact path must raise, never be
    silently recorded as missing - integrity pinning depends on it."""
    log = ExperimentLog(str(tmp_path))
    with pytest.raises(FileNotFoundError, match="relative to the study dir"):
        log.append("artifact", "analyst", "bad path", "phase1",
                   artifacts=["studies/foo/STRATEGY.md"])
    # nothing was written
    assert log._entries() == []


def test_allow_missing_and_verify_flags_unpinned(tmp_path):
    log = ExperimentLog(str(tmp_path))
    log.append("note", "analyst", "aspirational artifact", "phase1",
               artifacts=["STRATEGY.md"], allow_missing=True)
    assert log.verify() == []  # file genuinely absent: acceptable
    (tmp_path / "STRATEGY.md").write_text("now it exists")
    problems = log.verify()
    assert any("re-log it to pin" in p for p in problems)
    # re-logging with the hash pins it and supersedes the missing-flag record
    e = log.append("artifact", "analyst", "strategy pinned", "phase1",
                   artifacts=["STRATEGY.md"])
    assert e["artifacts"][0]["sha256"]
    assert log.verify() == []


def test_superseded_pin_not_flagged_latest_pin_enforced(tmp_path):
    """A re-logged (revised) artifact supersedes earlier pins of the same
    path: verify checks the file against the latest pin only, so a legitimate
    ITERATE revision does not poison verify forever - but tampering with the
    file after its latest pin is still caught."""
    art = tmp_path / "STRATEGY.md"
    art.write_text("strategy v1")
    log = ExperimentLog(str(tmp_path))
    log.append("artifact", "analyst", "strategy v1", "phase1",
               artifacts=["STRATEGY.md"])
    art.write_text("strategy v2 (iteration remediation)")
    assert any("changed since logging" in p for p in log.verify())
    log.append("artifact", "analyst", "strategy v2 re-pinned", "phase1",
               artifacts=["STRATEGY.md"])
    assert log.verify() == []  # old pin superseded, latest pin matches
    art.write_text("strategy v2 -- tampered after pinning")
    problems = log.verify()
    assert len(problems) == 1 and "changed since logging" in problems[0]
