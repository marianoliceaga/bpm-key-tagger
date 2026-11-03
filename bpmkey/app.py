"""Ventana principal: árbol de carpetas + lista de archivos de audio."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QDir, QSettings, Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDockWidget,
    QFileSystemModel,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QSplitter,
    QStyle,
    QTableView,
    QToolBar,
    QTreeView,
)

from bpmkey import AUDIO_EXTS, __version__
from bpmkey.bell import Bell
from bpmkey.tags import read_tags
from bpmkey.worker import DetectWorker

COL_NAME, COL_BPM, COL_KEY, COL_STATUS = range(4)
PATH_ROLE = Qt.ItemDataRole.UserRole + 1


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("BPM & Key Tagger")
        self.resize(1200, 750)

        self.settings = QSettings("ideapixel", "BPMKeyTagger")
        self.current_dir: str | None = None
        self.worker: DetectWorker | None = None
        self.row_items: dict[str, QStandardItem] = {}  # ruta normalizada -> item de nombre
        self.bell = Bell(self)

        self._build_tree()
        self._build_file_list()
        self._build_toolbar()
        self._build_log()
        self._build_statusbar()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.tree)
        splitter.addWidget(self.table)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([380, 820])
        self.setCentralWidget(splitter)

        self._restore_state()

    # ------------------------------------------------------------- widgets
    def _build_tree(self) -> None:
        self.fs_model = QFileSystemModel(self)
        self.fs_model.setFilter(QDir.Filter.AllDirs | QDir.Filter.NoDotAndDotDot | QDir.Filter.Drives)
        self.fs_model.setRootPath("")

        self.tree = QTreeView()
        self.tree.setModel(self.fs_model)
        for col in range(1, self.fs_model.columnCount()):
            self.tree.hideColumn(col)
        self.tree.setHeaderHidden(True)
        self.tree.setAnimated(False)
        self.tree.setSortingEnabled(True)
        self.tree.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.tree.selectionModel().currentChanged.connect(self._on_dir_changed)

    def _build_file_list(self) -> None:
        self.file_model = QStandardItemModel(0, 4, self)
        self.file_model.setHorizontalHeaderLabels(["Archivo", "BPM", "Tonalidad", "Estado"])

        self.table = QTableView()
        self.table.setModel(self.file_model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setWordWrap(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(COL_BPM, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COL_KEY, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COL_STATUS, QHeaderView.ResizeMode.Interactive)
        header.resizeSection(COL_STATUS, 260)

    def _build_toolbar(self) -> None:
        tb = QToolBar("Herramientas")
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(tb)
        style = self.style()

        self.act_bpm = QAction(style.standardIcon(QStyle.StandardPixmap.SP_MediaSeekForward), "Detectar BPMs", self)
        self.act_key = QAction(style.standardIcon(QStyle.StandardPixmap.SP_MediaVolume), "Detectar Tonalidad", self)
        self.act_both = QAction(style.standardIcon(QStyle.StandardPixmap.SP_MediaPlay), "Detectar BPMs y Tonalidad", self)
        self.act_cancel = QAction(style.standardIcon(QStyle.StandardPixmap.SP_MediaStop), "Cancelar", self)
        self.act_refresh = QAction(style.standardIcon(QStyle.StandardPixmap.SP_BrowserReload), "Refrescar", self)

        self.act_bpm.setToolTip("Detecta el BPM de los archivos de la carpeta seleccionada y todas sus subcarpetas")
        self.act_key.setToolTip("Detecta la tonalidad de los archivos de la carpeta seleccionada y todas sus subcarpetas")
        self.act_both.setToolTip("Detecta BPM y tonalidad de los archivos de la carpeta seleccionada y todas sus subcarpetas")
        self.act_refresh.setShortcut(QKeySequence.StandardKey.Refresh)
        self.act_cancel.setEnabled(False)

        self.act_bpm.triggered.connect(lambda: self._start(True, False))
        self.act_key.triggered.connect(lambda: self._start(False, True))
        self.act_both.triggered.connect(lambda: self._start(True, True))
        self.act_cancel.triggered.connect(self._cancel)
        self.act_refresh.triggered.connect(self._reload_files)

        for act in (self.act_bpm, self.act_key, self.act_both):
            tb.addAction(act)
        tb.addSeparator()
        tb.addAction(self.act_cancel)
        tb.addSeparator()
        tb.addAction(self.act_refresh)

    def _build_log(self) -> None:
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(5000)
        dock = QDockWidget("Registro", self)
        dock.setObjectName("log_dock")
        dock.setWidget(self.log)
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable | QDockWidget.DockWidgetFeature.DockWidgetFloatable)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)
        self.resizeDocks([dock], [150], Qt.Orientation.Vertical)

    def _build_statusbar(self) -> None:
        self.status_label = QLabel("Seleccioná una carpeta")
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(320)
        self.progress.setTextVisible(True)
        self.progress.hide()
        self.statusBar().addWidget(self.status_label, 1)
        self.statusBar().addPermanentWidget(self.progress)

    # ------------------------------------------------------- estado/ajustes
    def _restore_state(self) -> None:
        geometry = self.settings.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        last = self.settings.value("last_dir", "", type=str)
        start = last if last and os.path.isdir(last) else QDir.homePath()
        # Esperar a que el modelo del sistema de archivos cargue antes de seleccionar.
        QTimer.singleShot(0, lambda: self._select_dir(start))

    def _select_dir(self, path: str) -> None:
        index = self.fs_model.index(path)
        if not index.isValid():
            return
        self.tree.setCurrentIndex(index)
        self.tree.expand(index)
        QTimer.singleShot(300, lambda: self.tree.scrollTo(index, QAbstractItemView.ScrollHint.PositionAtCenter))

    def closeEvent(self, event) -> None:
        if self.worker and self.worker.isRunning():
            answer = QMessageBox.question(
                self, "Proceso en curso", "Hay un análisis en curso. ¿Cancelarlo y salir?"
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.worker.cancel()
            self.worker.wait()
        self.settings.setValue("geometry", self.saveGeometry())
        if self.current_dir:
            self.settings.setValue("last_dir", self.current_dir)
        super().closeEvent(event)

    # ------------------------------------------------------ lista archivos
    def _on_dir_changed(self, current, _previous) -> None:
        path = self.fs_model.filePath(current)
        if not path or not os.path.isdir(path):
            return
        self.current_dir = path
        self.settings.setValue("last_dir", path)
        self._reload_files()

    def _reload_files(self) -> None:
        self.file_model.removeRows(0, self.file_model.rowCount())
        self.row_items.clear()
        if not self.current_dir:
            return

        try:
            entries = sorted(
                (e for e in os.scandir(self.current_dir)
                 if e.is_file() and Path(e.name).suffix.lower() in AUDIO_EXTS and not e.name.startswith("._")),
                key=lambda e: e.name.lower(),
            )
        except OSError as exc:
            self.status_label.setText(f"No se puede leer la carpeta: {exc}")
            return

        self.table.setSortingEnabled(False)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            for entry in entries:
                status = ""
                try:
                    bpm, key = read_tags(entry.path)
                except Exception as exc:
                    bpm = key = None
                    status = f"Error al leer tags: {exc}"
                name_item = QStandardItem(entry.name)
                name_item.setData(entry.path, PATH_ROLE)
                name_item.setToolTip(entry.path)
                bpm_item = QStandardItem(bpm or "")
                bpm_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                key_item = QStandardItem(key or "")
                key_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                status_item = QStandardItem(status)
                self.file_model.appendRow([name_item, bpm_item, key_item, status_item])
                self.row_items[os.path.normcase(os.path.abspath(entry.path))] = name_item
        finally:
            QApplication.restoreOverrideCursor()
            self.table.setSortingEnabled(True)

        if not (self.worker and self.worker.isRunning()):
            self.status_label.setText(f"{len(entries)} archivos de audio en {self.current_dir}")

    def _update_row(self, path: str, bpm: str, key: str, status: str) -> None:
        item = self.row_items.get(os.path.normcase(os.path.abspath(path)))
        if item is None:  # archivo de una subcarpeta: no está en la lista visible
            return
        row = item.row()
        if bpm:
            self.file_model.item(row, COL_BPM).setText(bpm)
        if key:
            self.file_model.item(row, COL_KEY).setText(key)
        status_item = self.file_model.item(row, COL_STATUS)
        status_item.setText(status)
        status_item.setToolTip(status)

    # ------------------------------------------------------------ proceso
    def _set_running(self, running: bool) -> None:
        for act in (self.act_bpm, self.act_key, self.act_both):
            act.setEnabled(not running)
        self.act_cancel.setEnabled(running)
        self.progress.setVisible(running)

    def _start(self, want_bpm: bool, want_key: bool) -> None:
        if self.worker and self.worker.isRunning():
            return
        if not self.current_dir:
            QMessageBox.information(self, "Sin carpeta", "Seleccioná una carpeta en el panel izquierdo.")
            return

        what = " y ".join(x for x, on in (("BPM", want_bpm), ("tonalidad", want_key)) if on)
        self.log.appendPlainText(f"\n=== Detectando {what} en {self.current_dir} ===")
        self.status_label.setText(f"Buscando archivos para detectar {what}…")
        self.progress.setRange(0, 0)  # indeterminado mientras se escanea

        self.worker = DetectWorker(self.current_dir, want_bpm, want_key, self)
        self.worker.file_done.connect(self._update_row)
        self.worker.progress.connect(self._on_progress)
        self.worker.message.connect(self.log.appendPlainText)
        self.worker.summary.connect(self._on_summary)
        self.worker.finished.connect(lambda: self._set_running(False))
        self._set_running(True)
        self.worker.start()

    def _cancel(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.act_cancel.setEnabled(False)
            self.status_label.setText("Cancelando…")

    def _on_progress(self, done: int, total: int) -> None:
        self.progress.setRange(0, max(total, 1))
        self.progress.setValue(done if total else 1)
        self.progress.setFormat(f"{done} / {total}")
        if total:
            self.status_label.setText(f"Analizando… {done} de {total}")

    def _on_summary(self, s: dict) -> None:
        text = (
            f"{'Cancelado' if s['cancelled'] else 'Terminado'}: "
            f"{s['found']} encontrados, {s['written']} grabados, "
            f"{s['skipped']} ya tenían los datos, {s['errors']} errores."
        )
        self.status_label.setText(text)
        self.log.appendPlainText(text)
        if not s["cancelled"]:
            self.bell.ring()


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("BPM & Key Tagger")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("ideapixel")
    window = MainWindow()
    window.show()
    return app.exec()
