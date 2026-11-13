"""Encuentra la entrega más reciente en una carpeta, sin depender de un nombre de archivo concreto."""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Tuple

from ..dominio.campana import CODIGOS

_PATRON = re.compile(r"ENTREGA\s+DE\s+FONDOS\s+ETV\s+(" + "|".join(CODIGOS) + r")\s+((?:19|20)\d{2})",
                     re.IGNORECASE)
_ORDEN = list(CODIGOS)


def candidatas(carpeta: str | Path) -> List[Tuple[Path, int, int]]:
    """(archivo, año, orden de campaña) de cada entrega que hay en la carpeta."""
    carpeta = Path(carpeta)
    try:
        archivos = [p for p in carpeta.iterdir() if p.is_file()]
    except OSError:
        return []
    salida = []
    for p in archivos:
        if p.name.startswith("~$") or p.suffix.lower() not in (".xlsx", ".xlsm"):
            continue
        m = _PATRON.search(p.name)
        if m:
            salida.append((p, int(m.group(2)), _ORDEN.index(m.group(1).upper())))
    return salida


def clave_campana(archivo: str | Path) -> Optional[Tuple[int, int]]:
    """(año, orden de campaña) según el nombre del archivo, o None si no parece una entrega."""
    m = _PATRON.search(Path(archivo).name)
    return (int(m.group(2)), _ORDEN.index(m.group(1).upper())) if m else None


def mas_reciente(carpeta: str | Path) -> Optional[Path]:
    """La entrega de la campaña más nueva (año y luego orden bimestral; en empate, la modificada último)."""
    encontradas = candidatas(carpeta)
    if not encontradas:
        return None

    def clave(c):
        try:
            return (c[1], c[2], c[0].stat().st_mtime)
        except OSError:
            return (c[1], c[2], 0.0)

    return max(encontradas, key=clave)[0]
