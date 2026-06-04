# Design Deferrals (Intentional Simplifications)

This note documents deliberate gaps between this demo agent and production RAG systems.

## Dense retrieval only

Vector search uses FAISS with a single embedding model. There is **no hybrid sparse retrieval** partner (BM25 or learned-sparse) and no **Reciprocal Rank Fusion (RRF)** to merge ranked lists from multiple retrievers. Production systems run dense and sparse retrieval in parallel and fuse with RRF for better recall on exact terminology and paraphrase alike.

## Heuristic chunking

Documents split at fixed word windows with overlap. Semantic chunking that respects sentences and section headers is deferred.

## FAISS reload on every read

The index reloads from disk on each `memory.read()` for cross-process consistency when MCP tools index in a subprocess.

## Fixed embedding model

Changing `GEMINI_EMBED_MODEL` invalidates stored vectors; re-index after any embed model change.

See also [`docs/DEFERRALS.md`](../../docs/DEFERRALS.md) and `GET /api/deferrals`.
