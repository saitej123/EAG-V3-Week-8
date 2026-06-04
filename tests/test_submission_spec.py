"""Static checks for RAG submission requirements (no live LLM calls)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# Verbatim eight base scenarios — canonical source: corpus/BASE_QUERIES.json
def _base_query_texts() -> list[tuple[str, str]]:
    from cognitive_dag.catalog import load_base_queries

    return [(k, q) for k, q, _clean in load_base_queries()]


BASE_QUERY_TEXTS: list[tuple[str, str]] = _base_query_texts()

CUSTOM_SEMANTIC_MIN = 2


def _load_eval_suite():
    import runs.eval_suite as es

    return es


def _load_query_spec() -> dict:
    return json.loads((ROOT / "corpus" / "QUERY_SPEC.json").read_text(encoding="utf-8"))


def test_research_corpus_fifty_papers():
    manifest = json.loads((ROOT / "corpus" / "MANIFEST.json").read_text(encoding="utf-8"))
    count = int(manifest.get("item_count", 0))
    assert count >= 50
    pdfs = list((ROOT / "sandbox" / "research_papers").glob("*.pdf"))
    mds = list((ROOT / "sandbox" / "research_papers").glob("*.md"))
    assert len(pdfs) >= 50
    assert len(mds) >= 50


def test_papers_include_skillopt_and_autoresearchclaw():
    corpus = ROOT / "sandbox" / "research_papers"
    assert any("23904" in p.name for p in corpus.glob("*.pdf"))
    assert any("20025" in p.name for p in corpus.glob("*.pdf"))


def test_base_queries_verbatim_in_eval_suite():
    es = _load_eval_suite()
    suite = {(k, q) for k, q, _clean in es.BASE_QUERIES}
    expected = set(BASE_QUERY_TEXTS)
    assert suite == expected, f"mismatch: extra={suite - expected} missing={expected - suite}"


def test_five_custom_rag_queries_with_semantic_recall():
    es = _load_eval_suite()
    assert len(es.CUSTOM_QUERIES) == 5
    semantic = [row for row in es.CUSTOM_QUERIES if row[1] == "semantic"]
    assert len(semantic) >= CUSTOM_SEMANTIC_MIN
    spec = _load_query_spec()
    assert int(spec.get("requirements", {}).get("semantic_recall_min", 2)) >= CUSTOM_SEMANTIC_MIN


def test_custom_queries_match_query_spec():
    es = _load_eval_suite()
    spec_queries = {q["id"]: q["query"] for q in _load_query_spec()["queries"]}
    for key, _kind, query, _terms in es.CUSTOM_QUERIES:
        assert spec_queries[key] == query


def test_custom_queries_have_no_corpus_runner():
    src = (ROOT / "runs" / "eval_suite.py").read_text(encoding="utf-8")
    assert "custom_" in src and "_no_corpus" in src
    assert "use_vlm=False" in src or "index_document_path" in src


def test_perception_tool_blindness():
    from tests.test_architecture import check_perception_tool_blindness

    assert check_perception_tool_blindness() == []


def test_memory_format_hits():
    assert "_format_hits" in (ROOT / "cognitive_dag" / "memory.py").read_text(encoding="utf-8")


def test_submission_trace_tooling_present():
    assert (ROOT / "scripts" / "extract_traces.py").is_file()
    assert (ROOT / "runs" / "eval_suite.py").is_file()
    assert (ROOT / "corpus" / "MANIFEST.json").is_file()
    assert (ROOT / "scripts" / "download_research_papers.py").is_file()
    assert (ROOT / "scripts" / "index_research_corpus.py").is_file()


def test_mcp_rag_tools_have_corpus_docstrings():
    import inspect

    from cognitive_dag import mcp_server

    for name in ("index_document", "index_directory", "search_knowledge", "read_file"):
        fn = getattr(mcp_server, name)
        doc = inspect.getdoc(fn) or ""
        assert len(doc) >= 80, f"{name} docstring too short for Decision"
        if name in ("index_document", "index_directory", "read_file"):
            assert ".md" in doc or "markdown" in doc.lower() or "pdf" in doc.lower(), f"{name} should mention document types"


def test_decision_system_references_mcp_docstrings():
    src = (ROOT / "cognitive_dag" / "decision.py").read_text(encoding="utf-8")
    assert "docstring" in src.lower()
    assert "index_document" in src
    assert "search_knowledge" in src


@pytest.mark.parametrize("key,query", BASE_QUERY_TEXTS)
def test_base_query_in_api(key: str, query: str):
    from cognitive_dag.catalog import base_queries_payload

    payload = base_queries_payload()
    flat = {(r["id"], r["query"]) for s in payload["scenarios"] for r in s["runs"]}
    assert (key, query) in flat


def test_base_query_scenario_count_eight():
    from cognitive_dag.catalog import base_queries_payload

    assert base_queries_payload()["scenario_count"] == 8


@pytest.mark.parametrize("row", json.loads((ROOT / "corpus" / "QUERY_SPEC.json").read_text())["queries"])
def test_custom_query_in_api(row: dict):
    from cognitive_dag.catalog import custom_queries_payload

    payload = custom_queries_payload()
    by_id = {q["id"]: q for q in payload["queries"]}
    assert row["id"] in by_id
    assert by_id[row["id"]]["query"] == row["query"]
