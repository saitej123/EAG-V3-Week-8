#!/usr/bin/env python3
"""Bulk-index sandbox/research_papers into FAISS (text sidecars by default for speed)."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description="Index 50-paper research corpus")
    parser.add_argument("--keep-state", action="store_true")
    parser.add_argument("--vlm", action="store_true", help="Use VLM pipeline (slow; calls Gemini per page)")
    parser.add_argument("--md-only", action="store_true", default=True, help="Index .md sidecars only (default)")
    parser.add_argument("--all", dest="md_only", action="store_false", help="Index all supported files including PDFs")
    args = parser.parse_args()

    if not args.keep_state:
        state = ROOT / "state"
        if state.exists():
            shutil.rmtree(state)
            print("Cleaned state/")

    from cognitive_dag.indexing import index_document_path, index_directory

    corpus = ROOT / "sandbox" / "research_papers"
    if not corpus.is_dir():
        print("Missing sandbox/research_papers — run: uv run python scripts/download_research_papers.py")
        sys.exit(1)

    use_vlm = True if args.vlm else (False if args.md_only else None)
    if args.md_only and not args.vlm:
        files = sorted(corpus.glob("*.md"))
        total_chunks = 0
        per: list[dict] = []
        for f in files:
            rel = f"research_papers/{f.name}"
            r = index_document_path(rel, use_vlm=False)
            n = int(r.get("chunks_indexed", 0))
            total_chunks += n
            per.append({"path": rel, **r})
        result = {"directory": "research_papers", "files_indexed": len(per), "chunks_indexed": total_chunks, "files": per}
    else:
        result = index_directory("research_papers")

    out = ROOT / "logs" / "eval" / "corpus_index_result.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
