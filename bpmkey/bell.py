"""Campanita sintetizada que suena al terminar un proceso.

Reproduce el WAV con el mecanismo nativo de cada sistema operativo, sin
depender de QtMultimedia:
  * Windows: winsound (biblioteca estándar)
  * macOS:   afplay
  * Linux:   paplay / pw-play / aplay (el primero disponible)
Si nada de eso funciona, usa el beep del sistema.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import threading
import wave
from pathlib import Path

import numpy as np

# (relación de frecuencia, amplitud, tiempo de decaimiento en s): parciales
# inarmónicos típicos de una campana.
_PARTIALS = [
    (0.50, 0.30, 1.30),
    (1.00, 1.00, 1.60),
    (1.19, 0.45, 1.00),
    (1.56, 0.35, 0.80),
    (2.00, 0.50, 0.70),
    (2.51, 0.25, 0.50),
    (2.66, 0.20, 0.45),
    (3.01, 0.15, 0.35),
    (4.16, 0.10, 0.25),
]


def make_bell_wav(path: Path, f0: float = 1046.5, seconds: float = 2.5, sr: int = 44100) -> None:
    t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
    signal = np.zeros_like(t)
    for ratio, amp, decay in _PARTIALS:
        signal += amp * np.sin(2 * np.pi * f0 * ratio * t) * np.exp(-t / decay)
    signal *= 1 - np.exp(-t / 0.002)              # ataque suave, sin "click"
    signal *= 0.8 / np.max(np.abs(signal))
    pcm = (signal * 32767).astype("<i2")
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def _player_command() -> list[str] | None:
    if sys.platform == "darwin":
        return ["afplay"] if shutil.which("afplay") else None
    for cmd in (["paplay"], ["pw-play"], ["aplay", "-q"]):
        if shutil.which(cmd[0]):
            return cmd
    return None


class Bell:
    def __init__(self, parent=None) -> None:  # parent se acepta por compatibilidad con Qt
        self._path: Path | None = None
        try:
            path = Path(tempfile.gettempdir()) / "bpmkey_bell.wav"
            make_bell_wav(path)
            self._path = path
        except OSError:
            self._path = None

    def ring(self) -> None:
        if self._path is not None and self._play(self._path):
            return
        self._system_beep()

    @staticmethod
    def _play(path: Path) -> bool:
        if sys.platform == "win32":
            try:
                import winsound

                winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
                return True
            except Exception:
                return False

        cmd = _player_command()
        if cmd is None:
            return False
        try:
            proc = subprocess.Popen(
                [*cmd, str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        except OSError:
            return False
        # Recoger el proceso al terminar para no dejar zombies.
        threading.Thread(target=proc.wait, daemon=True).start()
        return True

    @staticmethod
    def _system_beep() -> None:
        try:
            from PySide6.QtWidgets import QApplication

            QApplication.beep()
        except Exception:
            print("\a", end="", flush=True)
