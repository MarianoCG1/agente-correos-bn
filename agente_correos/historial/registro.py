"""Registro de avisos: qué se preparó o envió, quién y cuándo.

Diseño medido sobre el SharePoint del banco (13/10/2026): crear un archivo tarda ~0,9 s, renombrar
~2,7 s y leer ~0,2 s. Por eso:

- Cada usuario escribe **un solo archivo por campaña** (`<campaña>/<usuario>.json`) y nadie más lo
  toca: no hay conflictos entre personas y para leer hay que abrir pocos archivos.
- Se escribe directo al nombre final (sin renombrar). Un lector que se cruce con una escritura a
  medias descarta ese archivo en esa lectura y lo recupera en la siguiente.
- Varios avisos se registran juntos (`registrar_lote`): una escritura por tanda, no por aviso.
- Antes de enviar se **reclama** el aviso: si otra persona lo reclamó primero, se cede.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

from ..dominio.avisos import ClaveAviso, EstadoAviso, EventoAviso
from ..entorno import usuario_windows

log = logging.getLogger(__name__)

_YA_AVISADO = (EstadoAviso.ENVIADO, EstadoAviso.BORRADOR, EstadoAviso.ENVIANDO)


@dataclass
class Reclamo:
    obtenidas: List[ClaveAviso] = field(default_factory=list)
    perdidas: Dict[ClaveAviso, EventoAviso] = field(default_factory=dict)   # aviso → evento de quien lo tiene


class RegistroEjecuciones:
    def __init__(self, carpeta: str | Path, usuario: Optional[str] = None,
                 reloj: Callable[[], datetime] = datetime.now, escritura_atomica: bool = False,
                 ruta_campana: Optional[Callable[[str], Path]] = None):
        """`ruta_campana(nombre)` permite guardar el registro dentro de la carpeta de la campaña que ya
        existe (p. ej. BACKUP_CORREOS/2026/<campaña>/_REGISTRO) en lugar de crear una carpeta aparte."""
        self._carpeta = Path(carpeta)
        self._ruta_campana = ruta_campana
        self._usuario = (usuario or usuario_windows()).strip()
        self._reloj = reloj
        self._atomica = escritura_atomica
        # La revisión de Enviados, un envío y la pantalla pueden escribir a la vez desde hilos distintos
        self._candado = threading.RLock()

    @property
    def usuario(self) -> str:
        return self._usuario

    # ---- escritura ------------------------------------------------------
    def registrar(self, evento: EventoAviso) -> EventoAviso:
        return self.registrar_lote([evento])[0]

    def registrar_lote(self, eventos: Iterable[EventoAviso]) -> List[EventoAviso]:
        """Agrega varios eventos con una sola escritura por campaña."""
        eventos = list(eventos)
        por_campana: Dict[str, List[EventoAviso]] = {}
        for ev in eventos:
            ev.creado_en = ev.creado_en or self._reloj()
            ev.id_evento = ev.id_evento or uuid.uuid4().hex[:10]
            ev.usuario = ev.usuario or self._usuario
            por_campana.setdefault(ev.clave.campana, []).append(ev)

        with self._candado:
            for campana, nuevos in por_campana.items():
                propios = self._leer_propios(campana)
                propios.extend(e.a_dict() for e in nuevos)
                self._escribir_propios(campana, propios)
        return eventos

    # ---- lectura --------------------------------------------------------
    def eventos(self, campana: str) -> List[EventoAviso]:
        """Eventos de todas las personas, del más antiguo al más reciente."""
        carpeta = self._dir_campana(campana)
        if not carpeta.is_dir():
            return []
        salida: List[EventoAviso] = []
        for archivo in sorted(carpeta.glob("*.json")):
            for crudo in self._leer_archivo(archivo):
                try:
                    salida.append(EventoAviso.desde_dict(crudo))
                except (KeyError, ValueError) as exc:
                    log.warning("Evento ilegible en %s: %s", archivo.name, exc)
        return sorted(salida, key=self._orden)

    def estados(self, campana: str) -> Dict[ClaveAviso, EventoAviso]:
        """Evento vigente de cada aviso: un envío confirmado prevalece; si no, el último."""
        vigente: Dict[ClaveAviso, EventoAviso] = {}
        for ev in self.eventos(campana):
            actual = vigente.get(ev.clave)
            if ev.estado is EstadoAviso.ANULADO:
                if actual is not None and actual.estado in (EstadoAviso.ENVIADO, EstadoAviso.ENVIANDO)                         and actual.usuario == ev.usuario:
                    del vigente[ev.clave]     # anulado a tiempo: vuelve a estar libre
                continue
            if actual is not None and actual.estado is EstadoAviso.ENVIADO:
                continue                      # el primer envío confirmado es el que cuenta
            vigente[ev.clave] = ev
        return vigente

    def estado_actual(self, clave: ClaveAviso) -> Optional[EventoAviso]:
        return self.estados(clave.campana).get(clave)

    def ya_avisado(self, clave: ClaveAviso) -> bool:
        actual = self.estado_actual(clave)
        return actual is not None and actual.estado in _YA_AVISADO

    # ---- exclusión entre personas ------------------------------------------
    def reclamar(self, claves: Iterable[ClaveAviso], asunto: str = "") -> Reclamo:
        """Se queda con los avisos que nadie más tiene antes de enviarlos.

        1. Los que ya figuran enviados, en borrador o reclamados por otra persona se devuelven como perdidos.
        2. Se registra el reclamo de los demás (una escritura).
        3. Se relee todo: si otra persona reclamó el mismo aviso antes (por hora y, en empate, por nombre),
           se cede y se retira el reclamo propio.
        """
        claves = list(dict.fromkeys(claves))
        resultado = Reclamo()
        libres: List[ClaveAviso] = []
        por_campana: Dict[str, Dict[ClaveAviso, EventoAviso]] = {}

        for clave in claves:
            estados = por_campana.setdefault(clave.campana, self.estados(clave.campana))
            actual = estados.get(clave)
            if actual and actual.estado in _YA_AVISADO and actual.usuario != self._usuario:
                resultado.perdidas[clave] = actual
            else:
                libres.append(clave)

        if not libres:
            return resultado
        self.registrar_lote(
            EventoAviso(clave=c, estado=EstadoAviso.ENVIANDO, asunto=asunto, detalle="reclamado")
            for c in libres)

        for campana in {c.campana for c in libres}:
            ganadores = self._ganadores_de_reclamo(campana)
            for clave in (c for c in libres if c.campana == campana):
                dueno = ganadores.get(clave)
                if dueno is None or dueno.usuario == self._usuario:
                    resultado.obtenidas.append(clave)
                else:
                    resultado.perdidas[clave] = dueno
                    self._retirar_reclamo(clave)
        return resultado

    def liberar(self, claves: Iterable[ClaveAviso]) -> None:
        """Retira los reclamos propios de avisos que finalmente no se enviaron (p. ej. hilo ambiguo)."""
        for clave in claves:
            self._retirar_reclamo(clave)

    def _ganadores_de_reclamo(self, campana: str) -> Dict[ClaveAviso, EventoAviso]:
        ganador: Dict[ClaveAviso, EventoAviso] = {}
        for ev in self.eventos(campana):
            if ev.estado not in (EstadoAviso.ENVIANDO, EstadoAviso.ENVIADO):
                continue
            actual = ganador.get(ev.clave)
            if actual is None or self._orden(ev) < self._orden(actual):
                ganador[ev.clave] = ev
        return ganador

    def _retirar_reclamo(self, clave: ClaveAviso) -> None:
        """Quita de mi propio archivo el reclamo que perdí (solo yo escribo ahí)."""
        with self._candado:
            propios = self._leer_propios(clave.campana)
            conservar = [e for e in propios
                         if not (e.get("estado") == EstadoAviso.ENVIANDO.value and e.get("detalle") == "reclamado"
                                 and e.get("agencia") == clave.agencia and e.get("tipo") == clave.tipo.value
                                 and e.get("fecha_objetivo") == (clave.fecha_objetivo.isoformat()
                                                                 if clave.fecha_objetivo else None))]
            if len(conservar) != len(propios):
                self._escribir_propios(clave.campana, conservar)

    # ---- archivos ---------------------------------------------------------
    def _ruta_propia(self, campana: str) -> Path:
        seguro = "".join(c if c.isalnum() or c in "-_." else "_" for c in self._usuario) or "usuario"
        return self._dir_campana(campana) / f"{seguro}.json"

    def _leer_propios(self, campana: str) -> List[dict]:
        return self._leer_archivo(self._ruta_propia(campana))

    @staticmethod
    def _leer_archivo(ruta: Path) -> List[dict]:
        if not ruta.is_file():
            return []
        try:
            datos = json.loads(ruta.read_text(encoding="utf-8"))
            return list(datos.get("eventos", []))
        except (OSError, ValueError) as exc:
            log.warning("Registro ilegible (se reintenta en la próxima lectura) %s: %s", ruta.name, exc)
            return []

    def _escribir_propios(self, campana: str, eventos: List[dict]) -> None:
        ruta = self._ruta_propia(campana)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        texto = json.dumps({"usuario": self._usuario, "eventos": eventos}, ensure_ascii=False, indent=1)
        if self._atomica:
            tmp = ruta.with_suffix(".tmp")
            tmp.write_text(texto, encoding="utf-8")
            os.replace(tmp, ruta)
        else:
            ruta.write_text(texto, encoding="utf-8")

    def _dir_campana(self, campana: str) -> Path:
        if self._ruta_campana is not None:
            return Path(self._ruta_campana(campana))
        return self._carpeta / self._subcarpeta(campana)

    @staticmethod
    def _orden(ev: EventoAviso):
        return (ev.creado_en or datetime.min, ev.usuario, ev.id_evento)

    @staticmethod
    def _subcarpeta(campana: str) -> str:
        seguro = "".join(c if c.isalnum() or c in " -_–" else "-" for c in campana)
        return " ".join(seguro.split()) or "sin-campana"
