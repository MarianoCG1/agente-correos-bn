"""Orquesta un envío de avisos: revisión previa → reclamo → armado → Outlook → registro → respaldo."""

from __future__ import annotations

import logging
import shutil
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable, Dict, List, Optional

from ..configuracion import Configuracion
from ..contenido.plantillas import asunto_inicio
from ..correo.buscador_hilo import ResultadoHilo, elegir_hilo
from ..correo.constructor import ConstructorCorreo
from ..correo.modelos import CorreoPreparado, MensajeEncontrado
from ..correo.puerta import ErrorCorreo, PuertaCorreo
from ..correo.respaldo_red import RespaldoRed
from ..datos.cronograma_loader import Cronograma
from ..datos.directorio_agencias import DirectorioAgencias, Destinatarios
from ..datos.excel_filtrador import ExcelFiltrador
from ..dominio.avisos import ClaveAviso, EstadoAviso, EventoAviso, TipoAviso
from ..entorno import nombre_equipo
from ..historial.registro import RegistroEjecuciones
from ..reglas.preflight import PreflightValidator, Veredicto
from ..usuario.perfil import PerfilUsuario

log = logging.getLogger(__name__)


@dataclass
class SolicitudAviso:
    agencia: str
    tipo: TipoAviso
    fecha_objetivo: Optional[date] = None
    id_hilo: Optional[str] = None            # el hilo que la persona eligió si había ambigüedad


@dataclass
class ResultadoAviso:
    agencia: str
    tipo: TipoAviso
    estado: EstadoAviso
    detalle: str = ""
    para: str = ""
    cc: str = ""
    id_outlook: str = ""
    modo: str = ""
    advertencias: List[str] = field(default_factory=list)


@dataclass
class Descartado:
    agencia: str
    fecha: date
    motivo: str


@dataclass
class PlanAutomatico:
    listos: List[SolicitudAviso] = field(default_factory=list)
    descartados: List[Descartado] = field(default_factory=list)
    ya_avisados: int = 0


class EnvioService:
    def __init__(self, config: Configuracion, cronograma: Cronograma, directorio: DirectorioAgencias,
                 registro: RegistroEjecuciones, respaldo: RespaldoRed, puerta: PuertaCorreo,
                 perfil: PerfilUsuario, logo: Optional[Path] = None,
                 hoy: Callable[[], date] = date.today, carpeta_temporal: Optional[Path] = None):
        self._cfg, self._crono, self._dir = config, cronograma, directorio
        self._reg, self._respaldo, self._puerta = registro, respaldo, puerta
        self._perfil, self._logo, self._hoy = perfil, logo, hoy
        self._constructor = ConstructorCorreo(config)
        self._validador = PreflightValidator(
            cronograma, directorio, registro, config,
            respaldo_inicios=lambda agencias: respaldo.inicios(cronograma.campana, agencias))
        self._temp = Path(carpeta_temporal or tempfile.gettempdir()) / f"etv_{uuid.uuid4().hex[:8]}"
        self._filtrador: Optional[ExcelFiltrador] = None

    # ------------------------------------------------------------------
    def limpiar(self) -> None:
        shutil.rmtree(self._temp, ignore_errors=True)

    def _adjunto_de(self, agencia: str) -> Path:
        if self._filtrador is None:
            self._filtrador = ExcelFiltrador(self._crono)
        destino = self._temp / Path(self._crono.ruta).name
        carpeta = self._temp / uuid.uuid4().hex[:6]
        carpeta.mkdir(parents=True, exist_ok=True)
        destino = carpeta / Path(self._crono.ruta).name
        self._filtrador.generar(agencia, destino)
        return destino

    # ------------------------------------------------------------------
    def buscar_hilo(self, agencia: str) -> ResultadoHilo:
        asunto = asunto_inicio(agencia, self._crono.campana.nombre)
        return elegir_hilo(self._puerta.buscar_enviados(asunto), asunto)

    def preparar(self, sol: SolicitudAviso, con_adjunto: bool = True) -> CorreoPreparado:
        """El correo exacto que saldría para este aviso. Lo usa la vista previa y el envío."""
        campana = self._crono.campana
        filas = self._crono.filas(sol.agencia, sol.fecha_objetivo if sol.tipo is TipoAviso.RECORDATORIO else None)
        if filas.empty:
            raise ErrorCorreo(f"{sol.agencia} no tiene filas para ese aviso.")
        dest = self._dir.buscar(sol.agencia) or Destinatarios()
        adjunto = self._adjunto_de(sol.agencia) if con_adjunto else None

        if sol.tipo is TipoAviso.INICIO:
            return self._constructor.inicio(sol.agencia, filas, campana, dest, self._perfil, self._logo, adjunto)

        hilo: Optional[MensajeEncontrado] = None
        busqueda = self.buscar_hilo(sol.agencia)
        if sol.id_hilo:
            hilo = next((m for m in busqueda.candidatos if m.id == sol.id_hilo), None)
            if hilo is None:
                raise ErrorCorreo("El hilo elegido ya no está disponible. Vuelva a elegirlo.")
        elif busqueda.estado == "unico":
            hilo = busqueda.elegido
        elif busqueda.estado == "ambiguo":
            raise ErrorCorreo(f"Hay {len(busqueda.candidatos)} hilos posibles para {sol.agencia}: elija uno.")

        respaldo = None if hilo else self._respaldo.buscar(campana, sol.agencia)
        return self._constructor.recordatorio(sol.agencia, filas, sol.fecha_objetivo, self._hoy(), campana,
                                              dest, self._perfil, self._logo, adjunto, hilo, respaldo)

    # ------------------------------------------------------------------
    def plan_automatico(self, fechas: List[date]) -> "PlanAutomatico":
        """Qué recordatorios pueden salir sin que una persona los revise uno por uno.

        Solo entran los que pasan la revisión previa sin ninguna advertencia y que se pueden responder en el
        hilo de la campaña (el original o el respaldo en red). Todo lo demás queda aparte, con su motivo,
        para revisarlo a mano."""
        plan = PlanAutomatico()
        for fecha in fechas:
            for r in self._validador.evaluar(TipoAviso.RECORDATORIO, fecha):
                motivo = self._motivo_para_revisar(r, fecha)
                if motivo == "ya":
                    plan.ya_avisados += 1
                elif motivo:
                    plan.descartados.append(Descartado(r.agencia, fecha, motivo))
                else:
                    plan.listos.append(SolicitudAviso(r.agencia, TipoAviso.RECORDATORIO, fecha))
        return plan

    def _motivo_para_revisar(self, r, fecha: date) -> str:
        """'' si el aviso puede salir solo; 'ya' si ya estaba avisado; si no, por qué hay que mirarlo a mano."""
        if r.veredicto is Veredicto.OMITIDA:
            return "ya"
        if r.veredicto is not Veredicto.LISTA:
            return r.motivo or "Requiere una decisión"
        avisos = [a for a in r.advertencias if not a.startswith("Elimine el borrador")]
        if avisos:
            return "Tiene advertencias: " + "; ".join(avisos)
        try:
            correo = self.preparar(SolicitudAviso(r.agencia, TipoAviso.RECORDATORIO, fecha), con_adjunto=False)
        except ErrorCorreo as exc:
            return str(exc)
        if correo.modo == "nuevo" or correo.advertencias:
            return "No se encontró el correo de inicio de la campaña para responderlo"
        return ""

    # ------------------------------------------------------------------
    def ejecutar(self, solicitudes: List[SolicitudAviso], accion: str = "enviar", diferir_minutos: int = 0,
                 progreso: Optional[Callable[[int, int, str], None]] = None,
                 cancelar: Optional[Callable[[], bool]] = None,
                 confirmar_lectura: bool = False) -> List[ResultadoAviso]:
        campana = self._crono.campana.nombre
        resultados: Dict[int, ResultadoAviso] = {}
        pendientes: List[int] = []

        # 1) Revisión previa
        for i, sol in enumerate(solicitudes):
            pf = self._validador.evaluar(sol.tipo, sol.fecha_objetivo, agencias=[sol.agencia])
            if not pf:
                resultados[i] = ResultadoAviso(sol.agencia, sol.tipo, EstadoAviso.ERROR, "Sin filas para ese aviso.")
                continue
            r = pf[0]
            if r.veredicto is Veredicto.LISTA:
                pendientes.append(i)
            else:
                estado = {Veredicto.OMITIDA: EstadoAviso.OMITIDO, Veredicto.BLOQUEADA: EstadoAviso.BLOQUEADO,
                          Veredicto.REVISAR: EstadoAviso.DECISION}[r.veredicto]
                resultados[i] = ResultadoAviso(sol.agencia, sol.tipo, estado, r.motivo)

        # 2) Reclamo: nadie más envía lo mismo
        claves = {i: ClaveAviso.crear(campana, solicitudes[i].agencia, solicitudes[i].tipo,
                                      solicitudes[i].fecha_objetivo) for i in pendientes}
        reclamo = self._reg.reclamar(claves.values())
        for i in list(pendientes):
            if claves[i] in reclamo.perdidas:
                dueno = reclamo.perdidas[claves[i]]
                resultados[i] = ResultadoAviso(
                    solicitudes[i].agencia, solicitudes[i].tipo, EstadoAviso.OMITIDO,
                    f"Ya lo tiene {dueno.usuario} ({dueno.estado.value})")
                pendientes.remove(i)

        # 3) Armado y envío, uno por uno
        estado_ok = EstadoAviso.ENVIADO if accion == "enviar" else EstadoAviso.BORRADOR
        for n, i in enumerate(pendientes, start=1):
            sol, clave = solicitudes[i], claves[i]
            if cancelar and cancelar():
                self._reg.liberar([claves[j] for j in pendientes[n - 1:]])
                for j in pendientes[n - 1:]:
                    resultados[j] = ResultadoAviso(solicitudes[j].agencia, solicitudes[j].tipo,
                                                   EstadoAviso.OMITIDO, "Cancelado por la persona")
                break
            if progreso:
                progreso(n - 1, len(pendientes), sol.agencia)
            try:
                correo = self.preparar(sol)
                correo.confirmar_lectura = confirmar_lectura
                rp = self._puerta.crear(correo, accion, diferir_minutos)
                self._reg.registrar(EventoAviso(
                    clave=clave, estado=estado_ok, asunto=correo.asunto, para=rp.para_final or "; ".join(correo.para),
                    cc=rp.cc_final or "; ".join(correo.cc), detalle=correo.modo, id_outlook=rp.id_outlook))
                res = ResultadoAviso(sol.agencia, sol.tipo, estado_ok, correo.modo, "; ".join(correo.para),
                                     "; ".join(correo.cc), rp.id_outlook, correo.modo,
                                     list(correo.advertencias) + list(rp.advertencias))
                if sol.tipo is TipoAviso.INICIO:
                    self._guardar_respaldo(correo, res)
                resultados[i] = res
            except ErrorCorreo as exc:
                resultados[i] = self._falla(clave, sol, str(exc), ambiguo="elija uno" in str(exc))
            except Exception as exc:           # una agencia con problema no detiene a las demás
                log.exception("Fallo al preparar %s", sol.agencia)
                resultados[i] = self._falla(clave, sol, f"Error inesperado: {exc}")
        if progreso:
            progreso(len(pendientes), len(pendientes), "")
        return [resultados[i] for i in range(len(solicitudes))]

    # ------------------------------------------------------------------
    def _falla(self, clave: ClaveAviso, sol: SolicitudAviso, detalle: str, ambiguo: bool = False) -> ResultadoAviso:
        if ambiguo:
            self._reg.liberar([clave])        # no se intentó nada: se devuelve el reclamo
            return ResultadoAviso(sol.agencia, sol.tipo, EstadoAviso.DECISION, detalle)
        self._reg.registrar(EventoAviso(clave=clave, estado=EstadoAviso.ERROR, detalle=detalle))
        return ResultadoAviso(sol.agencia, sol.tipo, EstadoAviso.ERROR, detalle)

    def _guardar_respaldo(self, correo: CorreoPreparado, res: ResultadoAviso) -> None:
        """El respaldo permite que otra persona continúe los recordatorios en el mismo hilo."""
        try:
            self._respaldo.guardar(
                self._crono.campana, correo.agencia, correo.asunto, correo.para, correo.cc, correo.html,
                excel=correo.adjuntos[0] if correo.adjuntos else None,
                usuario=self._reg.usuario, equipo=nombre_equipo())
        except Exception as exc:
            res.advertencias.append(f"No se pudo guardar el respaldo en la red: {exc}")
