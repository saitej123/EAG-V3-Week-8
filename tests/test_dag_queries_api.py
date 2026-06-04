"""DAG demo query corpus and /api/queries/dag contract tests."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from cognitive_dag.catalog import (
    assignment_payload,
    get_dag_query,
    load_assignment_queries,
    validate_assignment_corpus,
)

EXPECTED_IDS = ["hello", "A", "I", "J", "K", "P", "C_pass", "C_fail", "M", "CALC"]


def test_validate_assignment_corpus_clean():
    assert validate_assignment_corpus() == []


def test_every_demo_query_has_query_text_and_bounds():
    for row in load_assignment_queries():
        assert str(row["query"]).strip()
        assert float(row["wall_clock_sec"]) > 0
        assert row.get("title")
        assert int(row["part"]) in {1, 2, 3, 4, 5}


def test_design_queries_reference_real_ids():
    payload = assignment_payload()
    ids = {q["id"] for q in payload["queries"]}
    for dq in payload["design_queries"]:
        if dq["kind"] == "parallel":
            assert dq["query_id"] in ids
        if dq["kind"] == "critic":
            assert set(dq["query_ids"]).issubset(ids)


def test_groups_cover_all_queries():
    payload = assignment_payload()
    grouped = [qid for g in payload["groups"] for qid in g["query_ids"]]
    assert sorted(grouped) == sorted(EXPECTED_IDS)


def test_submission_outline_order_matches_checklist():
    payload = assignment_payload()
    outline = payload["outline"]
    assert len(outline) == 5
    assert outline[0]["part"] == 1
    assert outline[0]["query_ids"] == ["hello", "A", "I", "J", "K"]
    assert outline[1]["part"] == 2
    assert outline[1]["query_ids"] == ["P"]
    assert outline[1]["design_id"] == "parallel_design"
    assert outline[2]["query_ids"] == ["C_pass", "C_fail"]
    assert outline[2]["design_id"] == "critic_design"
    assert outline[3]["query_ids"] == ["M"]
    assert outline[4]["query_ids"] == ["CALC"]


@pytest.mark.parametrize("qid", EXPECTED_IDS)
def test_get_dag_query_lookup(qid: str):
    row = get_dag_query(qid)
    assert row is not None
    assert row["id"] == qid


def test_api_dag_queries_success():
    from app import app

    client = TestClient(app)
    res = client.get("/api/queries/dag")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "success"
    assert body["query_count"] == 10
    assert len(body["queries"]) == 10
    assert len(body["design_queries"]) == 2
    assert len(body["groups"]) == 5
    assert len(body["outline"]) == 5
    assert body["outline"][0]["query_ids"][0] == "hello"

    ids = [q["id"] for q in body["queries"]]
    assert sorted(ids) == sorted(EXPECTED_IDS)

    for q in body["queries"]:
        assert q["query"].strip()
        assert "wall_clock_sec" in q


def test_api_dag_queries_render_fields_for_ui():
    from app import app

    client = TestClient(app)
    body = client.get("/api/queries/dag").json()
    by_id = {q["id"]: q for q in body["queries"]}

    assert by_id["P"]["parallel_researchers"] == 3
    assert by_id["C_pass"]["critic_expect"] == "pass"
    assert by_id["C_fail"]["critic_expect"] == "fail_then_recovery"
    assert "validate_json_keys" in by_id["C_pass"]["query"]
    assert by_id["M"]["ui_hint"]
    assert by_id["CALC"]["ui_hint"]
    assert re.search(r"150769", by_id["M"]["ui_hint"])


def test_api_dag_queries_html_page_includes_loader():
    from app import app

    client = TestClient(app)
    html = client.get("/").text
    assert "loadDagQueries" in html
    assert "dagQueriesScroll" in html
    assert "/api/queries/dag" in html
