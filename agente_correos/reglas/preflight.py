"""Revisión previa: decide, antes de tocar Outlook, qué avisos pueden salir y cuáles no."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from datetime import date, datetime
from enum import Enum
from typing import Callable, Dict, List, Optional

import pandas as pd

from ..configuracion import Configuracion
from ..datos.cronograma_loader import Cronograma
from ..datos.directorio_agencias import DirectorioAgencias, Destinatarios
from ..dominio.avisos import ClaveAviso, EstadoAviso, EventoAviso, TipoAviso, normalizar_agencia
from ..historial.registro import RegistroEjecuciones


log = logging.getLogger(__name__)


class Veredicto(str, Enum):
    LISTA = "lista"            # puede salir
    REVISAR = "revisar"        # requiere una decisión de la persona
    OMITIDA = "omitida"        # ya se avisó
    BLOQUEADA = "bloqueada"    # no puede salir hasta corregir el dato


@dataclass
class ResultadoPreflight:
    agencia: str
    tipo: TipoAviso
    fecha_objetivo: Optional[date]
    veredicto: Veredicto
    motivo: str = ""
    advertencias: List[str] = field(default_factory=list)
    filas: int = 0
    destinatarios: Destinatarios = field(default_factory=Destinatarios)

    @property
    def incluible(self) -> bool:
        return self.veredicto is Veredicto.LISTA

    @property
    def estado(self) -> EstadoAviso:
        return {
            Veredicto.LISTA: EstadoAviso.HOY,
            Veredicto.REVISAR: EstadoAviso.DECISION,
            Veredicto.OMITIDA: EstadoAviso.OMITIDO,
            Veredicto.BLOQUEADA: EstadoAviso.BLOQUEADO,
        }[self.veredicto]


class PreflightValidator:
    def __init__(self, cronograma: Cronograma, directorio: DirectorioAgencias,
                 registro: RegistroEjecuciones, config: Configuracion,
                 respaldo_inicios: Optional[Callable[[List[str]], Dict[str, Optional[datetime]]]] = None):
        self._crono = cronograma
        self._dir = directorio
        self._reg = registro
        self._cfg = config
        # cuándo se respaldó el inicio de cada agencia (v1, v2 u otra persona): evita repetir un inicio ya enviado
        self._respaldo_inicios = respaldo_inicios

    # ------------------------------------------------------------------
    def evaluar(self, tipo: TipoAviso, fecha_objetivo: Optional[date] = None,
                agencias: Optional[List[str]] = None) -> List[ResultadoPreflight]:
        """Un resultado por cada agencia que tiene filas para el aviso pedido."""
        if tipo is TipoAviso.RECORDATORIO and fecha_objetivo is None:
            raise ValueError("Un recordatorio necesita fecha objetivo.")

        if agencias is None:
            agencias = (self._crono.agencias_en_fecha(fecha_objetivo)
                        if tipo is TipoAviso.RECORDATORIO else self._crono.agencias())

        previos: Dict[ClaveAviso, EventoAviso] = self._reg.estados(self._crono.campana.nombre)
        inicios = self._inicios_respaldados(agencias) if tipo is TipoAviso.INICIO else {}
        salida = []
        for agencia in agencias:
            filas = self._crono.filas(agencia, fecha_objetivo if tipo is TipoAviso.RECORDATORIO else None)
            if filas.empty:
                continue
            salida.append(self._evaluar_agencia(agencia, tipo, fecha_objetivo, filas, previos, inicios))
        return salida

    # ------------------------------------------------------------------
    def _inicios_respaldados(self, agencias: List[str]) -> Dict[str, Optional[datetime]]:
        if self._respaldo_inicios is None:
            return {}
        try:
            return self._respaldo_inicios(list(agencias)) or {}
        except Exception:                                   # una red caída no debe impedir la revisión
            log.warning("No se pudo leer el respaldo de los inicios", exc_info=True)
            return {}

    def _evaluar_agencia(self, agencia: str, tipo: TipoAviso, fecha: Optional[date],
                         filas: pd.DataFrame, previos: Dict[ClaveAviso, EventoAviso],
                         inicios: Optional[Dict[str, Optional[datetime]]] = None) -> ResultadoPreflight:
        clave = ClaveAviso.crear(self._crono.campana.nombre, agencia, tipo, fecha)
        r = ResultadoPreflight(agencia=agencia, tipo=tipo, fecha_objetivo=clave.fecha_objetivo,
                               veredicto=Veredicto.LISTA, filas=len(filas))

        previo = previos.get(clave)
        avisos_previos: List[str] = []
        if previo is not None:
            if previo.estado is EstadoAviso.BORRADOR and previo.usuario == self._reg.usuario:
                # Si descartó su borrador, debe poder generarlo de nuevo: solo se frena el de otra persona
                r.motivo = f"Ya tiene un borrador suyo del {previo.creado_en:%d/%m/%Y %H:%M}: se generará otro"
                avisos_previos.append("Elimine el borrador anterior en Outlook para no tenerlo duplicado.")
            elif previo.estado is EstadoAviso.ENVIADO:
                return self._con(r, Veredicto.OMITIDA,
                                 f"Ya se envió el {previo.creado_en:%d/%m/%Y %H:%M} ({previo.usuario})")
            elif previo.estado is EstadoAviso.BORRADOR:
                return self._con(r, Veredicto.OMITIDA,
                                 f"Ya existe un borrador del {previo.creado_en:%d/%m/%Y %H:%M} ({previo.usuario})")
            elif previo.estado is EstadoAviso.ENVIANDO:
                return self._con(r, Veredicto.REVISAR,
                                 f"Un envío iniciado el {previo.creado_en:%d/%m/%Y %H:%M} ({previo.usuario}) "
                                 "no terminó. Verifique en Enviados antes de repetirlo")
        elif tipo is TipoAviso.INICIO and inicios and inicios.get(agencia) is not None:
            return self._con(r, Veredicto.OMITIDA,
                             f"Ya hay respaldo del inicio del {inicios[agencia]:%d/%m/%Y} (versión anterior u otra persona)")

        dest = self._dir.buscar(agencia)
        if dest is None:
            return self._con(r, Veredicto.BLOQUEADA, "La agencia no figura en la lista de correos")
        r.destinatarios = dest
        if dest.invalidos:
            return self._con(r, Veredicto.BLOQUEADA,
                             "Correo con formato inválido: " + ", ".join(dest.invalidos))
        if not dest.para:
            return self._con(r, Veredicto.BLOQUEADA, "Sin correo registrado en la lista de agencias")
        fuera = dest.fuera_de_dominio(self._cfg.dominio_interno)
        if fuera:
            return self._con(r, Veredicto.BLOQUEADA,
                             f"Destinatario fuera de {self._cfg.dominio_con_arroba()}: " + ", ".join(fuera))

        r.advertencias = avisos_previos + self._advertencias_de_datos(filas)
        return r

    @staticmethod
    def _con(r: ResultadoPreflight, veredicto: Veredicto, motivo: str) -> ResultadoPreflight:
        r.veredicto, r.motivo = veredicto, motivo
        return r

    @staticmethod
    def _advertencias_de_datos(filas: pd.DataFrame) -> List[str]:
        """Datos incompletos que no impiden el envío pero se verían en rojo en la tabla."""
        avisos = []
        if "P65_Importe" in filas.columns:
            vacios = int((pd.to_numeric(filas["P65_Importe"], errors="coerce").fillna(0) == 0).sum())
            if vacios:
                avisos.append(f"{vacios} fila(s) sin importe de Pensión 65")
        if "Fecha_Entrega" in filas.columns:
            vacios = int(filas["Fecha_Entrega"].isna().sum())
            if vacios:
                avisos.append(f"{vacios} fila(s) sin fecha de entrega")
        return avisos


def resumen(resultados: List[ResultadoPreflight]) -> Dict[str, int]:
    conteo = {v.value: 0 for v in Veredicto}
    for r in resultados:
        conteo[r.veredicto.value] += 1
    return conteo
