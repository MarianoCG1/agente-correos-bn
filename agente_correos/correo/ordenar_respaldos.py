"""Ordena los respaldos que v1 fue dejando en distintas carpetas, sin borrar nada.

v1 guardaba cada respaldo según la ruta que tuviera configurada ese día, y quedaron tres formas:

    <raíz>/<año>/<campaña>/<AGENCIA>/             <raíz>/<año>/<año>/<campaña>/<AGENCIA>/
    <raíz>/BACKUP_CORREOS/<año>/<campaña>/<AGENCIA>/   ← la que usa v2

Primero se arma un plan (solo lectura). Aplicarlo **copia** lo que falta en la carpeta de v2; las
carpetas anteriores quedan intactas, así nada deja de funcionar para quien siga usando v1.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_ANIO = re.compile(r"^(19|20)\d{2}$")
_CAMPANA = re.compile(r"^.+\s((?:19|20)\d{2})$")
ARCHIVOS = ("metadata.json", "cuerpo_principal.html")


@dataclass
class Movimiento:
    campana: str
    agencia: str
    origen: Path
    destino: Path
    accion: str                  # 'copiar' | 'ya_ordenado' | 'conflicto' | 'duplicado'
    motivo: str = ""
    origen_guardado: Optional[datetime] = None
    destino_guardado: Optional[datetime] = None


def _guardado(carpeta: Path) -> Optional[datetime]:
    ruta = carpeta / "metadata.json"
    if not ruta.is_file():
        return None
    try:
        return datetime.fromisoformat(json.loads(ruta.read_text(encoding="utf-8")).get("saved_at", ""))
    except (OSError, ValueError):
        return datetime.min


def _es_respaldo(carpeta: Path) -> bool:
    return carpeta.is_dir() and any((carpeta / a).is_file() for a in ARCHIVOS)


def _subdirs(carpeta: Path) -> List[Path]:
    try:
        return sorted(p for p in carpeta.iterdir() if p.is_dir())
    except OSError:
        return []


def _descubrir(raiz: Path, canonica: Path) -> List[Tuple[str, Path]]:
    """(campaña, carpeta de agencia) de todo respaldo encontrado fuera de la carpeta canónica."""
    encontrados: List[Tuple[str, Path]] = []
    for anio_dir in _subdirs(raiz):
        if not _ANIO.match(anio_dir.name):
            continue
        for nivel in _subdirs(anio_dir):
            candidatas = [nivel]
            if _ANIO.match(nivel.name):                # <año>/<año>/<campaña>
                candidatas = _subdirs(nivel)
            for campana_dir in candidatas:
                if not _CAMPANA.match(campana_dir.name):
                    continue
                for agencia_dir in _subdirs(campana_dir):
                    if _es_respaldo(agencia_dir):
                        encontrados.append((campana_dir.name, agencia_dir))
    return [(c, a) for c, a in encontrados if canonica not in a.parents]


def planificar(raiz: str | Path, canonica: Optional[str | Path] = None) -> List[Movimiento]:
    raiz = Path(raiz)
    canonica = Path(canonica) if canonica else raiz / "BACKUP_CORREOS"
    mejor: Dict[Tuple[str, str], Movimiento] = {}
    plan: List[Movimiento] = []

    for campana, origen in _descubrir(raiz, canonica):
        anio = _CAMPANA.match(campana).group(1)
        destino = canonica / anio / campana / origen.name
        g_origen, g_destino = _guardado(origen), _guardado(destino) if _es_respaldo(destino) else None
        mov = Movimiento(campana, origen.name, origen, destino, "copiar", "", g_origen, g_destino)

        if g_destino is not None or _es_respaldo(destino):
            mov.accion = "ya_ordenado"
            mov.motivo = "Ya existe en la carpeta de v2"
            if (g_origen or datetime.min) > (g_destino or datetime.min):
                mov.accion = "conflicto"
                mov.motivo = "El de origen es más reciente que el de v2: revíselo antes de reemplazar"

        clave = (campana, origen.name.upper())
        previo = mejor.get(clave)
        if previo is not None and previo.accion == "copiar" and mov.accion == "copiar":
            # La misma agencia aparece en dos carpetas antiguas: se copia solo la más reciente
            nuevo, viejo = (mov, previo) if (g_origen or datetime.min) > (previo.origen_guardado or datetime.min) \
                else (previo, mov)
            viejo.accion, viejo.motivo = "duplicado", "Hay una copia más reciente en otra carpeta"
            mejor[clave] = nuevo
        else:
            mejor.setdefault(clave, mov)
        plan.append(mov)
    return sorted(plan, key=lambda m: (m.campana, m.agencia, str(m.origen)))


def aplicar(plan: List[Movimiento], reemplazar_conflictos: bool = False) -> int:
    """Copia lo que falta. Nunca borra el origen. Devuelve cuántas carpetas de agencia copió."""
    copiadas = 0
    for m in plan:
        if m.accion == "copiar" or (m.accion == "conflicto" and reemplazar_conflictos):
            m.destino.mkdir(parents=True, exist_ok=True)
            for archivo in m.origen.iterdir():
                if archivo.is_file():
                    shutil.copy2(archivo, m.destino / archivo.name)
            copiadas += 1
    return copiadas


def resumen(plan: List[Movimiento]) -> Dict[str, int]:
    conteo = {"copiar": 0, "ya_ordenado": 0, "conflicto": 0, "duplicado": 0}
    for m in plan:
        conteo[m.accion] += 1
    return conteo
