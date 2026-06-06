from __future__ import annotations

from app.config import get_settings
from app.schemas.evidence import FactResult


def remember_fact_result(result: FactResult) -> None:
    """Optionally index evidence snippets in Chroma without making it a hard dependency."""

    settings = get_settings()
    if not settings.enable_chroma_memory or result.error:
        return

    try:
        import chromadb
    except Exception:
        return

    client = chromadb.PersistentClient(path=str(settings.resolved_chroma_dir))
    collection = client.get_or_create_collection("excel_agent_evidence")
    documents = []
    metadatas = []
    ids = []
    for index, evidence in enumerate(result.evidence):
        text = " ".join(
            part
            for part in [evidence.title, evidence.snippet, str(result.value)]
            if part
        )
        if not text:
            continue
        documents.append(text)
        metadatas.append(
            {
                "entity": result.request.entity,
                "attribute": result.request.attribute,
                "kind": evidence.kind,
                "url": evidence.url or "",
            }
        )
        ids.append(f"{result.request.entity}:{result.request.attribute}:{index}")
    if documents:
        collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
