import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "corpus"))

from ingest import latex_to_text, split_sections  # noqa: E402
from search import Corpus  # noqa: E402

TEX = r"""
\documentclass{article}
\begin{document}
\title{Toy search}
Intro text before sections. % a comment
\section{Introduction}
We search for the rare decay of the Higgs boson to a Z boson and a J/psi meson
in four-lepton final states.
\section{Event selection}
Muons are required to have $p_T > 3$ GeV. The J/psi candidate mass window is
chosen from a significance scan. % tuned
\subsection{Trigger}
Single-muon triggers are used.
\section{Systematic uncertainties}
Polarization of the J/psi dominates the signal-efficiency uncertainty.
\end{document}
"""


def test_split_sections_tree():
    secs = split_sections(TEX)
    paths = [" > ".join(s["path"]) for s in secs]
    assert "Introduction" in paths
    assert "Event selection > Trigger" in paths
    trig = secs[paths.index("Event selection > Trigger")]
    assert trig["level"] == 2
    assert "Single-muon" in trig["text"]
    # comments stripped
    assert not any("tuned" in s["text"] for s in secs)


def test_latex_fallback_strips_markup():
    txt = latex_to_text(r"We require \textbf{two} muons with $p_T>3$ GeV \cite{ref1}.")
    assert "two muons" in txt
    assert "\\textbf" not in txt and "$" not in txt


def _write_index(tmp_path):
    docs = [
        {"arxiv_id": "0000.00001", "title": "Search for H to Z Jpsi",
         "abstract": "A rare Higgs decay search in four lepton final states.",
         "sections": [
             {"path": ["Event selection"], "level": 1,
              "text": "The J/psi mass window and muon pT cuts are optimized "
                      "with a Punzi significance scan."},
             {"path": ["Systematic uncertainties"], "level": 1,
              "text": "J/psi polarization dominates the efficiency uncertainty."},
         ]},
        {"arxiv_id": "0000.00002", "title": "Measurement of top quark mass",
         "abstract": "Top physics.",
         "sections": [{"path": ["Introduction"], "level": 1,
                       "text": "Top quark pairs are selected with b-tagging."}]},
    ]
    idx = tmp_path / "index"
    idx.mkdir()
    for d in docs:
        (idx / (d["arxiv_id"] + ".json")).write_text(json.dumps(d))
    return str(idx)


def test_search_ranks_relevant_section_first(tmp_path):
    c = Corpus(_write_index(tmp_path))
    hits = c.search("J/psi polarization systematic uncertainty", k=3)
    assert hits
    assert hits[0]["arxiv_id"] == "0000.00001"
    assert "Systematic" in hits[0]["section"]
    # off-topic paper must not outrank
    assert all(h["arxiv_id"] != "0000.00002" for h in hits[:1])


def test_get_section(tmp_path):
    c = Corpus(_write_index(tmp_path))
    sec = c.get_section("0000.00001", "systematic uncertainties")
    assert sec and "polarization" in sec["text"]


def test_empty_query(tmp_path):
    c = Corpus(_write_index(tmp_path))
    assert c.search("") == []
