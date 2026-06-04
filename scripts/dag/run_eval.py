#!/usr/bin/env python3
"""Run built-in DAG demo queries; capture logs and wall-clock bounds."""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from cognitive_dag.catalog import load_assignment_queries
from cognitive_dag.flow import Executor
from cognitive_dag.persistence import SessionLoadError

LOG_DIR = ROOT / "logs" / "dag"
SESSION_ROOT = ROOT / "state" / "sessions"


def _all_queries() -> list[dict]:
    return load_assignment_queries()


def _session_id(qid: str, fresh: bool) -> str:
    if fresh:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        return f"dag_{qid}_{ts}"
    return f"dag_{qid}"


async def _run_query(row: dict, *, fresh: bool, resume: bool) -> dict:
    qid = str(row["id"])
    query = str(row["query"])
    bound = float(row.get("wall_clock_sec") or 300)
    sid = str(row.get("session_override") or _session_id(qid, fresh))

    if fresh and not resume:
        session_dir = SESSION_ROOT / sid
        if session_dir.exists():
            shutil.rmtree(session_dir)

    log_path = LOG_DIR / f"{qid}.log"
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    t0 = time.monotonic()
    status = "ok"
    answer = ""
    error = ""

    try:
        ex = Executor()
        try:
            if resume:
                answer = await ex.resume(sid)
            else:
                answer = await ex.run(query, session_id=sid)
        finally:
            await ex.aclose()
    except SessionLoadError as e:
        status = "session_error"
        error = str(e)
    except RuntimeError as e:
        status = "runtime_error"
        error = str(e)
    except Exception as e:
        status = "error"
        error = f"{type(e).__name__}: {e}"

    wall = time.monotonic() - t0
    within_bound = wall <= bound if status == "ok" else False

    record = {
        "id": qid,
        "part": row.get("part"),
        "title": row.get("title"),
        "query": query,
        "session_id": sid,
        "status": status,
        "wall_clock_sec": round(wall, 3),
        "wall_clock_bound_sec": bound,
        "within_bound": within_bound,
        "answer_preview": answer[:500] if answer else "",
        "error": error,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }

    log_body = (
        f"# DAG query {qid} — {row.get('title', '')}\n"
        f"status={status} wall={wall:.2f}s bound={bound}s within={within_bound}\n"
        f"session=state/sessions/{sid}/\n\n"
        f"QUERY (verbatim):\n{query}\n\n"
    )
    if error:
        log_body += f"ERROR:\n{error}\n\n"
    if answer:
        log_body += f"ANSWER:\n{answer}\n"
    log_path.write_text(log_body, encoding="utf-8")
    record["log_path"] = str(log_path.relative_to(ROOT))

    summary_path = SESSION_ROOT / sid / "eval_summary.json"
    if summary_path.parent.exists():
        summary_path.write_text(json.dumps(record, indent=2), encoding="utf-8")

    return record


def main() -> int:
    all_rows = _all_queries()
    ids = [str(r["id"]) for r in all_rows]
    parser = argparse.ArgumentParser(description="Run DAG demo query eval suite")
    parser.add_argument(
        "--ids",
        nargs="*",
        default=ids,
        help=f"Query ids (default: all). Choices: {', '.join(ids)}",
    )
    parser.add_argument("--fresh", action="store_true", help="Use timestamped session ids")
    parser.add_argument("--resume", action="store_true", help="Resume existing session instead of new run")
    parser.add_argument("--json", action="store_true", help="Print JSON summary to stdout")
    args = parser.parse_args()

    selected = [r for r in all_rows if str(r["id"]) in args.ids]
    if not selected:
        print("No matching query ids.", file=sys.stderr)
        return 1

    results: list[dict] = []
    for row in selected:
        print(f"[eval] running {row['id']} …", file=sys.stderr, flush=True)
        rec = asyncio.run(_run_query(row, fresh=args.fresh, resume=args.resume))
        results.append(rec)
        mark = "PASS" if rec["status"] == "ok" and rec["within_bound"] else "FAIL"
        print(
            f"[eval] {row['id']}: {mark} status={rec['status']} "
            f"wall={rec['wall_clock_sec']}s bound={rec['wall_clock_bound_sec']}s",
            file=sys.stderr,
        )

    summary = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "results": results,
        "passed": sum(1 for r in results if r["status"] == "ok" and r["within_bound"]),
        "total": len(results),
    }
    summary_path = LOG_DIR / "summary.json"
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"\nSummary: {summary['passed']}/{summary['total']} within bounds")
        print(f"Logs: logs/dag/  summary: logs/dag/summary.json")

    return 0 if summary["passed"] == summary["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
