"""Firma de correo generada por la aplicación (réplica de la que cada persona arma en Outlook)."""

from __future__ import annotations

import base64
import html
import mimetypes
import os
from pathlib import Path
from typing import Optional

from .perfil import AVISO_CONFIDENCIAL, PerfilUsuario

CID_LOGO = "logo_firma"
_EXTENSIONES = {".png", ".jpg", ".jpeg", ".gif"}


def construir_firma(perfil: PerfilUsuario, logo_src: Optional[str] = None) -> str:
    """HTML de la firma. `logo_src` es 'cid:logo_firma' al enviar o un data URI en la vista previa."""
    e = html.escape
    lineas = [f"<b>{e(perfil.linea_titulo)}</b>"]
    if perfil.dependencia.strip():
        lineas.append(e(perfil.dependencia.strip()))

    contacto = f"Telf: {e(perfil.telefono.strip())}" if perfil.telefono.strip() else ""
    if perfil.anexo.strip():
        contacto += f" Anexo <b>{e(perfil.anexo.strip())}</b>"
    if contacto:
        lineas.append(contacto.strip())

    if perfil.direccion.strip():
        lineas.append(e(perfil.direccion.strip()))
    if perfil.mostrar_email and perfil.email.strip():
        correo = e(perfil.email.strip())
        lineas.append(f'E-mail: <b><a href="mailto:{correo}" style="color:#0563C1;">{correo}</a></b>')
    if perfil.aviso_confidencial:
        lineas.append(f'<span style="font-size:8pt;font-style:italic;">{e(AVISO_CONFIDENCIAL)}</span>')

    texto = "<br>".join(lineas)
    celda_logo = ""
    borde = ""
    if logo_src:
        celda_logo = (f'<td style="vertical-align:middle;padding-right:14px;">'
                      f'<img src="{e(logo_src, quote=True)}" alt="Banco de la Nación" '
                      f'style="height:70px;width:auto;"></td>')
        borde = "border-left:1px solid #000000;padding-left:14px;"

    return (
        '<table cellpadding="0" cellspacing="0" style="border-collapse:collapse;'
        'font-family:Calibri,Arial,sans-serif;font-size:11pt;color:#000000;"><tr>'
        f"{celda_logo}"
        f'<td style="vertical-align:top;{borde}">{texto}</td>'
        "</tr></table>"
    )


def logo_como_data_uri(ruta: str | Path) -> Optional[str]:
    """Para mostrar el logo en la vista previa de la interfaz."""
    ruta = Path(ruta)
    if not ruta.is_file():
        return None
    tipo = mimetypes.guess_type(ruta.name)[0] or "image/png"
    return f"data:{tipo};base64," + base64.b64encode(ruta.read_bytes()).decode("ascii")


def carpeta_firmas_outlook() -> Path:
    return Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Signatures"


def buscar_logo_en_firmas_outlook(carpeta: Optional[Path] = None) -> Optional[Path]:
    """Imagen más grande dentro de las firmas ya guardadas por Outlook (el logo de la persona).

    Permite reutilizar el logo oficial sin distribuirlo con la aplicación.
    """
    carpeta = carpeta or carpeta_firmas_outlook()
    if not carpeta.is_dir():
        return None
    candidatas = [p for p in carpeta.rglob("*")
                  if p.is_file() and p.suffix.lower() in _EXTENSIONES and p.parent.name.endswith("_files")]
    if not candidatas:
        return None
    return max(candidatas, key=lambda p: p.stat().st_size)
