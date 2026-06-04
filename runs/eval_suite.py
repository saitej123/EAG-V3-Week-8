#!/usr/bin/env python3
"""Run base A–H and custom R1–R5 eval queries; write logs/eval/*.log."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LOGS = ROOT / "logs" / "eval"
FINAL_MARKER = ">>> FINAL ANSWER <<<"
UI_JSON_MARKER = "[UI_RESULT_JSON]"

from cognitive_dag.catalog import load_base_queries, load_custom_queries  # noqa: E402

BASE_QUERIES: list[tuple[str, str, bool]] = load_base_queries()
CUSTOM_QUERIES: list[tuple[str, str, str, list[str]]] = load_custom_queries()


def _extract_answer(text: str) -> str:
    if FINAL_MARKER in text:
        part = text.split(FINAL_MARKER, 1)[1].strip()
        return part
    for line in text.splitlines():
        if UI_JSON_MARKER in line:
            try:
                payload = line.split(UI_JSON_MARKER, 1)[1].strip()
                data = json.loads(payload)
                return str(data.get("text", "")).strip()
            except json.JSONDecodeError:
                continue
    return ""


def score_log(path: Path, terms: list[str]) -> tuple[bool, str]:
    """Return (ok, message) — ok when enough answer_terms appear in the final answer."""
    if not path.is_file():
        return False, "missing log"
    text = path.read_text(encoding="utf-8", errors="replace")
    answer = _extract_answer(text)
    if not answer.strip():
        return False, "no final answer"
    low = answer.lower()
    matched = [t for t in terms if t.lower() in low]
    need = min(len(terms), max(2, (len(terms) + 1) // 2))
    if len(matched) >= need:
        return True, f"matched {matched}"
    return False, f"matched {matched} (need {need} of {terms})"


def _clean_state() -> None:
    state = ROOT / "state"
    if state.exists():
        shutil.rmtree(state)


def _index_research_papers() -> None:
    """Index markdown sidecars from sandbox/research_papers (fast path, no VLM)."""
    from cognitive_dag.indexing import index_document_path

    corpus = ROOT / "sandbox" / "research_papers"
    if not corpus.is_dir():
        raise FileNotFoundError(
            "Missing sandbox/research_papers — run: uv run python scripts/download_research_papers.py"
        )
    for md in sorted(corpus.glob("*.md")):
        rel = f"research_papers/{md.name}"
        index_document_path(rel, use_vlm=False)


async def _run_agent(query: str, log_path: Path) -> None:
    from dotenv import load_dotenv
    from loguru import logger

    load_dotenv(ROOT / ".env")
    os.environ["AGENT_MODE"] = "loop"

    LOGS.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger.remove()
    logger.add(sys.stderr, format="{time:HH:mm:ss} | {level: <8} | {message}", level="INFO")
    sink_id = logger.add(
        str(log_path),
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
        level="INFO",
        mode="w",
    )
    try:
        from cognitive_dag.agent import CognitiveAgent

        await CognitiveAgent().run(query)
    finally:
        logger.remove(sink_id)


async def run_base(key: str, query: str, clean: bool) -> None:
    if clean:
        _clean_state()
    print(f"[eval] base_{key} …", flush=True)
    await _run_agent(query, LOGS / f"base_{key}.log")


async def run_custom_indexed(key: str, query: str) -> None:
    _clean_state()
    _index_research_papers()
    print(f"[eval] custom_{key}_indexed …", flush=True)
    await _run_agent(query, LOGS / f"custom_{key}_indexed.log")


async def run_custom_no_corpus(key: str, query: str) -> None:
    _clean_state()
    print(f"[eval] custom_{key}_no_corpus …", flush=True)
    await _run_agent(query, LOGS / f"custom_{key}_no_corpus.log")


async def main_async(args: argparse.Namespace) -> int:
    run_base_queries = not args.custom_only and not args.skip_base
    run_custom = not args.base_only and not args.skip_custom

    if run_base_queries:
        for key, query, clean in BASE_QUERIES:
            await run_base(key, query, clean)

    if run_custom:
        for key, _kind, query, _terms in CUSTOM_QUERIES:
            await run_custom_indexed(key, query)
            await run_custom_no_corpus(key, query)

    print(f"\nLogs written to {LOGS.relative_to(ROOT)}/")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run RAG eval suite (base A–H + custom R1–R5)")
    parser.add_argument("--base-only", action="store_true", help="Run only base queries")
    parser.add_argument("--custom-only", action="store_true", help="Run only custom RAG queries")
    parser.add_argument("--skip-base", action="store_true", help="Skip base queries")
    parser.add_argument("--skip-custom", action="store_true", help="Skip custom queries")
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
