import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


ROOT = Path.cwd()
DB_PATH = Path(os.getenv("FORGE_DB", "data/forge.db"))
CHROMA_PATH = Path(os.getenv("FORGE_CHROMA", "data/chroma"))
OUTPUTS = Path(os.getenv("FORGE_OUTPUTS", "outputs"))
EMBED_LIMIT = int(os.getenv("FORGE_EMBED_LIMIT", "0") or 0)


def ensure_dirs() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHROMA_PATH.parent.mkdir(parents=True, exist_ok=True)
    (OUTPUTS / "logs").mkdir(parents=True, exist_ok=True)
    (OUTPUTS / "reports").mkdir(parents=True, exist_ok=True)
