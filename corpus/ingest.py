#!/usr/bin/env python3
"""Literature corpus ingestion (SciTreeRAG-inspired, simplified).

For each arXiv id: fetch metadata (export.arxiv.org API) and the LaTeX source
tarball, resolve \\input includes, strip comments, split on sectioning commands,
and store a section tree at corpus/index/<id>.json:

    {"arxiv_id", "title", "abstract", "authors", "ingested",
     "sections": [{"path": ["Introduction"], "level": 1, "text": "..."}]}

LaTeX→text uses pandoc when available, else a regex-stripping fallback (modern
HEP papers are LaTeX-sourced, so no OCR stage is needed).

CLI:
    ingest.py --ids 2306.xxxxx 1807.yyyyy [--index-dir corpus/index]
    ingest.py --id-file corpus/papers/seed_papers.txt
Rate-limits itself to 1 request / 3 s per arXiv policy.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
import xml.etree.ElementTree as ET

ARXIV_API = "https://export.arxiv.org/api/query"
ARXIV_SRC = "https://arxiv.org/e-print/{aid}"
ATOM = "{http://www.w3.org/2005/Atom}"


def _get_with_backoff(url, retries=4, base_wait=10, **kwargs):
    import requests

    for attempt in range(retries):
        r = requests.get(url, timeout=120, **kwargs)
        if r.status_code in (429, 500, 502, 503) and attempt < retries - 1:
            wait = base_wait * (2 ** attempt)
            print(f"  {r.status_code} from {url.split('?')[0]} — backing off {wait}s",
                  file=sys.stderr)
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r
    raise RuntimeError("unreachable")


def fetch_metadata(aid: str) -> dict:
    r = _get_with_backoff(ARXIV_API,
                          params={"id_list": aid, "max_results": 1})
    root = ET.fromstring(r.text)
    entry = root.find(f"{ATOM}entry")
    if entry is None:
        raise ValueError(f"arXiv id not found: {aid}")
    return {
        "arxiv_id": aid,
        "title": " ".join((entry.findtext(f"{ATOM}title") or "").split()),
        "abstract": " ".join((entry.findtext(f"{ATOM}summary") or "").split()),
        "authors": [a.findtext(f"{ATOM}name")
                    for a in entry.findall(f"{ATOM}author")][:12],
    }


def fetch_source(aid: str) -> dict[str, str]:
    """Return {filename: content} of .tex/.bbl files in the source tarball."""
    r = _get_with_backoff(ARXIV_SRC.format(aid=aid))
    blob = r.content
    out = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(blob)) as tf:
            for m in tf.getmembers():
                if m.isfile() and m.name.lower().endswith((".tex", ".bbl")):
                    out[m.name] = tf.extractfile(m).read().decode(
                        "utf-8", errors="replace")
    except tarfile.ReadError:
        # single-file (possibly gzipped) submission
        import gzip
        try:
            blob = gzip.decompress(blob)
        except OSError:
            pass
        text = blob.decode("utf-8", errors="replace")
        if "\\documentclass" in text or "\\begin{document}" in text:
            out["main.tex"] = text
    return out


def _main_tex(files: dict[str, str]) -> str:
    """Pick the root file and inline \\input/\\include one level deep."""
    root_name = None
    for name, txt in files.items():
        if "\\begin{document}" in txt:
            root_name = name
            break
    if root_name is None:
        return "\n".join(files.values())
    text = files[root_name]

    def repl(m):
        base = m.group(2).strip()
        for cand in (base, base + ".tex"):
            for name, txt in files.items():
                if name.endswith(cand):
                    return txt
        return ""

    return re.sub(r"\\(input|include)\{([^}]*)\}", repl, text)


def _strip_comments(tex: str) -> str:
    return re.sub(r"(?<!\\)%.*", "", tex)


_FALLBACK_PATTERNS = [
    (r"\\begin\{(equation|align|eqnarray|figure|table|tabular)\*?\}.*?"
     r"\\end\{\1\*?\}", " [MATH/FLOAT] "),
    (r"\\(cite|citep|citet|ref|eqref|label)\{([^}]*)\}", r" [\1:\2] "),
    (r"\\(textbf|textit|emph|mbox|text|textrm)\{([^{}]*)\}", r"\2"),
    (r"\$[^$]{0,300}\$", " [math] "),
    (r"\\[a-zA-Z]+\*?(\[[^\]]*\])?(\{[^{}]*\})?", " "),
    (r"[{}~]", " "),
    (r"\s+", " "),
]


def latex_to_text(tex: str) -> str:
    if shutil.which("pandoc"):
        try:
            p = subprocess.run(["pandoc", "-f", "latex", "-t", "plain",
                                "--wrap=none"], input=tex.encode(),
                               capture_output=True, timeout=120)
            if p.returncode == 0 and p.stdout.strip():
                return p.stdout.decode("utf-8", errors="replace")
        except Exception:
            pass
    out = tex
    for pat, rep in _FALLBACK_PATTERNS:
        out = re.sub(pat, rep, out, flags=re.DOTALL)
    return out.strip()


SECTION_RE = re.compile(
    r"\\(section|subsection|subsubsection)\*?\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}")


def split_sections(tex: str) -> list[dict]:
    """Split document body into a section tree (path = ancestor titles)."""
    body = tex.split("\\begin{document}")[-1].split("\\end{document}")[0]
    body = _strip_comments(body)
    levels = {"section": 1, "subsection": 2, "subsubsection": 3}
    marks = [(m.start(), m.end(), levels[m.group(1)],
              re.sub(r"\\\\|\\[a-zA-Z]+", "", m.group(2)).strip())
             for m in SECTION_RE.finditer(body)]
    sections = []
    stack: list[str] = []
    if marks and marks[0][0] > 200:
        pre = latex_to_text(body[: marks[0][0]])
        if pre.strip():
            sections.append({"path": ["(preamble)"], "level": 0,
                             "text": pre[:20000]})
    for i, (s, e, lvl, title) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(body)
        stack = stack[: lvl - 1] + [title]
        text = latex_to_text(body[e:end]).strip()
        if text:
            sections.append({"path": list(stack), "level": lvl,
                             "text": text[:20000]})
    if not sections:
        txt = latex_to_text(body)
        if txt.strip():
            sections = [{"path": ["(document)"], "level": 0,
                         "text": txt[:60000]}]
    return sections


def ingest_one(aid: str, index_dir: str) -> dict:
    os.makedirs(index_dir, exist_ok=True)
    out_path = os.path.join(index_dir, aid.replace("/", "_") + ".json")
    if os.path.exists(out_path):
        return {"arxiv_id": aid, "status": "cached"}
    meta_ok = True
    try:
        meta = fetch_metadata(aid)
    except Exception as e:
        # export API outage should not block source ingestion
        meta = {"arxiv_id": aid, "title": "", "abstract": "", "authors": []}
        meta_ok = False
        print(f"  metadata fetch failed for {aid}: {e}", file=sys.stderr)
    time.sleep(3)
    try:
        files = fetch_source(aid)
        sections = split_sections(_main_tex(files)) if files else []
        status = "ok" if sections else "metadata_only"
    except Exception as e:
        sections, status = [], f"source_failed: {e}"
    if not meta_ok:
        status += "+metadata_failed"
    if not sections and not meta_ok:
        return {"arxiv_id": aid, "status": "failed_entirely (not cached)"}
    doc = {**meta, "ingested": time.strftime("%Y-%m-%d"),
           "sections": sections, "status": status}
    with open(out_path, "w") as f:
        json.dump(doc, f)
    return {"arxiv_id": aid, "status": status, "n_sections": len(sections)}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ids", nargs="*", default=[])
    p.add_argument("--id-file")
    p.add_argument("--index-dir",
                   default=os.path.join(os.path.dirname(__file__), "index"))
    a = p.parse_args(argv)
    ids = list(a.ids)
    if a.id_file:
        with open(a.id_file) as f:
            for line in f:
                line = line.split("#")[0].strip()
                if line:
                    ids.append(line)
    if not ids:
        p.error("no arXiv ids given")
    for i, aid in enumerate(ids):
        res = ingest_one(aid, a.index_dir)
        print(json.dumps(res))
        if i + 1 < len(ids) and res.get("status") != "cached":
            time.sleep(3)
    return 0


if __name__ == "__main__":
    sys.exit(main())
