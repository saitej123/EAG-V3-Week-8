#!/usr/bin/env python3
"""Extract submission trace summaries from logs/eval/ for README."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs" / "eval"
OUT_MD = ROOT / "docs" / "SUBMISSION_TRACES.md"
OUT_JSON = LOGS / "trace_summary.json"

FINAL_MARKER = ">>> FINAL ANSWER <<<"
UI_JSON_MARKER = "[UI_RESULT_JSON]"


def _extract_final_answer(text: str) -> str:
    if FINAL_MARKER in text:
        part = text.split(FINAL_MARKER, 1)[1].strip()
        return part[:1200] + ("…" if len(part) > 1200 else "")
    for line in text.splitlines():
        if UI_JSON_MARKER in line:
            try:
                payload = line.split(UI_JSON_MARKER, 1)[1].strip()
                data = json.loads(payload)
                ans = str(data.get("text", "")).strip()
                if ans:
                    return ans[:1200] + ("…" if len(ans) > 1200 else "")
            except json.JSONDecodeError:
                pass
    return ""


def _iteration_count(text: str) -> int | None:
    hits = re.findall(r"─── iter (\d+)", text)
    return int(hits[-1]) if hits else None


def _analyze_log(path: Path) -> dict:
    if not path.is_file():
        return {"file": path.name, "missing": True}
    text = path.read_text(encoding="utf-8", errors="replace")
    return {
        "file": path.name,
        "missing": False,
        "iterations": _iteration_count(text),
        "has_final_answer": FINAL_MARKER in text or UI_JSON_MARKER in text,
        "excerpt": _extract_final_answer(text),
        "bytes": path.stat().st_size,
    }


def build_summary() -> dict:
    base_files = sorted(LOGS.glob("base_*.log"))
    custom_indexed = sorted(LOGS.glob("custom_*_indexed.log"))
    custom_no = sorted(LOGS.glob("custom_*_no_corpus.log"))

    return {
        "base_queries": [_analyze_log(p) for p in base_files],
        "custom_indexed": [_analyze_log(p) for p in custom_indexed],
        "custom_no_corpus": [_analyze_log(p) for p in custom_no],
    }


def render_markdown(summary: dict) -> str:
    lines = [
        "# Submission traces",
        "",
        "Auto-generated from `logs/eval/`. Regenerate:",
        "",
        "```bash",
        "uv run python scripts/extract_traces.py",
        "```",
        "",
        "## Eight base queries (A–H)",
        "",
        "| Log | Iters | Final answer |",
        "|-----|-------|--------------|",
    ]
    for row in summary["base_queries"]:
        if row.get("missing"):
            lines.append(f"| `{row['file']}` | — | *missing* |")
            continue
        iters = row.get("iterations") or "?"
        ok = "yes" if row.get("has_final_answer") else "no"
        lines.append(f"| [`{row['file']}`](../logs/eval/{row['file']}) | {iters} | {ok} |")

    lines.extend(["", "## Five custom RAG queries — indexed vs no-corpus", ""])
    indexed = {r["file"]: r for r in summary["custom_indexed"]}
    no_corpus = {r["file"]: r for r in summary["custom_no_corpus"]}

    for idx_row in summary["custom_indexed"]:
        key = idx_row["file"].replace("_indexed.log", "")
        no_name = f"{key}_no_corpus.log"
        no_row = no_corpus.get(no_name, {"missing": True, "file": no_name})
        lines.append(f"### {key}")
        lines.append("")
        lines.append(f"- **Indexed:** [`{idx_row['file']}`](../logs/eval/{idx_row['file']}) — "
                     f"iters={idx_row.get('iterations', '?')}, answer={'yes' if idx_row.get('has_final_answer') else 'no'}")
        lines.append(f"- **No corpus:** [`{no_row.get('file', no_name)}`](../logs/eval/{no_row.get('file', no_name)}) — "
                     f"iters={no_row.get('iterations', '?')}, answer={'yes' if no_row.get('has_final_answer') else 'no'}")
        if idx_row.get("excerpt"):
            lines.append("")
            lines.append("<details><summary>Indexed excerpt</summary>")
            lines.append("")
            lines.append(idx_row["excerpt"])
            lines.append("")
            lines.append("</details>")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    if not LOGS.is_dir():
        print(f"No logs at {LOGS}. Run: uv run python runs/eval_suite.py", file=sys.stderr)
        return 1
    summary = build_summary()
    LOGS.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(render_markdown(summary), encoding="utf-8")
    print(f"Wrote {OUT_MD}")
    print(f"Wrote {OUT_JSON}")
    missing = sum(1 for section in summary.values() for row in section if row.get("missing"))
    if missing:
        print(f"Warning: {missing} log file(s) missing", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
