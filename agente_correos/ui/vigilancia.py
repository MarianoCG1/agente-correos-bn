"""Lo que el programa hace por su cuenta mientras está abierto (no hace nada si está cerrado):

1. **Verificar Enviados**: cada pocos minutos lee la carpeta Enviados de la persona y anota en el registro
   compartido los avisos que salieron por fuera del programa. Solo lectura.
2. **Envío automático supervisado** (opcional, apagado de fábrica): a la hora elegida prepara los recordatorios
   de hoy y, tras una cuenta regresiva en pantalla que se puede cancelar, los envía. Solo sale lo que pasa la
   revisión sin advertencias; lo demás queda para revisarlo a mano. Los envíos conservan la ventana de anulación.

Los ajustes son de cada equipo (`automatico.json` en la carpeta de datos del usuario): la prueba de un equipo
no cambia el comportamiento de otro.
"""

from __future__ import annotations

import json
import logging
import queue
import re
import threading
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from ..dominio.avisos import EstadoAviso
from ..reglas.fecha_objetivo import CalendarioHabil
from ..servicios.enviados import ResultadoVerificacion, VerificadorEnviados
from ..servicios.envio import PlanAutomatico

log = logging.getLogger(__name__)

AJUSTES_INICIALES: Dict[str, Any] = {
    "activo": False,                 # envío automático
    "hora": "08:00",
    "accion": "enviar",              # 'enviar' o 'borrador' (ensayo: deja borradores en lugar de enviar)
    "cuenta_s": 60,                  # segundos de cuenta regresiva antes de enviar
    "verificar_enviados": True,
}
TOLERANCIA = timedelta(hours=3)      # si se abre el programa más tarde que esto, ya no se envía solo
CADA_REVISION = timedelta(minutes=3)
DIAS_PRIMERA_REVISION = 30
DIAS_REVISION = 3
ESPERA_REVISION = 120.0              # segundos máximos que se espera a Outlook en una revisión
REINTENTO = timedelta(seconds=60)

FASES_FINALES = ("hecho", "sin_nada", "cancelado")


class _Trabajador:
    """Un único hilo para todo lo que toca Outlook o la red desde la vigilancia: así se usa siempre la misma conexión COM
    y, si una llamada no responde, las demás no se acumulan detrás (se avisa y se reintenta en la próxima vuelta)."""

    def __init__(self):
        self._cola: "queue.Queue" = queue.Queue()
        self._hilo: Optional[threading.Thread] = None
        self._listo: Optional[threading.Event] = None

    def _bucle(self) -> None:
        while True:
            fn, caja, listo = self._cola.get()
            try:
                caja.append((True, fn()))
            except Exception as exc:
                log.warning("Tarea en segundo plano fallida: %s", exc)
                caja.append((False, str(exc) or exc.__class__.__name__))
            finally:
                listo.set()

    def correr(self, fn: Callable[[], Any], espera: float) -> Tuple[bool, Any]:
        """(True, valor) o (False, mensaje para la persona)."""
        if self._listo is not None and not self._listo.is_set():
            return False, "Outlook o la red siguen ocupados con la tarea anterior."
        if self._hilo is None:
            self._hilo = threading.Thread(target=self._bucle, name="vigilancia-outlook", daemon=True)
            self._hilo.start()
        caja: list = []
        self._listo = threading.Event()
        self._cola.put((fn, caja, self._listo))
        if not self._listo.wait(espera):
            return False, "Outlook o la red no respondieron a tiempo."
        return caja[0]


@dataclass
class _Auto:
    fase: str = "inactivo"
    mensaje: str = ""
    prueba: bool = False
    sale_a: Optional[datetime] = None
    plan: Optional[PlanAutomatico] = None
    accion: str = "enviar"
    lote: Optional[str] = None
    fecha_hecha: Optional[date] = None
    proximo_intento: Optional[datetime] = None
    iniciada_en: Optional[datetime] = None
    resumen: Dict[str, int] = field(default_factory=dict)


class Vigilancia:
    def __init__(self, api, carpeta: Path, ahora: Callable[[], datetime] = datetime.now):
        self._api = api
        self._ruta_ajustes = Path(carpeta) / "automatico.json"
        self._ruta_estado = Path(carpeta) / "automatico_estado.json"
        self._ahora = ahora
        self._lock = threading.RLock()            # protege los datos que lee la pantalla
        self._trabajo = threading.Lock()          # una sola tarea pesada a la vez (revisión, preparación)
        self._parar = threading.Event()
        self._trab = _Trabajador()
        self._hilo: Optional[threading.Thread] = None
        self._auto = _Auto(fecha_hecha=self._leer_fecha_hecha())
        # revisión de Enviados
        self._vistos: Set[str] = set()
        self._primera = True
        self._ultima_revision: Optional[datetime] = None
        self._ultimo_error = ""
        self._ultimo_resumen = ""
        self._nuevos_total = 0
        self._revisando = False

    # ---- ajustes ---------------------------------------------------------
    def ajustes(self) -> Dict[str, Any]:
        valores = dict(AJUSTES_INICIALES)
        try:
            crudo = json.loads(self._ruta_ajustes.read_text(encoding="utf-8"))
            valores.update({k: crudo[k] for k in AJUSTES_INICIALES if k in crudo})
        except (OSError, ValueError):
            pass
        return valores

    def guardar_ajustes(self, nuevos: Dict[str, Any]) -> Dict[str, Any]:
        from .api import ErrorUsuario                      # import tardío: api importa este módulo
        v = self.ajustes()
        v.update({k: nuevos[k] for k in AJUSTES_INICIALES if k in nuevos})
        v["activo"], v["verificar_enviados"] = bool(v["activo"]), bool(v["verificar_enviados"])
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", str(v["hora"])):
            raise ErrorUsuario("La hora debe tener el formato HH:MM, por ejemplo 08:00.")
        if v["accion"] not in ("enviar", "borrador"):
            raise ErrorUsuario("Elija si el modo automático envía o deja borradores.")
        try:
            v["cuenta_s"] = max(15, min(600, int(v["cuenta_s"])))
        except (TypeError, ValueError):
            raise ErrorUsuario("La cuenta regresiva debe ser un número de segundos.")
        self._ruta_ajustes.parent.mkdir(parents=True, exist_ok=True)
        self._ruta_ajustes.write_text(json.dumps(v, ensure_ascii=False, indent=1), encoding="utf-8")
        log.info("Ajustes del modo automático: %s", v)
        return v

    def _leer_fecha_hecha(self) -> Optional[date]:
        try:
            return date.fromisoformat(json.loads(self._ruta_estado.read_text(encoding="utf-8")).get("fecha", ""))
        except (OSError, ValueError, TypeError):
            return None

    def _marcar_hecha(self, dia: date, fase: str) -> None:
        self._auto.fecha_hecha = dia
        try:
            self._ruta_estado.parent.mkdir(parents=True, exist_ok=True)
            self._ruta_estado.write_text(json.dumps({"fecha": dia.isoformat(), "fase": fase}), encoding="utf-8")
        except OSError:
            log.warning("No se pudo guardar el estado del modo automático", exc_info=True)

    # ---- hilo ------------------------------------------------------------
    def iniciar(self) -> None:
        if self._hilo is not None:
            return
        self._hilo = threading.Thread(target=self._bucle, name="vigilancia", daemon=True)
        self._hilo.start()

    def detener(self) -> None:
        self._parar.set()

    def _bucle(self) -> None:
        while not self._parar.is_set():
            try:
                self.tick()
            except Exception:
                log.exception("Fallo inesperado en la vigilancia")
            self._parar.wait(2.0)

    # ---- una vuelta ------------------------------------------------------
    def tick(self, ahora: Optional[datetime] = None) -> None:
        ahora = ahora or self._ahora()
        if not self._api.listo_para_vigilar():
            return
        self._avanzar_envio(ahora)
        if not self._trabajo.acquire(blocking=False):
            return
        try:
            self._revisar_si_toca(ahora)
            self._programar(ahora)
        finally:
            self._trabajo.release()

    # ---- 1. Enviados -----------------------------------------------------
    def _revisar_si_toca(self, ahora: datetime) -> None:
        if not self.ajustes()["verificar_enviados"]:
            return
        if self._ultima_revision is not None and ahora - self._ultima_revision < CADA_REVISION:
            return
        self._revisar(ahora)

    def revisar_ahora(self) -> Dict[str, Any]:
        """La pidió la persona: devuelve qué encontró."""
        from .api import ErrorUsuario
        with self._trabajo:
            ok = self._revisar(self._ahora())
        if not ok:
            raise ErrorUsuario(self._ultimo_error or "No se pudo revisar la carpeta Enviados.")
        return {"resumen": self._ultimo_resumen, "nuevos_total": self._nuevos_total}

    def _revisar(self, ahora: datetime) -> bool:
        with self._lock:
            self._ultima_revision, self._revisando = ahora, True
        try:
            api = self._api
            dias = DIAS_PRIMERA_REVISION if self._primera else DIAS_REVISION
            ok, valor = self._trab.correr(lambda: self._revisar_en_hilo(ahora, dias), ESPERA_REVISION)
        finally:
            with self._lock:
                self._revisando = False
        with self._lock:
            if not ok:
                self._ultimo_error = str(valor)
                self._ultimo_resumen = ""
                return False
            res: ResultadoVerificacion = valor
            self._ultimo_error = ""
            self._primera = False
            self._vistos |= res.vistos
            if res.nuevos:
                self._nuevos_total += len(res.nuevos)
                api._inicios = None
                log.info("Enviados: se anotaron %d avisos enviados fuera del programa: %s",
                         len(res.nuevos), "; ".join(res.nuevos))
            partes = [f"{res.revisados} correos revisados"]
            if res.nuevos:
                partes.append(f"{len(res.nuevos)} avisos nuevos anotados")
            if res.sin_reconocer:
                partes.append(f"{res.sin_reconocer} sin fecha reconocible")
            self._ultimo_resumen = ", ".join(partes)
            return True

    def _revisar_en_hilo(self, ahora: datetime, dias: int) -> ResultadoVerificacion:
        api = self._api
        crono = api._cronograma()
        ver = VerificadorEnviados(api._puerta, api._registro, crono, ahora=lambda: ahora)
        return ver.revisar(ahora - timedelta(days=dias), self._vistos)

    # ---- 2. Envío automático ---------------------------------------------
    def _programar(self, ahora: datetime) -> None:
        aj = self.ajustes()
        a = self._auto
        if a.fase in ("cuenta", "enviando", "preparando"):
            return
        if not aj["activo"]:
            if a.fase in ("espera", "esperando_outlook", "inactivo", "error"):
                a.fase, a.mensaje = "inactivo", ""
            return
        hoy = ahora.date()
        if a.fase in FASES_FINALES and not a.prueba and a.fecha_hecha != hoy:
            a.fase, a.mensaje = "inactivo", ""              # el resultado de un día anterior ya no se muestra
        if a.fecha_hecha == hoy:
            return
        hora = datetime.combine(hoy, datetime.strptime(aj["hora"], "%H:%M").time())
        if ahora < hora:
            a.fase, a.mensaje = "espera", f"Hoy se prepararán los recordatorios a las {aj['hora']}."
            return
        if ahora > hora + TOLERANCIA:
            a.fase = "espera"
            a.mensaje = (f"La hora de hoy ({aj['hora']}) ya pasó y el programa no estaba abierto. "
                         "Use «Preparar avisos» o «Probar ahora».")
            return
        if a.proximo_intento and ahora < a.proximo_intento:
            return
        self._preparar(ahora, prueba=False)

    def probar_ahora(self) -> Dict[str, Any]:
        """Hace lo mismo que a la hora programada, ahora, sin importar la hora ni si ya corrió hoy."""
        from .api import ErrorUsuario
        if self._auto.fase in ("cuenta", "enviando", "preparando"):
            raise ErrorUsuario("Ya hay un envío automático en curso.")
        with self._trabajo:
            self._preparar(self._ahora(), prueba=True)
        return self.estado()["auto"]

    def _preparar(self, ahora: datetime, prueba: bool) -> None:
        api, a = self._api, self._auto
        aj = self.ajustes()
        a.prueba, a.accion, a.plan, a.lote, a.resumen = prueba, aj["accion"], None, None, {}
        a.fase, a.mensaje = "preparando", "Revisando Enviados y preparando los recordatorios de hoy…"
        try:
            if not api._compartida_ok:
                raise _EsperarPronto("Sin acceso a la carpeta compartida: el envío automático se pausa para no duplicar avisos.")
            if self._trab.correr(api._puerta.disponible, 15.0) != (True, True):
                raise _EsperarPronto("Outlook no está disponible. Ábralo para que el envío automático continúe.")
            if aj["verificar_enviados"]:
                self._revisar(ahora)
            ok, plan = self._trab.correr(lambda: self._plan_de_hoy(ahora), ESPERA_REVISION)
            if not ok:
                raise _EsperarPronto(str(plan))
        except _EsperarPronto as exc:
            a.fase, a.mensaje = "esperando_outlook", str(exc)
            a.proximo_intento = ahora + REINTENTO
            return
        except Exception as exc:                          # nunca debe quedar «preparando» para siempre
            log.exception("No se pudo preparar el envío automático")
            a.fase, a.mensaje = "esperando_outlook", f"No se pudo preparar el envío automático: {exc}"
            a.proximo_intento = ahora + REINTENTO
            return
        a.proximo_intento = None
        if plan is None:                                  # hoy no corresponde avisar ninguna fecha de pago
            self._terminar(ahora, "sin_nada", "Hoy no corresponde avisar ninguna fecha de pago.", prueba)
            return
        a.plan = plan
        if not plan.listos:
            motivo = "No hay recordatorios que enviar solos"
            motivo += f": {len(plan.descartados)} necesitan revisión manual." if plan.descartados else \
                ": todos los de hoy ya estaban avisados." if plan.ya_avisados else "."
            self._terminar(ahora, "sin_nada", motivo, prueba)
            return
        a.iniciada_en = ahora
        a.sale_a = ahora + timedelta(seconds=int(aj["cuenta_s"]))
        a.fase = "cuenta"
        a.mensaje = ""
        api._traer_al_frente()

    def _plan_de_hoy(self, ahora: datetime) -> Optional[PlanAutomatico]:
        api = self._api
        crono = api._cronograma()
        cal = CalendarioHabil(api._cfg.feriados_como_fechas())
        hoy = ahora.date()
        fechas = [f for f in crono.fechas_objetivo() if cal.fecha_de_aviso(f) == hoy]
        if not fechas:
            return None
        return api._servicio().plan_automatico(fechas)

    def _terminar(self, ahora: datetime, fase: str, mensaje: str, prueba: bool) -> None:
        a = self._auto
        a.fase, a.mensaje, a.sale_a = fase, mensaje, None
        if not prueba:
            self._marcar_hecha(ahora.date(), fase)

    def cancelar(self) -> Dict[str, Any]:
        from .api import ErrorUsuario
        a = self._auto
        if a.fase != "cuenta":
            raise ErrorUsuario("No hay una cuenta regresiva que cancelar.")
        self._terminar(self._ahora(), "cancelado", "Cancelado por la persona: no se envió nada.", a.prueba)
        log.info("Envío automático cancelado por la persona")
        return self.estado()["auto"]

    def descartar(self) -> Dict[str, Any]:
        """Oculta el resultado de un envío automático ya terminado."""
        a = self._auto
        if a.fase in FASES_FINALES:
            a.fase, a.mensaje, a.plan, a.lote = "inactivo", "", None, None
        return self.estado()["auto"]

    def enviar_ya(self) -> Dict[str, Any]:
        from .api import ErrorUsuario
        a = self._auto
        if a.fase != "cuenta":
            raise ErrorUsuario("No hay una cuenta regresiva en curso.")
        a.sale_a = self._ahora()
        return self.estado()["auto"]

    def _avanzar_envio(self, ahora: datetime) -> None:
        api, a = self._api, self._auto
        if a.fase == "cuenta" and a.sale_a is not None and ahora >= a.sale_a and a.plan is not None:
            try:
                lote = api._iniciar_lote(list(a.plan.listos), a.accion, api._cfg.confirmacion_lectura)
            except Exception as exc:
                log.exception("No se pudo iniciar el envío automático")
                self._terminar(ahora, "hecho", f"No se pudo iniciar el envío: {exc}", a.prueba)
                a.resumen = {"enviados": 0, "problemas": len(a.plan.listos)}
                return
            a.lote, a.fase, a.sale_a = lote.id, "enviando", None
            log.info("Envío automático iniciado: %d avisos (%s)", len(a.plan.listos), a.accion)
        elif a.fase == "enviando" and a.lote:
            lote = api._lotes.get(a.lote)
            if lote is not None and lote.terminado:
                bien = sum(1 for r in lote.resultados if r["estado_real"] in (EstadoAviso.ENVIADO.value,
                                                                              EstadoAviso.BORRADOR.value))
                otros = sum(1 for r in lote.resultados if r["estado_real"] in (EstadoAviso.OMITIDO.value,))
                a.resumen = {"enviados": bien, "omitidos": otros, "problemas": len(lote.resultados) - bien - otros}
                texto = (f"{bien} enviados" if a.accion == "enviar" else f"{bien} borradores creados")
                if lote.error:
                    texto += f" · Error: {lote.error}"
                self._terminar(ahora, "hecho", texto, a.prueba)
                log.info("Envío automático terminado: %s", a.resumen)

    # ---- lo que ve la pantalla --------------------------------------------
    def estado(self) -> Dict[str, Any]:
        ahora = self._ahora()
        aj = self.ajustes()
        a = self._auto
        lote = self._api._lotes.get(a.lote) if a.lote else None
        with self._lock:
            sync = {"activa": bool(aj["verificar_enviados"]),
                    "ultima": self._ultima_revision.isoformat(timespec="seconds") if self._ultima_revision else None,
                    "nuevos_total": self._nuevos_total, "error": self._ultimo_error,
                    "resumen": self._ultimo_resumen, "revisando": self._revisando}
        plan = a.plan
        return {
            "sync": sync,
            "auto": {
                "activo": bool(aj["activo"]), "hora": aj["hora"], "accion": a.accion if a.fase != "inactivo" else aj["accion"],
                "fase": a.fase, "mensaje": a.mensaje, "prueba": a.prueba,
                "sale_en": max(0, int((a.sale_a - ahora).total_seconds())) if a.sale_a else None,
                "listos": [{"agencia": s.agencia, "fecha": s.fecha_objetivo.isoformat()} for s in plan.listos] if plan else [],
                "descartados": [{"agencia": d.agencia, "fecha": d.fecha.isoformat(), "motivo": d.motivo}
                                for d in plan.descartados] if plan else [],
                "ya_avisados": plan.ya_avisados if plan else 0,
                "lote": a.lote,
                "avance": {"hechos": lote.hechos, "total": lote.total} if lote else None,
                "anulable_hasta": lote.anulable_hasta.isoformat() if lote and lote.anulable_hasta else None,
                "resumen": a.resumen, "fecha_hecha": a.fecha_hecha.isoformat() if a.fecha_hecha else None,
            },
        }


class _EsperarPronto(Exception):
    """Algo falta ahora (Outlook, red): se reintenta en un minuto sin marcar el día como hecho."""
