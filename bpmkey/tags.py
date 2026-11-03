"""Lectura y escritura de los frames ID3 TBPM / TKEY en archivos WAV y MP3."""

from __future__ import annotations

from pathlib import Path

from mutagen.id3 import TBPM, TKEY, Encoding
from mutagen.mp3 import MP3
from mutagen.wave import WAVE


def _open(path: str | Path):
    ext = Path(path).suffix.lower()
    if ext == ".wav":
        return WAVE(path)
    if ext == ".mp3":
        return MP3(path)
    raise ValueError(f"Formato no soportado: {ext}")


def _frame_text(tags, frame_id: str) -> str | None:
    frame = tags.get(frame_id)
    if frame is None or not frame.text:
        return None
    value = str(frame.text[0]).strip()
    return value or None


def read_tags(path: str | Path) -> tuple[str | None, str | None]:
    """Devuelve (bpm, key) tal como están guardados, o None si no existen."""
    audio = _open(path)
    if audio.tags is None:
        return None, None
    return _frame_text(audio.tags, "TBPM"), _frame_text(audio.tags, "TKEY")


def write_tags(path: str | Path, bpm: str | None = None, key: str | None = None) -> None:
    """Graba TBPM y/o TKEY (ID3v2.3, el más compatible). Ignora los valores None."""
    if bpm is None and key is None:
        return
    audio = _open(path)
    if audio.tags is None:
        audio.add_tags()
    if bpm is not None:
        audio.tags.setall("TBPM", [TBPM(encoding=Encoding.LATIN1, text=[bpm])])
    if key is not None:
        audio.tags.setall("TKEY", [TKEY(encoding=Encoding.LATIN1, text=[key])])
    audio.save(v2_version=3)
