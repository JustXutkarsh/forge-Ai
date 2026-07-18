from functools import lru_cache
from pathlib import Path

from forge.profiling import chroma_call, stage


@lru_cache(maxsize=4)
def _persistent_client(path: str):
    """Create one persistent Chroma client per configured path."""
    import chromadb
    return chromadb.PersistentClient(path=path)


@lru_cache(maxsize=4)
def _collection(path: str):
    """Open one Forge collection per configured Chroma path."""
    client = _persistent_client(path)
    return client.get_or_create_collection("forge_tickets")


class ChromaStore:
    def __init__(self, path: str | Path):
        normalized_path = str(path)
        with stage("Chroma initialization"):
            try:
                import chromadb
            except ImportError as exc:
                raise RuntimeError("ChromaDB is optional; install requirements.txt to enable vector storage") from exc
            self.client = chroma_call("PersistentClient(...)", _persistent_client, normalized_path)
            self.collection = chroma_call("client.get_or_create_collection('forge_tickets')", _collection, normalized_path)

    def upsert(self, ids: list[str], documents: list[str], embeddings: list[list[float]], metadatas: list[dict]) -> None:
        return chroma_call(
            "collection.upsert(...)",
            self.collection.upsert,
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )

    def query(self, embedding: list[float], n: int = 5) -> list[dict]:
        return chroma_call(
            "collection.query(...)",
            self.collection.query,
            query_embeddings=[embedding],
            n_results=n,
        )

    def count(self) -> int:
        """Return the number of vectors in the cached collection."""
        return chroma_call("collection.count()", self.collection.count)

    def get(self, limit: int = 1) -> dict:
        """Read a bounded sample for health checks."""
        return chroma_call("collection.get()", self.collection.get, limit=limit, include=["metadatas"])
