"""Custom corpus query spec (QUERY_SPEC.json)."""

from __future__ import annotations

from cognitive_dag.catalog import custom_queries_payload, load_custom_queries


def test_five_custom_queries():
    rows = load_custom_queries()
    assert len(rows) == 5


def test_semantic_recall_minimum():
    payload = custom_queries_payload()
    assert payload["requirements"]["semantic_count"] >= 2
    assert payload["requirements"]["semantic_recall_min"] >= 2


def test_custom_queries_payload_fields():
    payload = custom_queries_payload()
    for q in payload["queries"]:
        assert q["query"]
        assert q["answer_terms"]
        assert q["kind"] in {"semantic", "keyword", "cross-doc"}
        assert q["requires_index"] is True
