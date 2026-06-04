"""Cognitive DAG agent — vector memory, MCP tools, iteration loop or DAG orchestrator."""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = ["CognitiveAgent", "DagAgent"]

if TYPE_CHECKING:
    from cognitive_dag.agent import CognitiveAgent
    from cognitive_dag.flow import DagAgent


def __getattr__(name: str):
    if name == "CognitiveAgent":
        from cognitive_dag.agent import CognitiveAgent

        return CognitiveAgent
    if name == "DagAgent":
        from cognitive_dag.flow import DagAgent

        return DagAgent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
