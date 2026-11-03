# BPM & Key Tagger

Aplicación de escritorio multiplataforma (Windows / macOS / Linux) que detecta el **BPM** y la **tonalidad** de archivos `.wav` y `.mp3` y los graba en el propio archivo como frames **ID3v2.3** (`TBPM`, `TKEY`).

## Uso

- **Panel izquierdo**: árbol de carpetas.
- **Panel derecho**: archivos de audio de la carpeta seleccionada, con el BPM y la tonalidad que ya tienen grabados.
- **Barra de herramientas**:
  - **Detectar BPMs**, **Detectar Tonalidad** y **Detectar BPMs y Tonalidad** procesan la carpeta seleccionada **y todas sus subcarpetas**.
  - Solo se escribe el dato que falta: si un archivo ya tiene `TBPM` y/o `TKEY`, ese dato no se toca.
  - **Cancelar** detiene el proceso.
  - **Refrescar** (F5) relee la lista.
- Al terminar suena una campanita. El panel *Registro* muestra el detalle de cada archivo.

## Instalación y ejecución

Requiere Python 3.10 o superior.

Con [uv](https://docs.astral.sh/uv/):

```bash
uv sync
uv run python -m bpmkey
```

Con pip:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install PySide6-Essentials librosa mutagen numpy soundfile
python -m bpmkey
```

En **Linux**, la campanita se reproduce con `paplay`, `pw-play` o `aplay` (el primero que esté instalado). Si no hay ninguno, se usa el beep del sistema.

## Cómo funciona

| Paso | Detalle |
|---|---|
| BPM | `librosa.beat.beat_track`, refinado con una regresión lineal sobre los beats y redondeado a entero, como pide el estándar de `TBPM`. |
| Tonalidad | Separación armónica, chroma CQT y correlación con los perfiles de Krumhansl-Kessler (24 tonalidades). Se guarda en notación estándar (`Am`, `F#m`, `Eb`). |
| Tags | `mutagen`: chunk `id3 ` en WAV y cabecera ID3 en MP3, en versión v2.3 por compatibilidad. |
| Rendimiento | Varios archivos se analizan en paralelo, en procesos separados (CPU − 1, máximo 6). Se analizan como máximo los primeros 10 minutos de cada archivo. |

> La detección automática puede dar el doble o la mitad del BPM real, o confundir la tonalidad con su relativa (Am ↔ C), sobre todo en material ambiguo.

## Generar el ejecutable

Se usa PyInstaller con el spec incluido, [`bpmkey.spec`](bpmkey.spec), que sirve para los tres sistemas. **PyInstaller no hace compilación cruzada**: cada ejecutable se genera en su propio sistema operativo (y en macOS, en la arquitectura de destino).

Requisitos comunes: Python 3.10 o superior y [uv](https://docs.astral.sh/uv/getting-started/installation/).

### Windows

```powershell
cd bpm-key-tagger
uv sync
uv run pyinstaller --noconfirm bpmkey.spec
```

- El resultado queda en `dist\BPMKeyTagger\`, y el programa se abre con `BPMKeyTagger.exe`.
- Para distribuirlo, comprimí la carpeta completa en un zip. El `.exe` solo no funciona: necesita la carpeta `_internal` que tiene al lado.
- La primera vez, Windows SmartScreen puede advertir que el programa es de un editor desconocido, porque no está firmado. Se abre con *Más información → Ejecutar de todas formas*.

### macOS

```bash
cd bpm-key-tagger
uv sync
uv run pyinstaller --noconfirm bpmkey.spec
```

- El resultado es `dist/BPM Key Tagger.app`. Se puede arrastrar a `/Applications`.
- Se genera para la arquitectura del Python que lo compila: Apple Silicon (arm64) o Intel (x86_64). Para tener las dos versiones, compilá una vez en cada tipo de Mac.
- Si el `.app` no está firmado, Gatekeeper lo bloquea. Para tu propio uso alcanza con *clic derecho → Abrir*, o con:
  ```bash
  xattr -dr com.apple.quarantine "dist/BPM Key Tagger.app"
  ```
- Para distribuirlo a otras personas conviene firmarlo y notarizarlo. Hace falta una cuenta de Apple Developer:
  ```bash
  codesign --deep --force --options runtime --sign "Developer ID Application: TU NOMBRE (TEAMID)" "dist/BPM Key Tagger.app"
  ditto -c -k --keepParent "dist/BPM Key Tagger.app" BPMKeyTagger.zip
  xcrun notarytool submit BPMKeyTagger.zip --apple-id TU@MAIL --team-id TEAMID --password CONTRASEÑA_DE_APP --wait
  xcrun stapler staple "dist/BPM Key Tagger.app"
  ```

### Linux

```bash
# Debian/Ubuntu: bibliotecas que Qt necesita en tiempo de ejecución
sudo apt install libxcb-cursor0 libxkbcommon-x11-0 libegl1 libgl1 pulseaudio-utils
# Fedora: sudo dnf install xcb-util-cursor libxkbcommon-x11 mesa-libEGL pulseaudio-utils

cd bpm-key-tagger
uv sync
uv run pyinstaller --noconfirm bpmkey.spec
./dist/BPMKeyTagger/BPMKeyTagger
```

- Para distribuirlo, empaquetá la carpeta: `tar czf BPMKeyTagger-linux-x86_64.tar.gz -C dist BPMKeyTagger`.
- El ejecutable depende de la versión de **glibc** del sistema donde se compiló. Compilalo en la distribución más vieja que quieras soportar (por ejemplo, Ubuntu 22.04) y va a funcionar en las más nuevas, pero no al revés.
- Opcional, para que aparezca en el menú de aplicaciones: crear `~/.local/share/applications/bpmkeytagger.desktop` con este contenido:
  ```ini
  [Desktop Entry]
  Type=Application
  Name=BPM Key Tagger
  Exec=/ruta/a/BPMKeyTagger/BPMKeyTagger
  Terminal=false
  Categories=AudioVideo;Audio;
  ```

### Notas
- Se genera en modo *carpeta* (onedir) y no como un único archivo: arranca mucho más rápido y funciona mejor con los subprocesos de análisis.
- El resultado ocupa unos 350 MB, por numpy, scipy, numba y Qt.
- En la primera detección, numba compila algunas funciones y la guarda en caché (en `%LOCALAPPDATA%`, `~/Library/Caches` o `~/.cache`, carpeta `BPMKeyTagger`). Por eso el primer análisis tarda unos segundos más.
