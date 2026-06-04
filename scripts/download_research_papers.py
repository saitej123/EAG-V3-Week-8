#!/usr/bin/env python3
"""Download recent arXiv PDFs + markdown sidecars for the 50-paper research corpus."""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "sandbox" / "research_papers"
PINNED_PDF_DIR = ROOT / "sandbox" / "papers"
MANIFEST_PATH = ROOT / "corpus" / "MANIFEST.json"
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


def _fetch_arxiv_entries(*, max_results: int = 50, query: str | None = None) -> list[dict]:
    q = query or "cat:cs.LG OR cat:cs.CL OR cat:cs.AI"
    params = urllib.parse.urlencode(
        {
            "search_query": q,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": str(max_results),
        }
    )
    url = f"https://export.arxiv.org/api/query?{params}"
    with urllib.request.urlopen(url, timeout=120) as resp:
        raw = resp.read()
    root = ET.fromstring(raw)
    entries: list[dict] = []
    for entry in root.findall("atom:entry", ATOM_NS):
        arxiv_id = (entry.find("atom:id", ATOM_NS).text or "").split("/abs/")[-1]
        arxiv_id = arxiv_id.replace("v1", "").split("v")[0] if arxiv_id else ""
        title = " ".join((entry.find("atom:title", ATOM_NS).text or "").split())
        abstract = " ".join((entry.find("atom:summary", ATOM_NS).text or "").split())
        authors = [
            (a.find("atom:name", ATOM_NS).text or "").strip()
            for a in entry.findall("atom:author", ATOM_NS)
        ]
        published = (entry.find("atom:published", ATOM_NS).text or "")[:10]
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        entries.append(
            {
                "arxiv_id": arxiv_id,
                "title": title,
                "abstract": abstract,
                "authors": authors,
                "published": published,
                "pdf_url": pdf_url,
            }
        )
    return entries


def _safe_stem(arxiv_id: str) -> str:
    return re.sub(r"[^\w.\-]+", "_", arxiv_id)


def _download_pdf(url: str, dest: Path, *, retries: int = 3) -> bool:
    if dest.is_file() and dest.stat().st_size > 10_000:
        return True
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "cognitive-dag-agent/1.0"})
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = resp.read()
            if len(data) < 10_000:
                raise OSError(f"PDF too small ({len(data)} bytes)")
            dest.write_bytes(data)
            return True
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            if attempt + 1 >= retries:
                print(f"  FAIL pdf {dest.name}: {e}")
                return False
            time.sleep(2.0 * (attempt + 1))
    return False


def _write_sidecar(entry: dict, md_path: Path, pdf_sandbox_path: str) -> None:
    authors = ", ".join(entry["authors"][:8])
    if len(entry["authors"]) > 8:
        authors += ", et al."
    body = f"""# {entry["title"]}

**arXiv:** {entry["arxiv_id"]} · **Published:** {entry["published"]}  
**Authors:** {authors}  
**PDF:** `{pdf_sandbox_path}`

## Abstract

{entry["abstract"]}
"""
    md_path.write_text(body, encoding="utf-8")


def build_manifest(items: list[dict]) -> dict:
    return {
        "name": "Research Paper RAG Corpus",
        "description": "Fifty recent arXiv PDFs (cs.LG / cs.CL / cs.AI) with markdown sidecars under sandbox/research_papers/",
        "item_count": len(items),
        "index_tool": "index_directory('research_papers')",
        "retrieve_tool": "search_knowledge",
        "items": items,
    }


def _pinned_local_entries() -> list[dict]:
    """Include high-quality PDFs already in sandbox/papers/ (SkillOpt, AutoResearchClaw, …)."""
    out: list[dict] = []
    if not PINNED_PDF_DIR.is_dir():
        return out
    for pdf in sorted(PINNED_PDF_DIR.glob("*.pdf")):
        stem = pdf.stem
        arxiv_id = re.sub(r"v\d+$", "", stem)
        try:
            meta = _fetch_arxiv_entries(max_results=1, query=f"id:{arxiv_id}")[0]
            meta["local_pdf"] = pdf
            out.append(meta)
            continue
        except (IndexError, urllib.error.URLError, ET.ParseError):
            pass
        title = stem.replace("_", " ")
        out.append(
            {
                "arxiv_id": arxiv_id,
                "title": title,
                "abstract": f"Pinned local PDF from sandbox/papers/{pdf.name}.",
                "authors": [],
                "published": "",
                "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}.pdf",
                "local_pdf": pdf,
            }
        )
    return out


def build_manifest_from_disk() -> dict:
    """Rebuild MANIFEST.json from files already in sandbox/research_papers/."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest_items: list[dict] = []
    for md in sorted(OUT_DIR.glob("*.md")):
        stem = md.stem
        pdf = OUT_DIR / f"{stem}.pdf"
        text = md.read_text(encoding="utf-8")
        title = text.split("\n", 1)[0].lstrip("# ").strip() if text.startswith("#") else stem
        manifest_items.append(
            {
                "id": stem,
                "arxiv_id": re.sub(r"v\d+$", "", stem),
                "path": f"sandbox/research_papers/{md.name}",
                "sandbox_path": f"research_papers/{md.name}",
                "pdf_path": f"sandbox/research_papers/{pdf.name}" if pdf.is_file() else "",
                "pdf_sandbox_path": f"research_papers/{pdf.name}" if pdf.is_file() else "",
                "title": title,
                "word_count": len(text.split()),
            }
        )
    manifest = build_manifest(manifest_items)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Manifest: {len(manifest_items)} items → {MANIFEST_PATH}")
    return manifest


def download_corpus(*, count: int = 50, skip_pdf: bool = False, from_disk: bool = False) -> dict:
    if from_disk:
        return build_manifest_from_disk()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pinned = _pinned_local_entries()
    need = max(0, count - len(pinned))
    print(f"Fetching {need} arXiv entries (+ {len(pinned)} pinned local PDFs)…")
    entries = _fetch_arxiv_entries(max_results=need + 10)  # buffer for dedupe
    seen = {p["arxiv_id"] for p in pinned}
    merged: list[dict] = list(pinned)
    for e in entries:
        if e["arxiv_id"] in seen:
            continue
        merged.append(e)
        seen.add(e["arxiv_id"])
        if len(merged) >= count:
            break
    entries = merged[:count]

    manifest_items: list[dict] = []
    ok_pdfs = 0
    for i, entry in enumerate(entries, start=1):
        stem = _safe_stem(entry["arxiv_id"])
        pdf_name = f"{stem}.pdf"
        md_name = f"{stem}.md"
        pdf_path = OUT_DIR / pdf_name
        md_path = OUT_DIR / md_name
        pdf_sandbox = f"research_papers/{pdf_name}"

        print(f"[{i}/{len(entries)}] {entry['arxiv_id']} — {entry['title'][:72]}…")
        local_pdf = entry.get("local_pdf")
        if local_pdf is not None:
            if not pdf_path.is_file() or pdf_path.stat().st_size < 10_000:
                pdf_path.write_bytes(local_pdf.read_bytes())
            ok_pdfs += 1
        elif not skip_pdf:
            if _download_pdf(entry["pdf_url"], pdf_path):
                ok_pdfs += 1
            time.sleep(3.0)  # arXiv fair-use pacing
        _write_sidecar(entry, md_path, pdf_sandbox)

        manifest_items.append(
            {
                "id": stem,
                "arxiv_id": entry["arxiv_id"],
                "path": f"sandbox/research_papers/{md_name}",
                "sandbox_path": f"research_papers/{md_name}",
                "pdf_path": f"sandbox/research_papers/{pdf_name}",
                "pdf_sandbox_path": pdf_sandbox,
                "title": entry["title"],
                "published": entry["published"],
                "word_count": len(entry["abstract"].split()),
            }
        )

    manifest = build_manifest(manifest_items)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    catalog_path = ROOT / "corpus" / "papers_catalog.json"
    serializable = [{k: v for k, v in e.items() if k != "local_pdf"} for e in entries]
    catalog_path.write_text(
        json.dumps({"papers": serializable, "manifest_items": len(manifest_items)}, indent=2),
        encoding="utf-8",
    )
    print(f"\nDone: {len(manifest_items)} sidecars, {ok_pdfs} PDFs → {OUT_DIR}")
    print(f"Manifest: {MANIFEST_PATH}")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Download arXiv research corpus")
    parser.add_argument("--count", type=int, default=50)
    parser.add_argument("--skip-pdf", action="store_true", help="Metadata + sidecars only")
    parser.add_argument("--from-disk", action="store_true", help="Rebuild manifest from existing files")
    args = parser.parse_args()
    if args.from_disk:
        build_manifest_from_disk()
        return
    download_corpus(count=max(1, min(100, args.count)), skip_pdf=args.skip_pdf)


if __name__ == "__main__":
    main()
