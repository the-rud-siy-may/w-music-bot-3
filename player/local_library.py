"""
Local song library resolver for MVP playback.

Maps queries like "faded" → songs/faded.mp3
"""

from __future__ import annotations

from pathlib import Path

from utils.logger import get_logger

logger = get_logger(__name__)

AUDIO_EXTENSIONS = (".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac")


def resolve_local_song(query: str, songs_dir: Path) -> Path | None:
    """
    Resolve a song name to a file under songs_dir.

    Examples:
      "faded"     → songs/faded.mp3
      "believer"  → songs/believer.mp3
    """
    if not query or not query.strip():
        return None

    songs_dir = Path(songs_dir)
    if not songs_dir.is_dir():
        logger.warning("Songs directory missing: %s", songs_dir)
        return None

    key = query.strip().lower()
    # Remove path components — local names only
    key = Path(key).name

    # Exact stem match
    for path in songs_dir.iterdir():
        if not path.is_file():
            continue
        if path.suffix.lower() in AUDIO_EXTENSIONS and path.stem.lower() == key:
            logger.debug("Resolved %r → %s", query, path)
            return path.resolve()

    # Partial stem match
    for path in songs_dir.iterdir():
        if not path.is_file():
            continue
        if path.suffix.lower() in AUDIO_EXTENSIONS and key in path.stem.lower():
            logger.debug("Resolved %r → %s (partial)", query, path)
            return path.resolve()

    logger.info("No local song for query: %r", query)
    return None


def list_available_songs(songs_dir: Path) -> list[str]:
    """Return stems of available local songs."""
    songs_dir = Path(songs_dir)
    if not songs_dir.is_dir():
        return []
    return sorted(
        p.stem for p in songs_dir.iterdir()
        if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS
    )
