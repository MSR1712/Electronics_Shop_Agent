"""
Chroma vector store setup for the two RAG collections:
  - product_catalog: embedded product descriptions + specs
  - company_policies: embedded policy/FAQ document chunks

Uses Chroma's bundled local ONNX MiniLM-L6 model rather than a hosted
embeddings API: no API quota/rate limits and no per-call cost, which matters
once the catalog is large (Google's free-tier embedding quota was hit and
exhausted importing ~1000 products). This runs on plain onnxruntime with no
torch/scipy/sklearn in the inference path — deliberately avoiding
sentence-transformers, whose scipy/sklearn dependency chain gets blocked by
this machine's Windows Application Control policy (same class of block that
affects ffmpeg.exe here).

NOTE: switching embedding models means a different vector space — Chroma
collections built with a previous embedding function must be fully
re-ingested (see scripts/ingest_products.py / scripts/ingest_policies.py),
not incrementally updated, if the model here ever changes again.
"""

from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2
from langchain_chroma import Chroma
from langchain_core.embeddings import Embeddings

from config import settings


class _ChromaONNXEmbeddings(Embeddings):
    """Adapts chromadb's EmbeddingFunction interface (__call__(list[str]))
    to LangChain's Embeddings interface (embed_documents/embed_query),
    which is what langchain_chroma.Chroma's embedding_function expects."""

    def __init__(self) -> None:
        self._fn = ONNXMiniLM_L6_V2()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [list(map(float, v)) for v in self._fn(texts)]

    def embed_query(self, text: str) -> list[float]:
        return list(map(float, self._fn([text])[0]))


def get_embeddings() -> Embeddings:
    return _ChromaONNXEmbeddings()


def get_product_vectorstore() -> Chroma:
    return Chroma(
        collection_name=settings.chroma_collection_products,
        embedding_function=get_embeddings(),
        persist_directory=settings.chroma_persist_dir,
        # Without this, Chroma defaults to raw L2 distance, whose relevance-
        # score conversion isn't calibrated for these embeddings (observed:
        # scores clustered near 0, some negative, tripping LangChain's "must
        # be between 0 and 1" warning) — which broke MIN_RELEVANCE filtering
        # in tools/product_tools.py by making every match look irrelevant.
        # Cosine distance keeps relevance scores meaningfully spread in
        # [0, 1]. Fixed at collection-creation time, so an existing
        # collection must be re-ingested after this change, not just reused.
        collection_metadata={"hnsw:space": "cosine"},
    )


def get_policy_vectorstore() -> Chroma:
    return Chroma(
        collection_name=settings.chroma_collection_policies,
        embedding_function=get_embeddings(),
        persist_directory=settings.chroma_persist_dir,
        collection_metadata={"hnsw:space": "cosine"},
    )
