# -*- mode: python ; coding: utf-8 -*-
# Spec de PyInstaller multiplataforma.  Uso:  pyinstaller --noconfirm bpmkey.spec
#   Windows -> dist/BPMKeyTagger/BPMKeyTagger.exe
#   macOS   -> dist/BPM Key Tagger.app
#   Linux   -> dist/BPMKeyTagger/BPMKeyTagger
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

APP_NAME = "BPMKeyTagger"
DISPLAY_NAME = "BPM Key Tagger"
VERSION = "0.1.0"

# librosa carga sus submódulos de forma diferida (lazy_loader + __init__.pyi):
# el análisis estático no los ve, así que se agregan explícitamente.
datas = collect_data_files("librosa")
hiddenimports = collect_submodules("librosa") + ["soundfile", "soxr", "mutagen.wave", "mutagen.mp3"]

a = Analysis(
    ["run_bpmkey.py"],
    pathex=["."],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "IPython", "pytest", "librosa.display"],
    # numba necesita los .py reales de librosa en disco para compilar/cachear.
    module_collection_mode={"librosa": "pyz+py"},
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    console=False,                 # app de ventana, sin consola
    upx=False,
    argv_emulation=False,
    target_arch=None,              # macOS: arquitectura del Python usado
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(exe, a.binaries, a.datas, name=APP_NAME, upx=False)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name=f"{DISPLAY_NAME}.app",
        icon=None,
        bundle_identifier="ar.ideapixel.bpmkeytagger",
        version=VERSION,
        info_plist={
            "CFBundleDisplayName": DISPLAY_NAME,
            "CFBundleShortVersionString": VERSION,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
        },
    )
