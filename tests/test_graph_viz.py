"""DAG graph visualization payload tests."""

from __future__ import annotations

import json
import os
import time

import networkx as nx

from cognitive_dag.dag_schemas import NodeSpec, NodeState, NodeStatus, PlannerOutput
from cognitive_dag.flow import Graph
from cognitive_dag.graph_viz import graph_viz_payload, list_dag_sessions
from cognitive_dag.persistence import SessionStore
from cognitive_dag.skills import SkillRegistry


def test_graph_viz_payload_hello_shape(tmp_path, monkeypatch):
    from cognitive_dag import persistence as pers_mod

    monkeypatch.setattr(pers_mod, "SESSIONS_DIR", tmp_path / "sessions")
    sid = "dag_test_viz"
    store = SessionStore(sid)
    g = Graph(SkillRegistry())
    plan = PlannerOutput(
        rationale="hi",
        nodes=[NodeSpec(skill="formatter", inputs=["USER_QUERY"], metadata={"label": "out"})],
    )
    p = g.add_node_from_spec(NodeSpec(skill="planner", inputs=["USER_QUERY"], metadata={"label": "planner"}), node_id="n:1")
    g.extend_from(p, plan)
    store.save_query("Say hello.")
    store.save_graph(g.dg)
    store.save_node_state(
        NodeState(node_id="n:1", skill="planner", status=NodeStatus.complete, output="{}")
    )

    store.save_memory_hits(
        [
            {
                "descriptor": "faiss:chunk",
                "source": "papers/foo.md",
                "value": {"chunk": "Attention is all you need preview text."},
            }
        ]
    )

    payload = graph_viz_payload(sid)
    assert payload["node_count"] == 2
    assert payload["edge_count"] == 1
    assert len(payload["nodes"]) == 2
    assert any(n["skill"] == "formatter" for n in payload["nodes"])
    assert payload["stats"]["status_counts"]["complete"] == 1
    assert len(payload["memory_hits"]) == 1
    assert "Attention" in payload["memory_hits"][0]["preview"]
    assert "resumable" in payload
    assert payload["nodes"][0].get("result_preview") is not None
    assert all(n.get("position") for n in payload["nodes"])
    coords = {(n["position"]["x"], n["position"]["y"]) for n in payload["nodes"]}
    assert len(coords) == len(payload["nodes"])
    assert payload["nodes"][0]["status_label"] == "done"


def test_graph_viz_shows_running_from_disk(tmp_path, monkeypatch):
    from cognitive_dag import persistence as pers_mod

    monkeypatch.setattr(pers_mod, "SESSIONS_DIR", tmp_path / "sessions")
    sid = "dag_running_viz"
    store = SessionStore(sid)
    g = Graph(SkillRegistry())
    p = g.add_node_from_spec(NodeSpec(skill="planner", inputs=["USER_QUERY"], metadata={"label": "planner"}), node_id="n:1")
    f = g.add_node_from_spec(NodeSpec(skill="formatter", inputs=["n:1"], metadata={"label": "out"}), node_id="n:2")
    g.dg.add_edge(p, f)
    store.save_query("test")
    store.save_graph(g.dg)
    store.save_node_state(NodeState(node_id="n:1", skill="planner", status=NodeStatus.complete, output="{}"))
    store.save_node_state(NodeState(node_id="n:2", skill="formatter", status=NodeStatus.running, output=None))

    payload = graph_viz_payload(sid)
    fmt = next(n for n in payload["nodes"] if n["id"] == "n:2")
    assert fmt["status"] == "running"
    assert fmt["status_label"] == "run"
    assert payload["stats"]["status_counts"]["running"] == 1


def test_list_dag_sessions_orders_newest(tmp_path, monkeypatch):
    from cognitive_dag import persistence as pers_mod

    monkeypatch.setattr(pers_mod, "SESSIONS_DIR", tmp_path / "sessions")
    base = time.time()
    for i, sid in enumerate(("dag_old", "dag_new")):
        store = SessionStore(sid)
        store.ensure_dirs()
        store.save_query(sid)
        store.graph_path.write_text(
            json.dumps(nx.node_link_data(nx.DiGraph()), indent=2),
            encoding="utf-8",
        )
        os.utime(store.graph_path, (base + i, base + i))
    rows = list_dag_sessions()
    assert rows[0]["session_id"] == "dag_new"
