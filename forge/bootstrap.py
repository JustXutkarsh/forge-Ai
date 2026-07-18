"""Prepare Forge's large local data artifacts before API startup."""

from __future__ import annotations

import logging
import os
import shutil
import time
from pathlib import Path
from zipfile import ZipFile

import requests

logger = logging.getLogger("forge.bootstrap")

DOWNLOAD_RETRIES = 3
DOWNLOAD_CHUNK_SIZE = 1024 * 1024


def _artifact_ready(path: Path, directory: bool = False) -> bool:
    """Return whether a downloaded artifact is present and non-empty."""
    if directory:
        return path.is_dir() and any(path.iterdir())
    return path.is_file() and path.stat().st_size > 0


def _download_file(url: str, destination: Path) -> None:
    """Stream a remote file to disk with bounded retries and an atomic rename."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.part")
    last_error: Exception | None = None

    for attempt in range(1, DOWNLOAD_RETRIES + 1):
        try:
            logger.info("Downloading %s (attempt %d/%d)", destination.name, attempt, DOWNLOAD_RETRIES)
            with requests.get(url, stream=True, timeout=(10, 120)) as response:
                response.raise_for_status()
                with temporary.open("wb") as output:
                    for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                        if chunk:
                            output.write(chunk)
            os.replace(temporary, destination)
            logger.info("Downloaded %s (%d bytes)", destination, destination.stat().st_size)
            return
        except (requests.RequestException, OSError) as exc:
            last_error = exc
            temporary.unlink(missing_ok=True)
            logger.warning("Download failed for %s on attempt %d/%d: %s", destination.name, attempt, DOWNLOAD_RETRIES, exc)
            if attempt < DOWNLOAD_RETRIES:
                time.sleep(attempt)

    raise RuntimeError(f"Could not download {url} after {DOWNLOAD_RETRIES} attempts") from last_error


def _safe_extract(archive: Path, destination: Path) -> None:
    """Extract an archive while rejecting paths outside the destination."""
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with ZipFile(archive) as zipped:
        for member in zipped.infolist():
            target = (destination / member.filename).resolve()
            if target != root and root not in target.parents:
                raise RuntimeError(f"Unsafe path in Chroma archive: {member.filename}")
        zipped.extractall(destination)


def _extract_chroma_archive(archive: Path, destination: Path) -> None:
    """Extract Chroma into a temporary directory, then publish it atomically."""
    temporary = destination.parent / f".{destination.name}.extracting"
    if temporary.exists():
        shutil.rmtree(temporary)
    try:
        _safe_extract(archive, temporary)
        if not any(temporary.iterdir()):
            raise RuntimeError("Chroma archive is empty")
        if destination.exists():
            shutil.rmtree(destination)
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def _required_url(environment_name: str, artifact: Path) -> str:
    """Return a configured artifact URL or raise a useful startup error."""
    value = os.getenv(environment_name, "").strip()
    if not value:
        raise RuntimeError(
            f"{artifact} is missing. Set {environment_name} to a reachable download URL before starting Forge."
        )
    return value


def ensure_runtime_assets(db_path: str | Path, chroma_path: str | Path) -> None:
    """Ensure SQLite and Chroma artifacts exist before Forge initializes them."""
    database = Path(db_path)
    chroma = Path(chroma_path)
    database.parent.mkdir(parents=True, exist_ok=True)
    chroma.parent.mkdir(parents=True, exist_ok=True)

    if _artifact_ready(database):
        logger.info("SQLite artifact ready: %s", database)
    else:
        _download_file(_required_url("FORGE_DB_URL", database), database)

    if _artifact_ready(chroma, directory=True):
        logger.info("Chroma artifact ready: %s", chroma)
        return

    archive = chroma.parent / "chroma.zip"
    _download_file(_required_url("FORGE_CHROMA_URL", chroma), archive)
    try:
        logger.info("Extracting Chroma archive into %s", chroma)
        _extract_chroma_archive(archive, chroma)
    finally:
        archive.unlink(missing_ok=True)
    logger.info("Chroma artifact ready: %s", chroma)
