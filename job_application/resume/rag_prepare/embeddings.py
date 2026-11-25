"""Embedding model for RAG prepare."""

from __future__ import annotations

import os
import re


def embed_backend() -> str:
    return (os.getenv("EMBED_BACKEND") or "huggingface").strip().lower()


def embed_model_id() -> str:
    """Stable id for cache paths (backend + model name)."""
    backend = embed_backend()
    if backend == "openai":
        name = (os.getenv("OPENAI_EMBED_MODEL") or "text-embedding-3-small").strip()
        return f"openai_{_slug(name)}"
    name = (os.getenv("EMBED_MODEL_NAME") or "BAAI/bge-small-en-v1.5").strip()
    return f"hf_{_slug(name)}"


def _slug(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", text).strip("_") or "default"


def get_embed_model():
    """Default: local Hugging Face. Set EMBED_BACKEND=openai for OpenAI embeddings."""
    backend = embed_backend()
    if backend == "openai":
        from llama_index.embeddings.openai import OpenAIEmbedding

        api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
        if not api_key:
            raise ValueError("OPENAI_API_KEY required when EMBED_BACKEND=openai")
        model = (os.getenv("OPENAI_EMBED_MODEL") or "text-embedding-3-small").strip()
        return OpenAIEmbedding(api_key=api_key, model=model)

    if backend not in ("huggingface", "hf", "local"):
        raise ValueError(f"Unknown EMBED_BACKEND={backend!r} (use huggingface or openai)")

    from llama_index.embeddings.huggingface import HuggingFaceEmbedding

    model_name = os.getenv("EMBED_MODEL_NAME", "BAAI/bge-small-en-v1.5")
    return HuggingFaceEmbedding(model_name=model_name)
