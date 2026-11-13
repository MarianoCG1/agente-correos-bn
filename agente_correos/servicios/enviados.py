"""Revisa la carpeta Enviados de la persona y anota en el registro compartido los avisos que salieron por fuera
del programa (a mano desde Outlook, con la versión anterior o por otra persona desde su propio Outlook).

Es solo lectura sobre Outlook. Solo se consideran correos cuyo asunto es exactamente el de un aviso de la
campaña; una respuesta a una agencia («RE:», «RV:») o una prueba («[PRUEBA]») nunca cuenta como aviso.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Callable, Dict, List, Optional, Set, Tuple

from ..contenido.plantillas import asunto_inicio, asunto_recordatorio
from ..correo.buscador_hilo import _PREFIJOS, normalizar_asunto
from ..correo.puerta import PuertaCorreo
from ..datos.cronograma_loader import Cronograma
from ..dominio.avisos import ClaveAviso, EstadoAviso, EventoAviso, TipoAviso
from ..historial.registro import RegistroEjecuciones
from ..reglas.fecha_objetivo import MESES

log = logging.getLogger(__name__)

_NUMERO_MES = {m: i + 1 for i, m in enumerate(MESES)}
_NUMERO_MES["setiembre"] = 9
# «Se le recuerda que para el día de mañana 05 de noviembre de 2026, se debe programar…»
_FECHA_RECORDATORIO = re.compile(
    r"recuerda\s+que\s+para[^\d]{0,40}?(\d{1,2})\s+de\s+([a-záéíóúñ]+)\s+de\s+(\d{4})", re.IGNORECASE)
DETALLE = "Detectado en Enviados (enviado fuera del programa)"
_ESPERA_ENVIO_PROPIO = timedelta(minutes=10)      # un envío del programa tarda en quedar registrado


def fecha_del_recordatorio(texto: str) -> Optional[date]:
    """La fecha de pago a la que se refiere un recordatorio, leída del comienzo de su cuerpo."""
    m = _FECHA_RECORDATORIO.search(re.sub(r"\s+", " ", texto or ""))
    if not m:
        return None
    mes = _NUMERO_MES.get(m.group(2).lower())
    if not mes:
        return None
    try:
        return date(int(m.group(3)), mes, int(m.group(1)))
    except ValueError:
        return None


@dataclass
class ResultadoVerificacion:
    revisados: int = 0
    nuevos: List[str] = field(default_factory=list)       # «AG. UNO · recordatorio del 14/10»
    sin_reconocer: int = 0                                # parecían avisos pero no se pudo saber a qué fecha
    vistos: Set[str] = field(default_factory=set)         # ids ya resueltos: no se vuelven a leer


class VerificadorEnviados:
    def __init__(self, puerta: PuertaCorreo, registro: RegistroEjecuciones, cronograma: Cronograma,
                 ahora: Callable[[], datetime] = datetime.now):
        self._puerta, self._reg, self._crono, self._ahora = puerta, registro, cronograma, ahora

    def _asuntos(self) -> Dict[str, Tuple[str, TipoAviso]]:
        """Asunto normalizado → (agencia, tipo). El recordatorio puede salir en el hilo del inicio
        («RECORDATORIO: Programación de Fondos…») o como correo propio («RECORDATORIO: Entrega de Fondos…»)."""
        campana = self._crono.campana.nombre
        mapa: Dict[str, Tuple[str, TipoAviso]] = {}
        for agencia in self._crono.agencias():
            inicio = asunto_inicio(agencia, campana)
            mapa[normalizar_asunto(inicio)] = (agencia, TipoAviso.INICIO)
            mapa[normalizar_asunto("RECORDATORIO: " + inicio)] = (agencia, TipoAviso.RECORDATORIO)
            mapa[normalizar_asunto(asunto_recordatorio(agencia, campana))] = (agencia, TipoAviso.RECORDATORIO)
        return mapa

    def revisar(self, desde: datetime, vistos: Optional[Set[str]] = None) -> ResultadoVerificacion:
        campana = self._crono.campana.nombre
        vistos = set(vistos or ())
        resultado = ResultadoVerificacion()
        correos = self._puerta.enviados_desde(campana, desde, vistos)
        if not correos:
            return resultado
        mapa = self._asuntos()
        estados = self._reg.estados(campana)
        ahora = self._ahora()
        pendientes: List[EventoAviso] = []
        en_este_lote: Set[ClaveAviso] = set()

        for c in correos:
            resultado.revisados += 1
            if _PREFIJOS.match(c.asunto or ""):              # respuestas o reenvíos a una agencia: no son el aviso
                resultado.vistos.add(c.id)
                continue
            hallado = mapa.get(normalizar_asunto(c.asunto))
            if hallado is None:
                resultado.vistos.add(c.id)
                continue
            agencia, tipo = hallado
            fecha: Optional[date] = None
            if tipo is TipoAviso.RECORDATORIO:
                fecha = fecha_del_recordatorio(c.texto)
                if fecha is None or self._crono.filas(agencia, fecha).empty:
                    log.info("Recordatorio de %s sin fecha de pago reconocible (%s)", agencia, c.enviado_en)
                    resultado.sin_reconocer += 1
                    resultado.vistos.add(c.id)
                    continue
            clave = ClaveAviso.crear(campana, agencia, tipo, fecha)
            actual = estados.get(clave)
            if actual is not None and actual.estado is EstadoAviso.ENVIADO:
                resultado.vistos.add(c.id)                   # ya figura: lo envió el programa o ya se detectó
                continue
            if (actual is not None and actual.estado is EstadoAviso.ENVIANDO and actual.creado_en
                    and ahora - actual.creado_en < _ESPERA_ENVIO_PROPIO):
                continue                                     # el programa lo está enviando: se revisa en la próxima vuelta
            resultado.vistos.add(c.id)
            if clave in en_este_lote:
                continue
            en_este_lote.add(clave)
            pendientes.append(EventoAviso(clave=clave, estado=EstadoAviso.ENVIADO, asunto=c.asunto, para=c.para,
                                          detalle=DETALLE, id_outlook=c.id, creado_en=c.enviado_en))
            cuando = f"inicio" if tipo is TipoAviso.INICIO else f"recordatorio del {fecha:%d/%m}"
            resultado.nuevos.append(f"{agencia} · {cuando}")

        if pendientes:
            self._reg.registrar_lote(pendientes)
        return resultado
