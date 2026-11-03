"""BPM & Key Tagger: detecta BPM y tonalidad y los graba como ID3."""

import os
import sys
import tempfile

__version__ = "0.1.0"

AUDIO_EXTS = {".wav", ".mp3"}


def _user_cache_dir() -> str:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Caches")
    else:
        base = os.environ.get("XDG_CACHE_HOME")

    for candidate in (base, tempfile.gettempdir()):
        if not candidate:
            continue
        target = os.path.join(candidate, "BPMKeyTagger", "numba")
        try:
            os.makedirs(target, exist_ok=True)
            probe = os.path.join(target, ".write_test")
            with open(probe, "w") as f:
                f.write("ok")
            os.remove(probe)
            return target
        except OSError:
            continue
    return os.path.join(tempfile.gettempdir(), "BPMKeyTagger", "numba")


# numba (usado por librosa) guarda su caché de compilación junto a los .py de
# librosa. Si esa carpeta no es escribible (Program Files, /Applications, un
# bundle de PyInstaller, permisos restringidos...) en Windows puede quedar en un
# bucle infinito. Se fuerza una carpeta de usuario ANTES de importar librosa.
os.environ.setdefault("NUMBA_CACHE_DIR", _user_cache_dir())
