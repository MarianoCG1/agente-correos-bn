"""Respaldo del correo de inicio de cada agencia, en la carpeta compartida.

Es lo que permite que otra persona continúe los recordatorios en el mismo hilo. Mantiene el
formato de v1 (`metadata.json`, `cuerpo_principal.html` y el Excel de la agencia) y lee las tres
ubicaciones que v1 fue dejando según la ruta que tuviera configurada:

    <respaldo>/<año>/<campaña>/<AGENCIA>/           ← la de v2 (BACKUP_CORREOS)
    <raíz>/<año>/<campaña>/<AGENCIA>/               ← v1 apuntando a la carpeta de entrega
    <raíz>/<año>/<año>/<campaña>/<AGENCIA>/         ← v1 apuntando a la carpeta del año
"""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from ..dominio.campana import Campana
from ..entorno import nombre_equipo, usuario_windows

log = logging.getLogger(__name__)

NOMBRE_METADATA = "metadata.json"
NOMBRE_CUERPO = "cuerpo_principal.html"


def nombre_carpeta_agencia(agencia: str) -> str:
    """Igual que v1: mayúsculas, espacios como guion bajo, sin / \\ :"""
    return (str(agencia).strip().upper().replace(" ", "_")
            .replace("/", "").replace("\\", "").replace(":", ""))


@dataclass
class Respaldo:
    agencia: str
    carpeta: Path
    metadata: Dict[str, str]
    html: str
    excel: Optional[Path]

    @property
    def enviado_por(self) -> str:
        return self.metadata.get("sent_by", "") or "Caja y Valores BN"

    @property
    def guardado_en(self) -> Optional[datetime]:
        try:
            return datetime.fromisoformat(self.metadata.get("saved_at", ""))
        except ValueError:
            return None

    @property
    def asunto(self) -> str:
        return self.metadata.get("subject", "")

    @property
    def para(self) -> List[str]:
        return [x.strip() for x in self.metadata.get("to", "").replace(",", ";").split(";") if x.strip()]


class RespaldoRed:
    def __init__(self, canonica: str | Path, raices_anteriores: Iterable[str | Path] = ()):
        self._canonica = Path(canonica)
        self._anteriores = [Path(r) for r in raices_anteriores]

    # ---- ubicaciones ------------------------------------------------------
    def _candidatas(self, campana: Campana, agencia: str) -> List[Path]:
        anio, nombre = str(campana.anio), campana.nombre
        carpeta = nombre_carpeta_agencia(agencia)
        rutas = [self._canonica / anio / nombre / carpeta]
        for raiz in self._anteriores:
            rutas.append(raiz / anio / nombre / carpeta)
            rutas.append(raiz / anio / anio / nombre / carpeta)
        return rutas

    def destino(self, campana: Campana, agencia: str) -> Path:
        return self._canonica / str(campana.anio) / campana.nombre / nombre_carpeta_agencia(agencia)

    # ---- lectura -----------------------------------------------------------
    def buscar(self, campana: Campana, agencia: str) -> Optional[Respaldo]:
        """La copia más reciente entre las ubicaciones conocidas."""
        mejores: List[Respaldo] = []
        for carpeta in self._candidatas(campana, agencia):
            r = self._leer(carpeta, agencia)
            if r is not None:
                mejores.append(r)
        if not mejores:
            return None
        return max(mejores, key=lambda r: r.guardado_en or datetime.min)

    @staticmethod
    def _leer(carpeta: Path, agencia: str) -> Optional[Respaldo]:
        if not carpeta.is_dir():
            return None
        metadata: Dict[str, str] = {}
        ruta_meta = carpeta / NOMBRE_METADATA
        if ruta_meta.is_file():
            try:
                metadata = json.loads(ruta_meta.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                log.warning("metadata ilegible en %s: %s", carpeta, exc)
        html = ""
        ruta_html = carpeta / NOMBRE_CUERPO
        if ruta_html.is_file():
            try:
                html = ruta_html.read_text(encoding="utf-8")
            except OSError as exc:
                log.warning("cuerpo ilegible en %s: %s", carpeta, exc)
        if not metadata and not html:
            return None
        excel = next((p for p in sorted(carpeta.glob("*.xlsx"))), None)
        return Respaldo(agencia, carpeta, metadata, html, excel)

    def retirar(self, campana: Campana, agencia: str, max_minutos: int = 60) -> bool:
        """Borra el respaldo que dejó un inicio que la persona anuló a tiempo. Solo toca la ubicación de v2 y
        solo si el respaldo es reciente: nunca un respaldo antiguo."""
        carpeta = self.destino(campana, agencia)
        r = self._leer(carpeta, agencia)
        if r is None or r.guardado_en is None:
            return False
        if (datetime.now() - r.guardado_en).total_seconds() > max_minutos * 60:
            return False
        for nombre in (NOMBRE_METADATA, NOMBRE_CUERPO, *[p.name for p in carpeta.glob("*.xlsx")]):
            try:
                (carpeta / nombre).unlink()
            except OSError as exc:
                log.warning("No se pudo retirar %s: %s", carpeta / nombre, exc)
        return True

    def listar(self, campana: Campana, agencias: Iterable[str]) -> Dict[str, Optional[Respaldo]]:
        return {a: self.buscar(campana, a) for a in agencias}

    def inicios(self, campana: Campana, agencias: Iterable[str], hilos: int = 8) -> Dict[str, Optional[datetime]]:
        """Cuándo se respaldó el inicio de cada agencia (o None). Solo lee `metadata.json`, en paralelo,
        porque cada lectura en SharePoint tarda ~0,2 s."""
        from concurrent.futures import ThreadPoolExecutor

        def una(agencia: str) -> Optional[datetime]:
            mejor: Optional[datetime] = None
            for carpeta in self._candidatas(campana, agencia):
                ruta = carpeta / NOMBRE_METADATA
                try:
                    if not ruta.is_file():
                        continue
                    cuando = datetime.fromisoformat(json.loads(ruta.read_text(encoding="utf-8")).get("saved_at", ""))
                except (OSError, ValueError):
                    cuando = datetime.min
                if mejor is None or cuando > mejor:
                    mejor = cuando
            return mejor

        agencias = list(agencias)
        with ThreadPoolExecutor(max_workers=max(1, hilos)) as pool:
            return dict(zip(agencias, pool.map(una, agencias)))

    # ---- escritura ---------------------------------------------------------
    def guardar(self, campana: Campana, agencia: str, asunto: str, para: List[str], cc: List[str],
                html: str, excel: Optional[Path] = None, nombre_excel: str = "",
                usuario: str = "", equipo: str = "") -> Path:
        carpeta = self.destino(campana, agencia)
        carpeta.mkdir(parents=True, exist_ok=True)
        (carpeta / NOMBRE_CUERPO).write_text(html, encoding="utf-8")
        nombre_excel = nombre_excel or (excel.name if excel else "")
        if excel is not None and excel.is_file():
            shutil.copyfile(excel, carpeta / nombre_excel)
        metadata = {
            "campaign": campana.nombre,
            "agency": agencia,
            "subject": asunto,
            "to": "; ".join(para),
            "cc": "; ".join(cc),
            "sent_by": usuario or usuario_windows(),
            "pc_name": equipo or nombre_equipo(),
            "saved_at": datetime.now().isoformat(),
            "excel_filename": nombre_excel,
        }
        (carpeta / NOMBRE_METADATA).write_text(json.dumps(metadata, ensure_ascii=False, indent=2),
                                               encoding="utf-8")
        return carpeta
