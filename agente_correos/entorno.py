"""Datos del equipo y del usuario de Windows. Lo único que toca el sistema operativo."""

from __future__ import annotations

import ctypes
import os
import socket
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

NOMBRE_APP = "AgenteCorreosBN"


def carpeta_base() -> Path:
    """Carpeta de la app: la del .exe si está empaquetada, la raíz del repositorio si corre desde código."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def carpeta_datos_usuario() -> Path:
    """Carpeta propia de cada usuario (perfil y firma). No se comparte entre PCs."""
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home()
    return base / NOMBRE_APP


def usuario_windows() -> str:
    return os.environ.get("USERNAME") or os.environ.get("USER") or "desconocido"


def nombre_equipo() -> str:
    try:
        return socket.gethostname()
    except OSError:
        return "desconocido"


def nombre_completo_windows() -> str:
    """Nombre para mostrar de la cuenta (el del directorio corporativo si hay dominio).

    Devuelve '' si no se puede obtener; quien llama usa entonces `usuario_windows()`.
    """
    try:
        buf = ctypes.create_unicode_buffer(256)
        tam = ctypes.c_ulong(len(buf))
        NAME_DISPLAY = 3
        if ctypes.windll.secur32.GetUserNameExW(NAME_DISPLAY, buf, ctypes.byref(tam)):
            return buf.value.strip()
    except (AttributeError, OSError):
        pass
    return ""


def ruta_desde_url_sharepoint(url: str) -> str:
    """Enlace de SharePoint → ruta que Windows puede abrir como carpeta.

    'https://srv/bn/operaciones/x' → '//srv@SSL/DavWWWRoot/bn/operaciones/x'.
    Lo que no es un enlace http(s) se devuelve sin cambios (ya es una ruta).
    """
    partes = urlsplit(url.strip())
    if partes.scheme not in ("http", "https") or not partes.netloc:
        return url
    sufijo = "@SSL" if partes.scheme == "https" else ""
    return f"//{partes.netloc}{sufijo}/DavWWWRoot{unquote(partes.path)}"
