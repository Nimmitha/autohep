---
name: acquire-data
description: Get input data for a study — validate user-provided ntuples, download CMS Open Data, apply golden-JSON lumi filtering, or generate CRAB configs for the human to submit. Use when a study needs data or the user mentions samples/datasets/open data/CRAB.
---

# acquire-data

Three routes; pick per the study's needs. All acquired files land under
`studies/<name>/data/` and are logged with hashes.

## Route A — user-provided ntuples (primary for collaboration data & signal MC)

1. User copies/symlinks files into `studies/<name>/data/user/`.
2. Probe every file: `python tools/ntuple_probe.py <file> --out
   studies/<name>/data/user/<file>.probe.json` — this is reconnaissance, not
   schema enforcement; there is no fixed schema by design.
3. Sanity gate: nonzero entries, a readable tree, NaN fraction < 10% per branch;
   failures go back to the user, never silently dropped.
4. Log each accepted file (`artifact` entry with sha256).

## Route B — CMS Open Data (autonomous; reduced-lumi demonstrations)

1. Find records: `python tools/opendata.py search "<primary dataset> <year> NanoAOD"`.
   Collision data and many MC sets for 2016 (and earlier) are public; NanoAOD is
   uproot-readable directly.
2. Inspect: `python tools/opendata.py record <recid>`; get file URIs with
   `python tools/opendata.py files <recid> --limit N`.
3. Download a bounded sample (respect `framework/scaling.md`; start with 1–2
   files): `python tools/opendata.py download <uri> --dest studies/<name>/data/opendata/`.
4. Collision data MUST be lumi-filtered with the matching validation JSON
   (also published on the portal — search "validated runs <year>"):
   `python tools/opendata.py lumifilter in.root golden.json --out filtered.root`.
   Record the certified fraction in the log.
5. Record integrated-luminosity bookkeeping in the study artifact — open data is
   a partial-lumi demonstration; never present it as the full-dataset result.

## Route C — CRAB config generation (human submits; no grid auth here)

1. Build a job spec (request name, DAS dataset path, CMSSW pset, golden JSON,
   splitting) — take the dataset path from the user or the study's strategy.
2. `python tools/crab_configgen.py --spec spec.json --out-dir
   studies/<name>/crab/<era>/` — emits crabConfig + submit script.
3. Hand the user the paths and the submit instructions printed by the tool;
   log a `human_gate` entry. The user runs it on LPC/lxplus and copies outputs
   back via Route A.

Never fetch data from any source other than the CERN Open Data portal or the
user's own paths.
