import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass


OPENAI_KEY_ERROR = "OpenAI API key not found.\n\nCreate a .env file in the project root and add:\n\nOPENAI_API_KEY=your_key_here"


class OpenAIConfigurationError(RuntimeError):
    """Raised when an OpenAI-backed command has no configured API key."""


def require_openai_api_key() -> str:
    """Return the configured OpenAI key or raise a user-facing configuration error."""
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise OpenAIConfigurationError(OPENAI_KEY_ERROR)
    return key


DB_PATH = Path(os.getenv("FORGE_DB", "data/forge.db"))
CHROMA_PATH = Path(os.getenv("FORGE_CHROMA", "data/chroma"))
OUTPUTS = Path(os.getenv("FORGE_OUTPUTS", "outputs"))
EMBED_LIMIT = int(os.getenv("FORGE_EMBED_LIMIT", "0") or 0)


def ensure_dirs() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHROMA_PATH.parent.mkdir(parents=True, exist_ok=True)
    (OUTPUTS / "logs").mkdir(parents=True, exist_ok=True)
    (OUTPUTS / "reports").mkdir(parents=True, exist_ok=True)
