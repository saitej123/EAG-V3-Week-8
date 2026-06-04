"""Serialize persisted DAG sessions for the Web UI (vis-network)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import networkx as nx

from .dag_schemas import AgentResult, NodeStatus
from . import persistence
from .persistence import SessionLoadError, SessionStore

_SKILL_COLORS: dict[str, str] = {
    "planner": "#18181b",
    "researcher": "#2563eb",
    "retriever": "#0891b2",
    "distiller": "#7c3aed",
    "summariser": "#6366f1",
    "critic": "#d97706",
    "coder": "#059669",
    "sandbox_executor": "#0d9488",
    "formatter": "#52525b",
    "calculator": "#db2777",
    "browser": "#0284c7",
}

_STATUS_COLORS: dict[str, str] = {
    "pending": "#e4e4e7",
    "running": "#fef3c7",
    "complete": "#dcfce7",
    "failed": "#fee2e2",
    "skipped": "#f4f4f5",
}

_STATUS_BORDERS: dict[str, str] = {
    "pending": "#a1a1aa",
    "running": "#f59e0b",
    "complete": "#22c55e",
    "failed": "#ef4444",
    "skipped": "#d4d4d8",
}


def _node_status(skill: str, graph: nx.DiGraph, nid: str, states: dict[str, Any]) -> str:
    if nid in states:
        st = states[nid]
        raw = st.status.value if hasattr(st.status, "value") else str(st.status)
        return raw
    result = graph.nodes[nid].get("result")
    if isinstance(result, AgentResult):
        return result.status.value
    if isinstance(result, dict):
        return str(result.get("status") or "pending")
    return "pending"


def _memory_hits_for_ui(store: SessionStore) -> list[dict[str, str]]:
    """Compact memory hits for the graph sidebar."""
    rows: list[dict[str, str]] = []
    for raw in store.load_memory_hits()[:8]:
        if not isinstance(raw, dict):
            continue
        desc = str(raw.get("descriptor") or "memory")
        val = raw.get("value") if isinstance(raw.get("value"), dict) else {}
        chunk = val.get("chunk") or val.get("raw") or val.get("text") or ""
        preview = str(chunk).strip()[:200]
        if len(str(chunk).strip()) > 200:
            preview += "…"
        source = str(raw.get("source") or val.get("path") or "")
        rows.append({"descriptor": desc, "source": source, "preview": preview})
    return rows


def _session_stats(states: dict[str, Any]) -> dict[str, Any]:
    counts = {"complete": 0, "running": 0, "pending": 0, "failed": 0, "skipped": 0}
    wall = 0.0
    for st in states.values():
        raw = st.status.value if hasattr(st.status, "value") else str(st.status)
        if raw in counts:
            counts[raw] += 1
        if getattr(st, "elapsed_s", None):
            wall = max(wall, float(st.elapsed_s))
    return {"status_counts": counts, "max_node_elapsed_s": round(wall, 2)}


def _result_preview(graph: nx.DiGraph, nid: str, states: dict[str, Any]) -> str:
    if nid in states:
        st = states[nid]
        if st.error:
            return f"Error: {st.error[:200]}"
        if st.output:
            text = str(st.output)
            return text[:280] + ("…" if len(text) > 280 else "")
    result = graph.nodes[nid].get("result")
    if isinstance(result, AgentResult):
        if result.error:
            return f"Error: {result.error[:200]}"
        if result.output:
            text = str(result.output)
            return text[:280] + ("…" if len(text) > 280 else "")
    return ""


def _graph_node_count(graph_path: Path) -> int:
    try:
        data = json.loads(graph_path.read_text(encoding="utf-8"))
        return len(data.get("nodes", []))
    except (json.JSONDecodeError, OSError):
        return 0


def list_dag_sessions(*, limit: int = 30) -> list[dict[str, Any]]:
    """Recent session folders that contain graph.json, newest first."""
    sessions_dir = persistence.SESSIONS_DIR
    if not sessions_dir.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in sessions_dir.iterdir():
        if not path.is_dir():
            continue
        graph_path = path / "graph.json"
        if not graph_path.is_file():
            continue
        mtime = graph_path.stat().st_mtime
        query = ""
        qpath = path / "query.txt"
        if qpath.is_file():
            query = qpath.read_text(encoding="utf-8", errors="replace").strip()
            if len(query) > 120:
                query = query[:117] + "…"
        rows.append(
            {
                "session_id": path.name,
                "modified_utc": datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat(),
                "query_preview": query,
                "node_count": _graph_node_count(graph_path),
            }
        )
    rows.sort(key=lambda r: r["modified_utc"], reverse=True)
    return rows[:limit]


def latest_dag_session_id() -> str | None:
    sessions = list_dag_sessions(limit=1)
    return sessions[0]["session_id"] if sessions else None


def graph_viz_payload(session_id: str) -> dict[str, Any]:
    """Build vis-network nodes/edges from a persisted session."""
    store = SessionStore(session_id)
    if not store.exists():
        raise SessionLoadError(f"No graph for session {session_id}")
    graph = store.load_graph()
    try:
        states = store.load_all_node_states()
    except SessionLoadError:
        states = {}

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    for nid, data in graph.nodes(data=True):
        skill = str(data.get("skill") or "?")
        label = str(data.get("label") or nid)
        status = _node_status(skill, graph, nid, states)
        timing = ""
        if nid in states and getattr(states[nid], "elapsed_s", None) is not None:
            timing = f"<br/>Elapsed: {states[nid].elapsed_s:.2f}s"
        title = (
            f"<b>{escape_html(skill)}</b> · {escape_html(nid)}<br/>"
            f"Status: {escape_html(status)}{timing}<br/>"
            f"{escape_html(_result_preview(graph, nid, states))}"
        )
        node_elapsed = None
        if nid in states and states[nid].elapsed_s is not None:
            node_elapsed = round(float(states[nid].elapsed_s), 2)
        nodes.append(
            {
                "id": nid,
                "label": f"{skill}\n{label}",
                "title": title,
                "elapsed_s": node_elapsed,
                "color": {
                    "background": _STATUS_COLORS.get(status, "#f4f4f5"),
                    "border": _STATUS_BORDERS.get(status, "#a1a1aa"),
                    "highlight": {"background": "#e0e7ff", "border": "#4f46e5"},
                },
                "font": {"color": "#18181b", "size": 15, "face": "Inter, system-ui, sans-serif", "multi": True},
                "borderWidth": 2 if status == "running" else 1,
                "shape": "box",
                "margin": 12,
                "widthConstraint": {"minimum": 110, "maximum": 260},
                "skill": skill,
                "status": status,
            }
        )

    for src, dst in graph.edges():
        edges.append(
            {
                "from": src,
                "to": dst,
                "arrows": "to",
                "color": {"color": "#a1a1aa", "highlight": "#6366f1"},
                "smooth": {"type": "cubicBezier", "roundness": 0.2},
            }
        )

    query = ""
    if store.query_path.is_file():
        query = store.query_path.read_text(encoding="utf-8", errors="replace").strip()

    return {
        "session_id": session_id,
        "query": query,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": nodes,
        "edges": edges,
        "layout_hint": "hierarchical",
        "memory_hits": _memory_hits_for_ui(store),
        "stats": _session_stats(states),
    }


def escape_html(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
