#!/usr/bin/env python3
"""Hierarchical retrieval over the ingested corpus.

Two-stage scoring that exploits document structure (tree-RAG style, no
embeddings): a paper-level score (title + abstract TF-IDF) gates and boosts a
section-level score, so hits come back as (paper, section-path, snippet) rather
than flat chunks.

CLI:
    search.py "J/psi polarization systematic" [--k 8] [--index-dir corpus/index]
    search.py --paper 1807.xxxxx --section "Systematic uncertainties"  # fetch text
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from collections import Counter

TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9/+\-']*")


def _tokens(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


class Corpus:
    def __init__(self, index_dir: str):
        self.index_dir = index_dir
        self.docs = []
        for fn in sorted(os.listdir(index_dir)) if os.path.isdir(index_dir) else []:
            if fn.endswith(".json"):
                with open(os.path.join(index_dir, fn)) as f:
                    self.docs.append(json.load(f))
        # document frequencies over sections
        self.df: Counter = Counter()
        self.n_sections = 0
        for d in self.docs:
            for s in d.get("sections", []):
                self.n_sections += 1
                self.df.update(set(_tokens(" ".join(s["path"]) + " " + s["text"])))

    def _idf(self, tok: str) -> float:
        return math.log((self.n_sections + 1) / (self.df.get(tok, 0) + 0.5))

    def _score(self, q_toks: list[str], text: str, length_norm: float = 0.4) -> float:
        toks = _tokens(text)
        if not toks:
            return 0.0
        tf = Counter(toks)
        norm = (len(toks) ** length_norm) or 1.0
        return sum(self._idf(t) * math.sqrt(tf.get(t, 0)) for t in set(q_toks)) / norm

    def search(self, query: str, k: int = 8) -> list[dict]:
        q = _tokens(query)
        if not q:
            return []
        results = []
        for d in self.docs:
            paper_score = self._score(
                q, d.get("title", "") + " " + d.get("abstract", ""))
            for s in d.get("sections", []):
                sec_score = self._score(q, " ".join(s["path"]) + " " + s["text"])
                if sec_score <= 0 and paper_score <= 0:
                    continue
                score = sec_score * (1.0 + 0.5 * paper_score)
                snippet = self._snippet(q, s["text"])
                results.append({
                    "arxiv_id": d["arxiv_id"], "title": d.get("title", ""),
                    "section": " > ".join(s["path"]),
                    "score": round(score, 4), "snippet": snippet,
                })
        results.sort(key=lambda r: -r["score"])
        return results[:k]

    @staticmethod
    def _snippet(q_toks: list[str], text: str, width: int = 320) -> str:
        low = text.lower()
        best = 0
        for t in q_toks:
            i = low.find(t)
            if i >= 0:
                best = i
                break
        start = max(0, best - width // 4)
        return ("…" if start else "") + text[start:start + width].strip() + "…"

    def get_section(self, arxiv_id: str, section_query: str) -> dict | None:
        for d in self.docs:
            if d["arxiv_id"] == arxiv_id:
                q = _tokens(section_query)
                scored = [(self._score(q, " ".join(s["path"])), s)
                          for s in d.get("sections", [])]
                scored.sort(key=lambda x: -x[0])
                if scored and scored[0][0] > 0:
                    return scored[0][1]
        return None


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("query", nargs="?")
    p.add_argument("--k", type=int, default=8)
    p.add_argument("--index-dir",
                   default=os.path.join(os.path.dirname(__file__), "index"))
    p.add_argument("--paper", help="arXiv id for --section retrieval")
    p.add_argument("--section", help="section-title query within --paper")
    a = p.parse_args(argv)
    c = Corpus(a.index_dir)
    if not c.docs:
        print(json.dumps({"error": "corpus index empty — run corpus/ingest.py "
                                    "on corpus/papers/seed_papers.txt first"}))
        return 1
    if a.paper and a.section:
        sec = c.get_section(a.paper, a.section)
        print(json.dumps(sec or {"error": "section not found"}, indent=1))
        return 0
    if not a.query:
        p.error("give a query, or --paper with --section")
    print(json.dumps(c.search(a.query, a.k), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
