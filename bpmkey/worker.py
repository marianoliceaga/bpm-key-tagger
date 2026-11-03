"""Hilo de trabajo: recorre el directorio, analiza en paralelo y graba los tags."""

from __future__ import annotations

import multiprocessing
import os
from collections import deque
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from bpmkey import AUDIO_EXTS
from bpmkey.analysis import analyze
from bpmkey.tags import read_tags, write_tags


def default_workers() -> int:
    # Limitar a máx. 3 procesos para no agotar la RAM cuando se procesan tracks pesados
    return max(1, min((os.cpu_count() or 2) // 2, 3))


class DetectWorker(QThread):
    # path, bpm, key, estado
    file_done = Signal(str, str, str, str)
    progress = Signal(int, int)        # hechos, total
    message = Signal(str)              # línea para el registro
    summary = Signal(dict)

    def __init__(self, root: str, want_bpm: bool, want_key: bool, parent=None) -> None:
        super().__init__(parent)
        self.root = root
        self.want_bpm = want_bpm
        self.want_key = want_key
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    @property
    def cancelled(self) -> bool:
        return self._cancel

    # ------------------------------------------------------------------ run
    def run(self) -> None:
        stats = {"found": 0, "skipped": 0, "written": 0, "errors": 0, "cancelled": False}

        files = self._collect_files()
        stats["found"] = len(files)
        self.message.emit(f"Se encontraron {len(files)} archivos de audio en «{self.root}» y sus subcarpetas.")

        jobs = self._pending_jobs(files, stats)
        total = len(jobs)
        self.progress.emit(0, total)
        if stats["skipped"]:
            self.message.emit(f"{stats['skipped']} archivos ya tenían los datos y se omiten.")

        if total and not self._cancel:
            workers = min(default_workers(), total)
            self.message.emit(f"Analizando {total} archivos con {workers} procesos…")
            self._process(jobs, workers, stats)

        stats["cancelled"] = self._cancel
        self.summary.emit(stats)

    # -------------------------------------------------------------- helpers
    def _collect_files(self) -> list[str]:
        files: list[str] = []
        for dirpath, dirnames, filenames in os.walk(self.root):
            if self._cancel:
                break
            dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
            for name in sorted(filenames):
                if Path(name).suffix.lower() in AUDIO_EXTS and not name.startswith("._"):
                    files.append(os.path.join(dirpath, name))
        return files

    def _pending_jobs(self, files: list[str], stats: dict) -> list[tuple[str, bool, bool]]:
        jobs = []
        for path in files:
            if self._cancel:
                break
            try:
                bpm, key = read_tags(path)
            except Exception as exc:
                stats["errors"] += 1
                self._report(path, None, None, f"Error al leer tags: {exc}")
                continue
            need_bpm = self.want_bpm and not bpm
            need_key = self.want_key and not key
            if need_bpm or need_key:
                jobs.append((path, need_bpm, need_key))
            else:
                stats["skipped"] += 1
        return jobs

    def _process(self, jobs, workers: int, stats: dict) -> None:
        total = len(jobs)
        done = 0
        queue = deque(jobs)
        ctx = multiprocessing.get_context("spawn")
        pool = ProcessPoolExecutor(max_workers=workers, mp_context=ctx, max_tasks_per_child=20)
        pending: dict = {}

        def fill_pool() -> None:
            while queue and len(pending) < workers and not self._cancel:
                job = queue.popleft()
                pending[pool.submit(analyze, *job)] = job

        try:
            fill_pool()
            while pending:
                if self._cancel:
                    self.message.emit("Cancelando… se espera a que terminen los análisis en curso.")
                    for fut in pending:
                        fut.cancel()
                    break

                finished, _ = wait(pending.keys(), timeout=0.25, return_when=FIRST_COMPLETED)
                pool_broken = False
                for fut in finished:
                    job = pending.pop(fut)
                    try:
                        res = fut.result()
                    except BrokenProcessPool:
                        pool_broken = True
                        done += 1
                        stats["errors"] += 1
                        self._report(job[0], None, None, "Error: proceso terminado abruptamente (archivo corrupto o memoria insuficiente)")
                        self.progress.emit(done, total)
                    except Exception as exc:
                        done += 1
                        stats["errors"] += 1
                        self._report(job[0], None, None, f"Error de análisis: {exc}")
                        self.progress.emit(done, total)
                    else:
                        done += 1
                        self._handle_result(res, stats)
                        self.progress.emit(done, total)

                if pool_broken:
                    # Devolver a la cola los trabajos en vuelo que aún no habían terminado
                    for fut, job in list(pending.items()):
                        queue.appendleft(job)
                    pending.clear()
                    pool.shutdown(wait=False, cancel_futures=True)
                    if queue and not self._cancel:
                        pool = ProcessPoolExecutor(max_workers=workers, mp_context=ctx, max_tasks_per_child=20)

                fill_pool()
        finally:
            pool.shutdown(wait=True, cancel_futures=True)

    def _handle_result(self, res: dict, stats: dict) -> None:
        path, bpm, key = res["path"], res["bpm"], res["key"]
        if res["error"]:
            stats["errors"] += 1
            self._report(path, None, None, f"Error de análisis: {res['error']}")
            return
        try:
            write_tags(path, bpm=bpm, key=key)
        except Exception as exc:
            stats["errors"] += 1
            self._report(path, bpm, key, f"Error al grabar: {exc}")
            return

        stats["written"] += 1
        parts = []
        if bpm:
            parts.append(f"BPM {bpm}")
        if key:
            parts.append(f"Tonalidad {key}")
        self._report(path, bpm, key, "Grabado: " + ", ".join(parts))

    def _report(self, path: str, bpm: str | None, key: str | None, status: str) -> None:
        self.file_done.emit(path, bpm or "", key or "", status)
        self.message.emit(f"{'✗' if status.startswith('Error') else '✓'} {path} — {status}")
