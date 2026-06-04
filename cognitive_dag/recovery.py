"""Failure classification and recovery policy for the DAG orchestrator."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, TYPE_CHECKING

if TYPE_CHECKING:
    from .dag_schemas import AgentResult, NodeSpec, NodeState
    from .flow import Graph

FailureKind = Literal["transient", "validation_error", "upstream_failure"]
RecoveryAction = Literal["skip", "replan"]

_TRANSIENT_KEYWORDS = (
    "503",
    "502",
    "504",
    "timeout",
    "connection",
    "bad gateway",
    "gateway timeout",
    "ConnectionError",
    "HTTPStatusError",
    "service unavailable",
)

_VALIDATION_KEYWORDS = (
    "malformed",
    "ValidationError",
    "validation error",
)


def classify_failure(error_text: str) -> FailureKind:
    """Map error text to recovery policy (keyword matcher — pinned by unit tests)."""
    text = error_text or ""
    lower = text.lower()
    for kw in _TRANSIENT_KEYWORDS:
        if kw in text or kw.lower() in lower:
            return "transient"
    for kw in _VALIDATION_KEYWORDS:
        if kw in text or kw.lower() in lower:
            return "validation_error"
    return "upstream_failure"


@dataclass
class RecoveryDecision:
    action: RecoveryAction
    reason: str
    note: str = ""
    failure_report: dict[str, Any] = field(default_factory=dict)


def plan_recovery(
    *,
    failed_skill: str,
    error_text: str,
    failed_node_id: str,
) -> RecoveryDecision:
    """Policy gate for node failure — transient/validation skip; upstream replans."""
    kind = classify_failure(error_text)
    if kind == "transient":
        return RecoveryDecision(action="skip", reason=kind, note=error_text)
    if kind == "validation_error":
        return RecoveryDecision(action="skip", reason=kind, note=error_text)
    if failed_skill == "planner":
        return RecoveryDecision(
            action="skip",
            reason="planner_failure",
            note=error_text,
            failure_report={"node_id": failed_node_id, "skill": failed_skill, "error": error_text},
        )
    return RecoveryDecision(
        action="replan",
        reason=kind,
        note=error_text,
        failure_report={"node_id": failed_node_id, "skill": failed_skill, "error": error_text},
    )


def handle_critic_verdict(
    critic_id: str,
    raw_output: str,
    graph: Graph,
    states: dict[str, NodeState],
    recovered_branches: dict[str, bool],
    critic_fail_cap_hit: list[str],
    *,
    fail_cap: int = 1,
) -> bool:
    """Process critic fail/pass. Returns True when fail was handled (no graph extend)."""
    from .dag_schemas import CriticVerdict, NodeSpec, NodeState as NS, NodeStatus
    from .llm_retry import loads_json_lenient

    data = loads_json_lenient(raw_output)
    verdict = CriticVerdict.model_validate(data)
    if verdict.verdict == "pass":
        return False

    meta = graph.dg.nodes[critic_id].get("metadata") or {}
    target = str(meta.get("target") or meta.get("child") or "")
    succs = list(graph.dg.successors(critic_id))
    if not target and succs:
        target = succs[0]

    for sid in succs:
        if sid in states:
            states[sid].status = NodeStatus.skipped

    count = graph.critic_fail_counts.get(target, 0) + 1
    graph.critic_fail_counts[target] = count
    if count > fail_cap:
        critic_fail_cap_hit.append(target or critic_id)
        recovered_branches[target] = True
        return True

    c_label = graph.dg.nodes[critic_id].get("label", critic_id)
    recovery = NodeSpec(
        skill="planner",
        inputs=["USER_QUERY", f"n:{c_label}"],
        metadata={
            "label": f"recovery_{count}",
            "recovery": True,
            "question": verdict.rationale,
            "failure_report": {"critic_id": critic_id, "target": target, "rationale": verdict.rationale},
        },
    )
    rid = graph.add_node_from_spec(recovery)
    graph.dg.add_edge(critic_id, rid)
    states[rid] = NS(
        node_id=rid,
        skill="planner",
        inputs=list(recovery.inputs),
        metadata=dict(recovery.metadata),
    )
    recovered_branches[target] = True
    return True
