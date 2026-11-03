import multiprocessing


def main() -> int:
    # Import diferido: los procesos hijos (spawn) re-importan este módulo
    # y no necesitan cargar la interfaz gráfica.
    from bpmkey.app import run

    return run()


if __name__ == "__main__":
    multiprocessing.freeze_support()  # necesario si se empaqueta con PyInstaller
    raise SystemExit(main())
