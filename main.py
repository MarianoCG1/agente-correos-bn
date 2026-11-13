"""Arranque de Agente de Correos BN v2.0.

    py main.py

Abre la interfaz (agente_correos/ui/web) en una ventana de pywebview y le entrega la `Api`.
"""

import ctypes
import logging
import sys
from pathlib import Path

from agente_correos import __version__
from agente_correos.entorno import carpeta_base, carpeta_datos_usuario


def _ruta_web() -> Path:
    """La carpeta de la interfaz, tanto desde el código como empaquetada con PyInstaller."""
    base = carpeta_base()
    for candidata in (base / "agente_correos" / "ui" / "web",
                      base / "_internal" / "agente_correos" / "ui" / "web"):
        if (candidata / "index.html").is_file():
            return candidata
    raise FileNotFoundError(f"No se encontró la interfaz en {base}")


def _configurar_log() -> None:
    carpeta = carpeta_datos_usuario()
    carpeta.mkdir(parents=True, exist_ok=True)
    manejadores = [logging.FileHandler(carpeta / "agente_correos.log", encoding="utf-8")]
    if sys.stderr is not None:                  # empaquetado sin consola no hay stderr
        manejadores.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=manejadores)


def _centrado(ancho: int, alto: int):
    try:
        u = ctypes.windll.user32
        return (u.GetSystemMetrics(0) - ancho) // 2, (u.GetSystemMetrics(1) - alto) // 2
    except Exception:
        return None, None


def main() -> int:
    _configurar_log()
    log = logging.getLogger("main")
    try:
        import webview
        from agente_correos.ui.api import Api
    except ImportError as exc:
        print(f"Falta una dependencia: {exc}\nInstale con: py -m pip install -r requirements-ui.txt")
        return 2

    api = Api(diferir_arranque=True, vigilancia=True)
    try:
        index = _ruta_web() / "index.html"
    except FileNotFoundError as exc:
        log.error("%s", exc)
        _avisar(str(exc))
        return 2

    # Se abre como file://: con una ruta simple pywebview levantaría su servidor local (bottle) y no hace falta.
    ventana = webview.create_window(
        f"Agente de Correos BN {__version__}", index.as_uri(), js_api=api, width=1280, height=800,
        min_size=(1100, 700), background_color="#F7F7F8", maximized=True)
    api.set_window(ventana)
    log.info("Iniciando la interfaz desde %s", index)
    webview.start()
    api.cerrar()
    return 0


def _avisar(texto: str) -> None:
    """Sin consola, un fallo al arrancar no se vería: se muestra en una ventana de Windows."""
    try:
        ctypes.windll.user32.MessageBoxW(0, texto, f"Agente de Correos BN {__version__}", 0x10)
    except Exception:
        print(texto)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        logging.getLogger("main").exception("El programa no pudo iniciar")
        _avisar("El programa no pudo iniciar.\n\nSi se repite, envíe el archivo de registro:\n"
                f"{carpeta_datos_usuario() / 'agente_correos.log'}")
        sys.exit(1)
