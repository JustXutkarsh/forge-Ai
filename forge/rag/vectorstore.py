from pathlib import Path


class ChromaStore:
    def __init__(self, path: str | Path):
        try:
            import chromadb
        except ImportError as exc:
            raise RuntimeError("ChromaDB is optional; install requirements.txt to enable vector storage") from exc
        self.client = chromadb.PersistentClient(path=str(path))
        self.collection = self.client.get_or_create_collection("forge_tickets")

    def upsert(self, ids: list[str], documents: list[str], embeddings: list[list[float]], metadatas: list[dict]) -> None:
        self.collection.upsert(ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas)

    def query(self, embedding: list[float], n: int = 5) -> list[dict]:
        return self.collection.query(query_embeddings=[embedding], n_results=n)
