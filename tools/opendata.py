#!/usr/bin/env python3
"""CERN Open Data acquisition: search records, list files, download, and apply
certified-luminosity (golden JSON) filtering to NanoAOD.

The CERN Open Data portal API (https://opendata.cern.ch/api/records/) is public.
NanoAOD files are plain ROOT and readable with uproot — no CMSSW required.
Downloads go over HTTPS (root:// URLs are rewritten via the EOS public gateway
when possible).

CLI:
    opendata.py search "SingleMuon 2016 NanoAOD" [--n 10]
    opendata.py record 30563                    # show metadata + file index
    opendata.py files 30563 [--limit 5]
    opendata.py download <url> --dest data/opendata/
    opendata.py lumifilter in.root golden.json --tree Events --out filtered.root
"""
from __future__ import annotations

import argparse
import json
import os
import sys

API = "https://opendata.cern.ch/api/records"


def _get(url, **params):
    import requests

    r = requests.get(url, params=params or None, timeout=60,
                     headers={"Accept": "application/json"})
    r.raise_for_status()
    return r.json()


def search(query: str, n: int = 10) -> list[dict]:
    js = _get(API, q=query, size=n, page=1)
    out = []
    for hit in js.get("hits", {}).get("hits", []):
        md = hit.get("metadata", {})
        out.append({
            "recid": hit.get("id"),
            "title": md.get("title"),
            "type": (md.get("type") or {}).get("primary"),
            "experiment": md.get("experiment"),
            "year": md.get("date_created"),
        })
    return out


def record(recid: int) -> dict:
    return _get(f"{API}/{recid}").get("metadata", {})


def file_urls(recid: int, limit: int | None = None) -> list[dict]:
    """Return [{'uri', 'size', 'checksum'}] for a record. Records with large
    file counts publish *file-index* JSON files; those are expanded."""
    md = record(recid)
    files = md.get("files", [])
    out = []
    for f in files:
        uri = f.get("uri", "")
        if uri.endswith("_file_index.json") or f.get("key", "").endswith(
                "_file_index.json"):
            try:
                idx = _get(_https(uri))
                for entry in idx:
                    out.append({"uri": entry.get("uri"),
                                "size": entry.get("size"),
                                "checksum": entry.get("checksum")})
            except Exception as e:
                out.append({"uri": uri, "error": f"index fetch failed: {e}"})
        elif not uri.endswith("_file_index.txt"):
            out.append({"uri": uri, "size": f.get("size"),
                        "checksum": f.get("checksum")})
    return out[:limit] if limit else out


def _https(uri: str) -> str:
    """Rewrite root://eospublic.cern.ch//eos/... to the HTTPS gateway."""
    if uri.startswith("root://eospublic.cern.ch/"):
        path = uri.split("root://eospublic.cern.ch/", 1)[1]
        return "https://eospublic.cern.ch/" + path.lstrip("/")
    if uri.startswith("http"):
        return uri
    return uri


def download(uri: str, dest_dir: str, chunk=1 << 20) -> str:
    import requests

    url = _https(uri)
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, os.path.basename(url))
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return dest  # idempotent
    tmp = dest + ".part"
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for c in r.iter_content(chunk_size=chunk):
                f.write(c)
    os.replace(tmp, dest)
    return dest


# ---------------------------------------------------------------------------
# golden-JSON lumi filtering
# ---------------------------------------------------------------------------

def load_lumi_mask(golden_json_path: str) -> dict:
    """{run(int): [(lo, hi), ...]} inclusive lumisection ranges."""
    with open(golden_json_path) as f:
        raw = json.load(f)
    return {int(run): [(int(a), int(b)) for a, b in ranges]
            for run, ranges in raw.items()}


def lumi_mask_events(runs, lumis, mask: dict):
    """Vectorized bool mask: event passes if (run, lumi) is certified."""
    import numpy as np

    runs = np.asarray(runs)
    lumis = np.asarray(lumis)
    out = np.zeros(runs.shape, dtype=bool)
    for run in np.unique(runs):
        ranges = mask.get(int(run))
        if not ranges:
            continue
        sel = runs == run
        ls = lumis[sel]
        ok = np.zeros(ls.shape, dtype=bool)
        for lo, hi in ranges:
            ok |= (ls >= lo) & (ls <= hi)
        out[sel] = ok
    return out


def lumifilter_file(in_path: str, golden_json_path: str, out_path: str,
                    tree: str = "Events", run_branch: str = "run",
                    lumi_branch: str = "luminosityBlock",
                    step: int = 200_000) -> dict:
    """Stream a NanoAOD-like file, keep only certified (run, lumi) events."""
    import awkward as ak
    import uproot

    mask = load_lumi_mask(golden_json_path)
    n_in = n_out = 0
    writer = None
    try:
        for chunk in uproot.iterate(f"{in_path}:{tree}", step_size=step,
                                    library="ak"):
            n_in += len(chunk)
            keep = lumi_mask_events(ak.to_numpy(chunk[run_branch]),
                                    ak.to_numpy(chunk[lumi_branch]), mask)
            passed = chunk[keep]
            n_out += len(passed)
            if len(passed):
                if writer is None:
                    writer = uproot.recreate(out_path)
                    writer[tree] = passed
                else:
                    writer[tree].extend(passed)
    finally:
        if writer is not None:
            writer.close()
    return {"input": in_path, "output": out_path if writer else None,
            "events_in": n_in, "events_out": n_out,
            "certified_fraction": (n_out / n_in) if n_in else 0.0}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("search"); sp.add_argument("query"); sp.add_argument("--n", type=int, default=10)
    rp = sub.add_parser("record"); rp.add_argument("recid", type=int)
    fp = sub.add_parser("files"); fp.add_argument("recid", type=int); fp.add_argument("--limit", type=int, default=None)
    dp = sub.add_parser("download"); dp.add_argument("uri"); dp.add_argument("--dest", required=True)
    lp = sub.add_parser("lumifilter")
    lp.add_argument("input"); lp.add_argument("golden_json")
    lp.add_argument("--tree", default="Events"); lp.add_argument("--out", required=True)
    a = p.parse_args(argv)
    if a.cmd == "search":
        print(json.dumps(search(a.query, a.n), indent=1))
    elif a.cmd == "record":
        print(json.dumps(record(a.recid), indent=1))
    elif a.cmd == "files":
        print(json.dumps(file_urls(a.recid, a.limit), indent=1))
    elif a.cmd == "download":
        print(download(a.uri, a.dest))
    elif a.cmd == "lumifilter":
        print(json.dumps(lumifilter_file(a.input, a.golden_json, a.out, a.tree),
                         indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
