"""Punto de entrada para PyInstaller (y alternativa a `python -m bpmkey`)."""

import multiprocessing

if __name__ == "__main__":
    multiprocessing.freeze_support()  # imprescindible: los análisis corren en subprocesos

    # Importar bpmkey configura NUMBA_CACHE_DIR antes de que se cargue librosa.
    from bpmkey.app import run

    raise SystemExit(run())
