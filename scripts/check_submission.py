#!/usr/bin/env python3
"""Report submission readiness (static checks + optional log verification)."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs" / "eval"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runs.eval_suite import BASE_QUERIES, CUSTOM_QUERIES, score_log  # noqa: E402

# Max iterations per base log (README iteration budgets)
ITERATION_CEILINGS: dict[str, int] = {
    "base_a": 4,
    "base_b": 4,
    "base_c_run1": 4,
    "base_c_run2": 3,
    "base_d": 4,
    "base_e": 4,
    "base_f_run1": 4,
    "base_f_run2": 4,
    "base_g": 4,
    "base_h": 4,
}

EXPECTED_LOGS = (
    [f"base_{k}.log" for k, _, _ in BASE_QUERIES]
    + [f"custom_{k}_indexed.log" for k, _, _, _ in CUSTOM_QUERIES]
    + [f"custom_{k}_no_corpus.log" for k, _, _, _ in CUSTOM_QUERIES]
)


def _iterations(path: Path) -> int | None:
    if not path.is_file():
        return None
    hits = re.findall(r"─── iter (\d+)", path.read_text(encoding="utf-8", errors="replace"))
    return int(hits[-1]) if hits else None


def _has_answer(path: Path) -> bool:
    if not path.is_file():
        return False
    t = path.read_text(encoding="utf-8", errors="replace")
    return ">>> FINAL ANSWER <<<" in t or "[UI_RESULT_JSON]" in t


def main() -> int:
    failures: list[str] = []
    warnings: list[str] = []

    print("=== Submission check ===\n")

    # Static tests
    rc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_architecture.py", "tests/test_submission_spec.py", "-q"],
        cwd=ROOT,
    )
    if rc.returncode != 0:
        failures.append("Static spec tests failed (see pytest output above)")
    else:
        print("PASS  Static requirements (corpus, queries, architecture gate)\n")

    # Manifest
    manifest = ROOT / "corpus" / "MANIFEST.json"
    if manifest.is_file():
        data = json.loads(manifest.read_text(encoding="utf-8"))
        print(f"PASS  Corpus manifest: {data.get('item_count')} items\n")
    else:
        failures.append("Missing corpus/MANIFEST.json")

    # Trace logs
    print("=== Trace logs (logs/eval/) ===")
    missing_logs: list[str] = []
    for name in EXPECTED_LOGS:
        path = LOGS / name
        if not path.is_file():
            missing_logs.append(name)
            print(f"  MISSING  {name}")
            continue
        iters = _iterations(path)
        ok = _has_answer(path)
        ceiling = ITERATION_CEILINGS.get(name.replace(".log", ""))
        iter_ok = iters is not None and (ceiling is None or iters <= ceiling)
        status = "ok" if ok and iter_ok else "CHECK"
        iter_note = f"iters={iters}" if iters else "iters=?"
        if ceiling and iters and iters > ceiling:
            iter_note += f" (exceeds ceiling {ceiling})"
            status = "FAIL"
        print(f"  {status:5}  {name} — answer={'yes' if ok else 'no'}, {iter_note}")

    if missing_logs:
        warnings.append(
            f"{len(missing_logs)} log(s) missing — run: uv run python runs/eval_suite.py && uv run python scripts/extract_traces.py"
        )

    # Custom indexed vs no-corpus
    print("\n=== Custom RAG: indexed vs no-corpus ===")

    for key, kind, _query, terms in CUSTOM_QUERIES:
        idx = LOGS / f"custom_{key}_indexed.log"
        no = LOGS / f"custom_{key}_no_corpus.log"
        ok_idx, msg_idx = score_log(idx, terms) if idx.is_file() else (False, "missing")
        ok_no, msg_no = score_log(no, terms) if no.is_file() else (False, "missing")
        if ok_idx and not ok_no:
            print(f"  PASS  {key} ({kind}): retrieval required — indexed {msg_idx}, no-corpus weaker")
        elif not idx.is_file() or not no.is_file():
            print(f"  SKIP  {key}: logs missing")
            warnings.append(f"custom_{key}: missing indexed or no-corpus log")
        elif not ok_idx:
            print(f"  FAIL  {key}: indexed run did not match terms — {msg_idx}")
            failures.append(f"custom_{key}_indexed: {msg_idx}")
        elif ok_no:
            print(f"  FAIL  {key}: no-corpus still matched terms — retrieval not proven ({msg_no})")
            failures.append(f"custom_{key}_no_corpus: should fail without index")
        else:
            print(f"  PASS  {key} ({kind}): indexed {msg_idx}, no-corpus {msg_no}")

    traces_md = ROOT / "docs" / "SUBMISSION_TRACES.md"
    if traces_md.is_file():
        print(f"\nPASS  {traces_md.relative_to(ROOT)} present")
    else:
        warnings.append("docs/SUBMISSION_TRACES.md missing — run scripts/extract_traces.py after eval_suite")

    images = list((ROOT / "Images").glob("*"))
    if images:
        print(f"PASS  Images/ has {len(images)} file(s)")
    else:
        warnings.append("Images/ empty — add Web UI screenshots for queries A–D")

    print("\n=== Summary ===")
    for w in warnings:
        print(f"  WARN: {w}")
    for f in failures:
        print(f"  FAIL: {f}")

    if failures:
        return 1
    if warnings:
        print("\nStatic requirements satisfied. Generate traces before GitHub submission.")
        return 0
    print("\nAll checks passed including trace logs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
