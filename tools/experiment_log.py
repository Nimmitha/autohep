#!/usr/bin/env python3
"""Append-only experiment log (JSONL).

Every phase action, decision, review verdict, artifact, and human interaction is
recorded here. Entries are never edited or removed; corrections are new entries
with kind="correction" referencing the original entry id.

Library:
    log = ExperimentLog(study_dir)
    log.append(kind="decision", agent="analyst", phase="phase3",
               summary="chose onecand policy", detail={...}, artifacts=["phases/..."])

CLI:
    experiment_log.py append <study_dir> --kind decision --agent analyst \
        --phase phase3 --summary "..." [--detail-json '{}'] [--artifact path ...]
    experiment_log.py verify <study_dir>     # checks hash chain + artifact hashes
    experiment_log.py tail <study_dir> [-n 20]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import sys

LOG_NAME = "EXPERIMENT_LOG.jsonl"

KINDS = {
    "phase_start", "phase_end", "decision", "tool_run", "artifact",
    "review_finding", "review_verdict", "human_gate", "human_response",
    "correction", "note",
}


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class ExperimentLog:
    def __init__(self, study_dir: str):
        self.study_dir = os.path.abspath(study_dir)
        self.path = os.path.join(self.study_dir, LOG_NAME)

    # -- internals ---------------------------------------------------------
    def _entries(self):
        if not os.path.exists(self.path):
            return []
        out = []
        with open(self.path) as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
        return out

    def _chain_hash(self, prev_hash: str, payload: dict) -> str:
        blob = prev_hash + json.dumps(payload, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()

    # -- API ---------------------------------------------------------------
    def append(self, kind: str, agent: str, summary: str, phase: str = "",
               detail: dict | None = None, artifacts: list[str] | None = None) -> dict:
        if kind not in KINDS:
            raise ValueError(f"unknown log kind {kind!r}; allowed: {sorted(KINDS)}")
        entries = self._entries()
        prev_hash = entries[-1]["chain"] if entries else "genesis"
        art_records = []
        for rel in artifacts or []:
            full = os.path.join(self.study_dir, rel)
            rec = {"path": rel}
            if os.path.exists(full):
                rec["sha256"] = _sha256(full)
                rec["bytes"] = os.path.getsize(full)
            else:
                rec["missing"] = True
            art_records.append(rec)
        payload = {
            "id": len(entries),
            "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "kind": kind,
            "agent": agent,
            "phase": phase,
            "summary": summary,
            "detail": detail or {},
            "artifacts": art_records,
        }
        payload["chain"] = self._chain_hash(prev_hash, payload)
        with open(self.path, "a") as f:
            f.write(json.dumps(payload, sort_keys=True) + "\n")
        return payload

    def verify(self) -> list[str]:
        """Return a list of problems (empty == log is intact)."""
        problems = []
        prev_hash = "genesis"
        for i, e in enumerate(self._entries()):
            chain = e.pop("chain")
            if e.get("id") != i:
                problems.append(f"entry {i}: id mismatch ({e.get('id')})")
            if self._chain_hash(prev_hash, e) != chain:
                problems.append(f"entry {i}: chain hash mismatch (log was edited)")
            prev_hash = chain
            for art in e.get("artifacts", []):
                if "sha256" in art:
                    full = os.path.join(self.study_dir, art["path"])
                    if os.path.exists(full) and _sha256(full) != art["sha256"]:
                        problems.append(
                            f"entry {i}: artifact {art['path']} changed since logging")
        return problems


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    ap = sub.add_parser("append")
    ap.add_argument("study_dir")
    ap.add_argument("--kind", required=True, choices=sorted(KINDS))
    ap.add_argument("--agent", required=True)
    ap.add_argument("--phase", default="")
    ap.add_argument("--summary", required=True)
    ap.add_argument("--detail-json", default="{}")
    ap.add_argument("--artifact", action="append", default=[])

    vp = sub.add_parser("verify")
    vp.add_argument("study_dir")

    tp = sub.add_parser("tail")
    tp.add_argument("study_dir")
    tp.add_argument("-n", type=int, default=20)

    a = p.parse_args(argv)
    log = ExperimentLog(a.study_dir)
    if a.cmd == "append":
        e = log.append(a.kind, a.agent, a.summary, a.phase,
                       json.loads(a.detail_json), a.artifact)
        print(json.dumps({"id": e["id"], "chain": e["chain"][:12]}))
    elif a.cmd == "verify":
        problems = log.verify()
        for pr in problems:
            print("PROBLEM:", pr)
        print("OK" if not problems else f"{len(problems)} problem(s)")
        return 1 if problems else 0
    elif a.cmd == "tail":
        for e in log._entries()[-a.n:]:
            print(f"[{e['id']:>4}] {e['ts'][:19]} {e['kind']:<15} "
                  f"{e['agent']:<12} {e['phase']:<8} {e['summary']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
