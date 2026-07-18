"""Application resources shared by FastAPI requests."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from fastapi import Request

from forge.analytics.schema import init_db
from forge.config import CHROMA_PATH, DB_PATH, EMBEDDING_MODEL, EMBEDDING_PROVIDER
from forge.rag.embedding import get_embedding_service
from forge.rag.vectorstore import ChromaStore


class SQLiteConnections:
    """Reuse one SQLite connection per worker thread and close them at shutdown."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._local = threading.local()
        self._all: list[sqlite3.Connection] = []
        self._lock = threading.Lock()

    def get(self) -> sqlite3.Connection:
        connection = getattr(self._local, "connection", None)
        if connection is None:
            connection = sqlite3.connect(self.path, check_same_thread=False)
            connection.row_factory = sqlite3.Row
            init_db(connection)
            with self._lock:
                self._all.append(connection)
            self._local.connection = connection
        return connection

    def close_all(self) -> None:
        with self._lock:
            connections = list(self._all)
            self._all.clear()
        for connection in connections:
            connection.close()


class ForgeRuntime:
    """Own process-scoped local model, Chroma, and SQLite resources."""

    def __init__(self, db_path: str | Path = DB_PATH, chroma_path: str | Path = CHROMA_PATH) -> None:
        self.db_path = Path(db_path)
        self.chroma_path = Path(chroma_path)
        self.database = SQLiteConnections(self.db_path)
        self.embedding_service = None
        self.chroma_store: ChromaStore | None = None
        self.startup_error: str | None = None

    def startup(self) -> None:
        """Initialize expensive resources once for the process."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.embedding_service = get_embedding_service()
        except Exception as exc:
            self.startup_error = str(exc)
        try:
            store = ChromaStore(self.chroma_path)
            store.count()
            self.chroma_store = store
        except Exception as exc:
            self.startup_error = self.startup_error or str(exc)
        self.database.get()

    def shutdown(self) -> None:
        """Close SQLite connections; cached model and Chroma resources are process-scoped."""
        self.database.close_all()

    @property
    def semantic_ready(self) -> bool:
        return self.embedding_service is not None and self.chroma_store is not None

    def connection(self) -> sqlite3.Connection:
        return self.database.get()


def get_runtime(request: Request) -> ForgeRuntime:
    """Resolve the process runtime attached by the application lifespan."""
    return request.app.state.runtime


def embedding_settings() -> tuple[str, str]:
    """Return configured embedding provider and model for API metadata."""
    return EMBEDDING_PROVIDER, EMBEDDING_MODEL
