"""Configuración con historial: cada cambio de ruta o de valor queda con quién y cuándo.

Hay dos niveles. La configuración compartida (jefatura, exclusiones, feriados, respaldo…) vive en la carpeta
compartida y la ven todas las personas. Las rutas que dependen del equipo (entrega vigente, carpetas de descarga,
carpeta compartida…) se guardan solo en ese equipo, en `local.json`, para que no afecten a nadie más.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from .configuracion import Configuracion
from .entorno import usuario_windows

# Rutas que pertenecen a cada equipo: nunca se comparten con otras personas
CAMPOS_LOCALES: Tuple[str, ...] = ("cronograma_path", "carpeta_original", "carpeta_entrega",
                                   "carpeta_compartida", "agencias_path")

# campo, etiqueta que ve la persona, tipo esperado
RUTAS: Tuple[Tuple[str, str, str], ...] = (
    ("cronograma_path", "Entrega vigente (alimenta los correos)", "archivo"),
    ("carpeta_original", "Carpeta del cronograma original", "carpeta"),
    ("carpeta_entrega", "Carpeta donde se guarda la entrega generada", "carpeta"),
    ("respaldo_path", "Respaldo de correos (BACKUP_CORREOS)", "carpeta"),
    ("carpeta_compartida", "Carpeta compartida del programa (registro, agencias, perfiles)", "carpeta"),
    ("agencias_path", "Excel de origen de la lista de agencias", "archivo"),
)


class ConflictoConfiguracion(RuntimeError):
    """Otra persona cambió la configuración mientras esta pantalla estaba abierta."""


@dataclass
class CambioConfig:
    cuando: str
    usuario: str
    campo: str
    antes: str
    despues: str


@dataclass
class EstadoRuta:
    campo: str
    etiqueta: str
    valor: str
    estado: str          # 'sin_configurar' | 'ok' | 'no_existe' | 'tipo_incorrecto'
    detalle: str = ""
    alcance: str = "compartida"      # 'equipo': solo este equipo · 'compartida': todas las personas

    @property
    def correcta(self) -> bool:
        return self.estado == "ok"


def _alcance(campo: str) -> str:
    return "equipo" if campo in CAMPOS_LOCALES else "compartida"


def estado_de_rutas(config: Configuracion) -> List[EstadoRuta]:
    """Revisa cada ruta configurada: si existe y si es del tipo esperado. No escribe nada."""
    salida = []
    for campo, etiqueta, tipo in RUTAS:
        valor = str(getattr(config, campo, "") or "").strip()
        if not valor:
            salida.append(EstadoRuta(campo, etiqueta, "", "sin_configurar", "Sin configurar", _alcance(campo)))
            continue
        try:
            existe = os.path.exists(valor)
            es_dir = os.path.isdir(valor)
        except OSError as exc:
            salida.append(EstadoRuta(campo, etiqueta, valor, "no_existe", f"No se pudo consultar: {exc}", _alcance(campo)))
            continue
        if not existe:
            salida.append(EstadoRuta(campo, etiqueta, valor, "no_existe", "No existe o no es accesible", _alcance(campo)))
        elif (tipo == "carpeta") != es_dir:
            salida.append(EstadoRuta(campo, etiqueta, valor, "tipo_incorrecto",
                                     f"Debe ser {'una carpeta' if tipo == 'carpeta' else 'un archivo'}", _alcance(campo)))
        else:
            salida.append(EstadoRuta(campo, etiqueta, valor, "ok", "Accesible", _alcance(campo)))
    return salida


class RepositorioConfiguracion:
    def __init__(self, ruta: str | Path, usuario: Optional[str] = None,
                 reloj: Callable[[], datetime] = datetime.now, ruta_local: Optional[str | Path] = None):
        self._ruta = Path(ruta)
        self._usuario = (usuario or usuario_windows()).strip()
        self._reloj = reloj
        self._ruta_local = Path(ruta_local) if ruta_local else None   # sin ella, todo es compartido
        self._version = 0
        self._config = Configuracion()                  # lo compartido, tal como está en la carpeta
        self._efectiva = self._config                   # compartido + lo propio de este equipo
        self._historial: List[CambioConfig] = []
        self._local: dict = {}
        self._historial_local: List[CambioConfig] = []
        self.cargar()

    @property
    def configuracion(self) -> Configuracion:
        return self._efectiva

    def historial(self, campo: Optional[str] = None) -> List[CambioConfig]:
        todos = sorted(self._historial + self._historial_local, key=lambda c: c.cuando)
        return [c for c in todos if campo is None or c.campo == campo]

    # ---- parte propia de este equipo ----------------------------------
    def _leer_local(self) -> Tuple[dict, List[CambioConfig]]:
        if self._ruta_local is None or not self._ruta_local.is_file():
            return {}, []
        try:
            crudo = json.loads(self._ruta_local.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}, []
        historial = []
        for c in crudo.get("historial", []):
            try:
                historial.append(CambioConfig(**c))
            except TypeError:
                continue
        return crudo, historial

    def _combinar(self, compartida: Configuracion) -> Configuracion:
        if self._ruta_local is None:
            return compartida
        valores = asdict(compartida)
        for campo in CAMPOS_LOCALES:                    # lo propio del equipo manda; lo compartido se ignora
            valores[campo] = str(self._local.get(campo, "") or "")
        return Configuracion(**valores)

    def _guardar_local(self, nueva: Configuracion) -> List[CambioConfig]:
        antes = {c: str(self._local.get(c, "") or "") for c in CAMPOS_LOCALES}
        despues = {c: str(getattr(nueva, c, "") or "") for c in CAMPOS_LOCALES}
        cambios = [CambioConfig(self._reloj().isoformat(timespec="seconds"), self._usuario, c, antes[c], despues[c])
                   for c in CAMPOS_LOCALES if antes[c] != despues[c]]
        if not cambios:
            return []
        self._local.update(despues)
        self._historial_local = (self._historial_local + cambios)[-200:]
        datos = dict(self._local)
        datos["historial"] = [asdict(c) for c in self._historial_local]
        self._ruta_local.parent.mkdir(parents=True, exist_ok=True)
        self._ruta_local.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
        return cambios

    # ------------------------------------------------------------------
    def cargar(self) -> Configuracion:
        self._version, self._config, self._historial = self._leer_disco()
        self._local, self._historial_local = self._leer_local()
        self._efectiva = self._combinar(self._config)
        return self._efectiva

    def _leer_disco(self):
        if not self._ruta.is_file():
            return 0, Configuracion(), []
        crudo = json.loads(self._ruta.read_text(encoding="utf-8"))
        valores = crudo.get("valores", crudo if "version" not in crudo else {})
        conocidos = {f.name for f in fields(Configuracion)}
        config = Configuracion(**{k: v for k, v in valores.items() if k in conocidos})
        historial = [CambioConfig(**c) for c in crudo.get("historial", [])]
        return int(crudo.get("version", 0)), config, historial

    def guardar(self, nueva: Configuracion) -> List[CambioConfig]:
        """Guarda y devuelve los campos que cambiaron. Lo propio del equipo se guarda aparte; lo compartido
        falla si otra persona guardó antes."""
        if self._ruta_local is None:
            return self._guardar_compartida(nueva)
        cambios_local = self._guardar_local(nueva)
        base = asdict(nueva)
        for campo in CAMPOS_LOCALES:                    # lo propio del equipo no viaja a la carpeta compartida
            base[campo] = getattr(self._config, campo)
        cambios = self._guardar_compartida(Configuracion(**base))
        self._efectiva = self._combinar(self._config)
        return cambios_local + cambios

    def _guardar_compartida(self, nueva: Configuracion) -> List[CambioConfig]:
        anterior = asdict(self._config)
        if all(valor == anterior.get(campo) for campo, valor in asdict(nueva).items()):
            return []                                   # nada que guardar: no se toca el archivo compartido
        version_disco, _, _ = self._leer_disco()
        if version_disco != self._version:
            raise ConflictoConfiguracion(
                "Otra persona cambió la configuración. Vuelva a cargarla antes de guardar.")

        anterior, cambios = asdict(self._config), []
        for campo, valor in asdict(nueva).items():
            if valor != anterior.get(campo):
                cambios.append(CambioConfig(self._reloj().isoformat(timespec="seconds"), self._usuario,
                                            campo, _texto(anterior.get(campo)), _texto(valor)))
        if not cambios:
            return []

        self._config, self._version = nueva, self._version + 1
        self._historial.extend(cambios)
        self._ruta.parent.mkdir(parents=True, exist_ok=True)
        self._ruta.write_text(json.dumps({
            "version": self._version,
            "valores": asdict(self._config),
            "historial": [asdict(c) for c in self._historial],
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        return cambios


def _texto(valor) -> str:
    return "; ".join(map(str, valor)) if isinstance(valor, (list, tuple)) else str(valor)
