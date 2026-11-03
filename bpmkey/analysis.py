"""Detección de BPM y tonalidad.

Este módulo se ejecuta dentro de procesos hijos (ProcessPoolExecutor), por eso
las funciones son de nivel módulo y librosa se importa de forma diferida.
"""

from __future__ import annotations

import warnings

import numpy as np

SR = 22050          # frecuencia de muestreo de análisis
HOP = 512           # resolución temporal (~23.2 ms)
MAX_SECONDS = 90    # ventana máxima de análisis (90 segundos)

# Perfiles de tonalidad de Krumhansl-Kessler (C mayor / C menor)
MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

# Notación compatible con TKEY (máx. 3 caracteres)
MAJOR_NAMES = ["C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
MINOR_NAMES = ["Cm", "C#m", "Dm", "Ebm", "Em", "Fm", "F#m", "Gm", "G#m", "Am", "Bbm", "Bm"]


def load_audio(path: str) -> tuple[np.ndarray, int]:
    import librosa
    import soundfile as sf

    offset = 0.0
    try:
        total_dur = sf.info(path).duration
        if total_dur > MAX_SECONDS + 30.0:
            # Tomar un segmento representativo evitando intros en silencio
            offset = min(30.0, (total_dur - MAX_SECONDS) / 2.0)
    except Exception:
        pass

    y, sr = librosa.load(path, sr=SR, mono=True, offset=offset, duration=MAX_SECONDS, dtype=np.float32)
    if y.size < sr * 2:
        raise ValueError("audio demasiado corto (< 2 s)")
    if not np.any(np.abs(y) > 1e-4) and offset > 0.0:
        y, sr = librosa.load(path, sr=SR, mono=True, offset=0.0, duration=MAX_SECONDS, dtype=np.float32)
    if not np.any(np.abs(y) > 1e-4):
        raise ValueError("audio en silencio")
    return y, sr


def detect_bpm(y: np.ndarray, sr: int) -> float:
    import librosa

    onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP)
    tempo, beats = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr, hop_length=HOP)
    tempo = float(np.atleast_1d(tempo)[0])
    if tempo <= 0:
        raise ValueError("no se detectó pulso")

    # Refinamiento: la estimación de librosa está cuantizada; una regresión
    # lineal sobre los tiempos de los beats da una resolución mucho más fina.
    if len(beats) >= 8:
        times = librosa.frames_to_time(beats, sr=sr, hop_length=HOP)
        slope = np.polyfit(np.arange(len(times)), times, 1)[0]
        if slope > 0:
            refined = 60.0 / slope
            if abs(refined - tempo) / tempo < 0.08:
                tempo = refined
    return tempo


def detect_key(y: np.ndarray, sr: int) -> str:
    import librosa

    y_harm = librosa.effects.harmonic(y, margin=2.0)
    chroma = librosa.feature.chroma_cqt(y=y_harm, sr=sr)
    profile = chroma.mean(axis=1)
    if np.allclose(profile, 0) or np.std(profile) == 0:
        raise ValueError("no hay contenido armónico suficiente")

    best_score, best_name = -np.inf, None
    for tonic in range(12):
        for template, names in ((MAJOR_PROFILE, MAJOR_NAMES), (MINOR_PROFILE, MINOR_NAMES)):
            score = np.corrcoef(profile, np.roll(template, tonic))[0, 1]
            if score > best_score:
                best_score, best_name = score, names[tonic]
    return best_name


def analyze(path: str, want_bpm: bool, want_key: bool) -> dict:
    """Analiza un archivo.

    Devuelve {'path', 'bpm', 'key', 'error'}; bpm/key son strings o None y
    'error' es None si todo salió bien.
    """
    result = {"path": path, "bpm": None, "key": None, "error": None}
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            y, sr = load_audio(path)
            if want_bpm:
                result["bpm"] = str(int(round(detect_bpm(y, sr))))
            if want_key:
                result["key"] = detect_key(y, sr)
    except Exception as exc:  # se reporta en la UI, no debe romper el pool
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result
