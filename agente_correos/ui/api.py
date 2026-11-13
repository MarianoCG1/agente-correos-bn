"""Lo que la interfaz (pywebview) puede pedirle al programa.

Cada método público devuelve `{"ok": True, "datos": ...}` o `{"ok": False, "error": "texto"}` y nunca
lanza excepciones hacia JavaScript. No contiene reglas de negocio: las reglas viven en los módulos de
dominio y aquí solo se las llama y se da forma a la respuesta.
"""

from __future__ import annotations

import base64
import functools
import json
import logging
import platform
import re
import shutil
import sys
import tempfile
import threading
import uuid
import zipfile
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..configuracion import Configuracion
from ..correo.modelos import MensajeEncontrado
from ..correo.outlook_gateway import OutlookGateway
from ..correo.puerta import ErrorCorreo, PuertaCorreo
from ..correo.respaldo_red import RespaldoRed
from ..datos.auditoria_entrega import inferir_cambios
from ..datos.cronograma_loader import (COL_FILA, COL_OBJETIVO, COL_PUNTO, Cronograma, CronogramaError,
                                       CronogramaLoader, programas_activos)
from ..datos.directorio_agencias import DirectorioAgencias
from ..datos.generador_entrega import (CAMPOS_REPROGRAMABLES, CambiosEntrega, EntregaError, GeneradorEntrega,
                                       Reprogramacion, Suspension, nombre_sugerido_entrega, sugerir_suspendidos)
from ..datos.repositorio_agencias import AgenciaInvalida, ConflictoEdicion, RepositorioAgencias
from ..dominio.avisos import ClaveAviso, EstadoAviso, EventoAviso, TipoAviso, normalizar_agencia
from .. import __version__, institucional
from ..entorno import (carpeta_base, carpeta_datos_usuario, nombre_completo_windows, nombre_equipo,
                       ruta_desde_url_sharepoint, usuario_windows)
from ..historial.registro import RegistroEjecuciones
from ..reglas.fecha_objetivo import CalendarioHabil, DIAS, MESES
from ..reglas.preflight import PreflightValidator, Veredicto
from ..repositorio_configuracion import (RUTAS, ConflictoConfiguracion, RepositorioConfiguracion,
                                         estado_de_rutas)
from ..servicios.envio import EnvioService, SolicitudAviso
from ..usuario.firma import CID_LOGO, buscar_logo_en_firmas_outlook, construir_firma, logo_como_data_uri
from ..usuario.perfil import PerfilUsuario, separar_cargo_y_nombre
from .vigilancia import Vigilancia

log = logging.getLogger(__name__)

RAIZ_SUGERIDA = institucional.raiz_sugerida()   # la de data/institucional.json si existe; si no, una carpeta local
NOMBRE_BACKUP = "BACKUP_CORREOS"            # ya existe: es donde v1 dejaba los respaldos
NOMBRE_COMPARTIDA = "_PROGRAMA"              # única carpeta nueva, dentro de BACKUP_CORREOS
ESPERA_OUTLOOK = 10.0                        # segundos que se espera a Outlook al abrir el programa
ESPERA_RED = 12.0                            # segundos que se espera a SharePoint antes de avisar
MENSAJE_RED_LENTA = ("La carpeta de entregas no respondió a tiempo. Revise su conexión a SharePoint "
                     "y pulse «Actualizar».")
_LENTO = object()                            # marca: la red no respondió a tiempo

# Cómo se muestra cada estado en el tablero (códigos que conoce la interfaz)
_UI = {
    EstadoAviso.ENVIADO: "env", EstadoAviso.BORRADOR: "borr", EstadoAviso.ENVIANDO: "dec",
    EstadoAviso.ERROR: "dec", EstadoAviso.OMITIDO: "omit", EstadoAviso.BLOQUEADO: "bloq",
    EstadoAviso.DECISION: "dec", EstadoAviso.VENCIDO: "venc", EstadoAviso.HOY: "hoy",
    EstadoAviso.PENDIENTE: "pend", EstadoAviso.ANULADO: "omit",
}


class ErrorUsuario(Exception):
    """Mensaje pensado para mostrarse tal cual a la persona."""


def _api(fn):
    @functools.wraps(fn)
    def envoltura(self, *args, **kwargs):
        try:
            self._asegurar()
            return {"ok": True, "datos": fn(self, *args, **kwargs)}
        except (ErrorUsuario, AgenciaInvalida, ConflictoEdicion, ConflictoConfiguracion, EntregaError,
                CronogramaError, ErrorCorreo) as exc:
            return {"ok": False, "error": str(exc)}
        except Exception as exc:                       # nunca se propaga a JavaScript
            log.exception("Error en %s", fn.__name__)
            return {"ok": False, "error": f"Error inesperado: {exc}"}
    return envoltura


def _iso(d: Optional[date]) -> Optional[str]:
    return d.isoformat() if d else None


def _largo(d: date) -> str:
    return f"{DIAS[d.weekday()]} {d.day} de {MESES[d.month - 1]} de {d.year}"


class _Lote:
    def __init__(self, total: int, accion: str):
        self.id = uuid.uuid4().hex[:8]
        self.total, self.hechos, self.actual = total, 0, ""
        self.accion, self.resultados, self.terminado, self.error = accion, [], False, ""
        self.anulable_hasta: Optional[datetime] = None
        self.claves: Dict[str, ClaveAviso] = {}
        self.cancelar = False


class Api:
    def __init__(self, puerta: Optional[PuertaCorreo] = None, hoy: Callable[[], date] = date.today,
                 datos_locales: Optional[Path] = None, dialogos: Any = None, diferir_arranque: bool = False,
                 carpetas_agencias: Optional[List[Path]] = None, vigilancia: bool = False,
                 ahora: Callable[[], datetime] = datetime.now):
        self._puerta = puerta or OutlookGateway()
        self._hoy = hoy
        self._locales = Path(datos_locales) if datos_locales else carpeta_datos_usuario()
        self._dialogos = dialogos
        self._usuario = usuario_windows()
        self._lock = threading.RLock()
        self._lotes: Dict[str, _Lote] = {}
        self._crono_cache: Optional[tuple] = None
        self._inicios: Optional[tuple] = None
        self._svc: Optional[tuple] = None
        self._entregas: Dict[str, Path] = {}
        self._temp = Path(tempfile.gettempdir()) / f"agente_correos_{uuid.uuid4().hex[:6]}"
        self._carpetas_agencias = carpetas_agencias      # None = los lugares habituales de v1
        self._listo = False
        self._aviso_inicio = ""
        self._ventana = None
        self._vigilancia = Vigilancia(self, self._locales, ahora=ahora)
        self._vigilar = vigilancia                        # solo la aplicación real arranca el hilo; las pruebas lo llaman a mano
        if not diferir_arranque:
            self._asegurar()

    def _asegurar(self) -> None:
        """Abre la carpeta compartida la primera vez que se necesita, no al crear la Api: así la ventana
        aparece enseguida aunque la red tarde en responder."""
        if self._listo:
            return
        with self._lock:
            if not self._listo:
                self._preparar_almacenes()
                self._listo = True

    def set_window(self, ventana) -> None:
        self._ventana = ventana
        if self._dialogos is None:
            from .dialogos import Dialogos
            self._dialogos = Dialogos(ventana)

    # ------------------------------------------------------------------
    # Almacenes compartidos
    # ------------------------------------------------------------------
    def _local_json(self) -> Path:
        return self._locales / "local.json"

    def _leer_local(self) -> dict:
        try:
            return json.loads(self._local_json().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _preparar_almacenes(self) -> None:
        local = self._leer_local()
        elegida = str(local.get("carpeta_compartida") or "").strip()
        # Path("") es "." (la carpeta actual): sin ruta elegida se usa la de BACKUP_CORREOS, nunca la actual
        compartida = Path(elegida) if elegida else self._base_respaldo_inicial() / NOMBRE_COMPARTIDA
        self._compartida_ok = self._accesible(compartida)
        if not self._compartida_ok:
            compartida = self._locales / "compartida_local"          # solo lectura/borradores
            compartida.mkdir(parents=True, exist_ok=True)
        self._compartida = compartida
        self._cfg_repo = RepositorioConfiguracion(compartida / "config.json", self._usuario,
                                                  ruta_local=self._local_json())
        if not (compartida / "config.json").exists():
            self._sembrar_desde_v1()
        cfg = self._cfg_repo.configuracion
        self._ag_repo = RepositorioAgencias(compartida / "agencias.json", self._usuario,
                                            dominio=cfg.dominio_interno)
        # El registro vive dentro de la carpeta de cada campaña, junto a los respaldos que ya existen
        self._registro = RegistroEjecuciones(
            compartida / "registro", self._usuario, ruta_campana=self._carpeta_registro)
        self._sembrar_agencias()

    @staticmethod
    def _base_respaldo_inicial() -> Path:
        """BACKUP_CORREOS existente: el de v1 si su configuración lo indica, si no el de la carpeta de entrega."""
        for base in (carpeta_base().parent, Path.cwd(), Path.cwd().parent):
            ruta = base / "etv_config.json"
            if ruta.is_file():
                try:
                    destino = json.loads(ruta.read_text(encoding="utf-8")).get("backup_network_path", "")
                except (OSError, ValueError):
                    destino = ""
                destino = ruta_desde_url_sharepoint(destino) if destino else ""
                if destino and Path(destino).name.upper() == NOMBRE_BACKUP:
                    return Path(destino)
        return Path(RAIZ_SUGERIDA) / NOMBRE_BACKUP

    def _canonica(self) -> Path:
        return Path(self._cfg.respaldo_path) if self._cfg.respaldo_path else self._base_respaldo_inicial()

    def _carpeta_registro(self, campana: str) -> Path:
        anio = campana.strip().split(" ")[-1]
        return self._canonica() / (anio if anio.isdigit() else "sin-año") / campana / "_REGISTRO"

    @staticmethod
    def _limitado(fn: Callable[[], Any], espera: float, defecto: Any = None) -> Any:
        """Corre `fn` con un tope de tiempo. Una red lenta no debe dejar la ventana en «Conectando…»:
        si no responde a tiempo se devuelve `defecto` y la tarea sigue sola en segundo plano."""
        resultado: list = []

        def correr():
            try:
                resultado.append(fn())
            except Exception:
                log.debug("Operación de red fallida", exc_info=True)

        hilo = threading.Thread(target=correr, daemon=True)
        hilo.start()
        hilo.join(espera)
        return resultado[0] if resultado else defecto

    @staticmethod
    def _accesible(carpeta: Path, espera: float = 8.0) -> bool:
        """Crea la carpeta si falta y comprueba que responde. Una red caída no debe colgar el arranque."""
        resultado = []

        def probar():
            try:
                carpeta.mkdir(parents=True, exist_ok=True)
                resultado.append(carpeta.is_dir())
            except OSError:
                resultado.append(False)

        hilo = threading.Thread(target=probar, daemon=True)
        hilo.start()
        hilo.join(espera)
        return bool(resultado and resultado[0])

    def _sembrar_desde_v1(self) -> None:
        """Primera vez: toma rutas del etv_config.json de v1 si está cerca."""
        for base in (carpeta_base().parent, Path.cwd(), Path.cwd().parent):
            ruta = base / "etv_config.json"
            if ruta.is_file():
                try:
                    v1 = json.loads(ruta.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    return
                destino = ruta_desde_url_sharepoint(v1.get("backup_network_path", ""))
                respaldo = destino if Path(destino).name.upper() == NOMBRE_BACKUP else ""
                self._cfg_repo.guardar(Configuracion(**{**asdict(self._cfg), "respaldo_path": respaldo}))
                return

    @property
    def _cfg(self) -> Configuracion:
        # pywebview recorre los atributos de la Api al arrancar; esto no debe abrir la red ni fallar
        repo = getattr(self, "_cfg_repo", None)
        return repo.configuracion if repo is not None else Configuracion()

    def _raiz_entrega(self) -> Path:
        if self._cfg.cronograma_path:
            return Path(self._cfg.cronograma_path).parent
        return Path(RAIZ_SUGERIDA)

    def _respaldo(self) -> RespaldoRed:
        raiz = self._raiz_entrega()
        return RespaldoRed(self._canonica(), [raiz])

    def _perfil_path(self) -> Path:
        return self._compartida / "perfiles" / f"{self._usuario}.json"

    def _perfil(self) -> PerfilUsuario:
        return PerfilUsuario.cargar(self._perfil_path())

    def _cronograma(self) -> Cronograma:
        ruta = self._cfg.cronograma_path
        existe = self._limitado(lambda: bool(ruta) and Path(ruta).is_file(), ESPERA_RED)
        if existe is None:
            raise ErrorUsuario(MENSAJE_RED_LENTA)
        if not existe:
            hallada = self._limitado(self._buscar_entrega, ESPERA_RED, _LENTO)
            if hallada is _LENTO:
                raise ErrorUsuario(MENSAJE_RED_LENTA)
            if hallada is None:
                raise ErrorUsuario("No se encontró la entrega vigente. Genérela en «Preparar entrega» "
                                   "o indíquela en Configuración › Rutas.")
            ruta = str(hallada)
            try:                                              # queda registrado como cambio de configuración
                self._cfg_repo.guardar(Configuracion(**{**asdict(self._cfg), "cronograma_path": ruta}))
            except Exception:
                log.warning("No se pudo recordar la entrega detectada", exc_info=True)
        mtime = Path(ruta).stat().st_mtime
        with self._lock:
            if self._crono_cache and self._crono_cache[0] == (ruta, mtime):
                return self._crono_cache[1]
            c = CronogramaLoader().cargar(ruta, hoy=self._hoy())
            self._crono_cache = ((ruta, mtime), c)
            self._svc = None
            return c

    def _entrega_mas_reciente(self, actual: str) -> Optional[dict]:
        """Si en las carpetas conocidas hay una entrega de una campaña posterior a la que se usa, la devuelve."""
        from ..datos.entrega_vigente import clave_campana
        hallada = self._buscar_entrega()
        if hallada is None or Path(hallada) == Path(actual):
            return None
        a, b = clave_campana(Path(actual)), clave_campana(Path(hallada))
        if b is None or (a is not None and b <= a):
            return None
        return {"archivo": Path(hallada).name, "ruta": str(hallada)}

    def _entrega_vigente(self) -> str:
        """Ruta de la entrega configurada si existe; si no, la más reciente de las carpetas conocidas."""
        if self._cfg.cronograma_path and Path(self._cfg.cronograma_path).is_file():
            return self._cfg.cronograma_path
        hallada = self._buscar_entrega()
        return str(hallada) if hallada else ""

    def _buscar_entrega(self) -> Optional[Path]:
        """La entrega más reciente en las carpetas conocidas (la de entregas anteriores y la de la raíz)."""
        from ..datos.entrega_vigente import mas_reciente
        carpetas = []
        if self._cfg.carpeta_entrega:
            carpetas.append(Path(self._cfg.carpeta_entrega))
        if self._cfg.cronograma_path:
            carpetas.append(Path(self._cfg.cronograma_path).parent)
        carpetas.append(Path(RAIZ_SUGERIDA))
        for carpeta in carpetas:
            hallada = mas_reciente(carpeta)
            if hallada is not None:
                return hallada
        return None

    def _invalidar(self) -> None:
        with self._lock:
            self._crono_cache = self._inicios = self._svc = None

    def _logo(self, perfil: Optional[PerfilUsuario] = None) -> Optional[Path]:
        perfil = perfil or self._perfil()
        if perfil.logo_path and Path(perfil.logo_path).is_file():
            return Path(perfil.logo_path)
        return buscar_logo_en_firmas_outlook()

    def _servicio(self) -> EnvioService:
        crono = self._cronograma()
        perfil = self._perfil()
        clave = (crono.ruta, self._crono_cache[0][1], json.dumps(asdict(perfil), sort_keys=True),
                 json.dumps(asdict(self._cfg), sort_keys=True), self._ag_repo._version)
        with self._lock:
            if self._svc and self._svc[0] == clave:
                return self._svc[1]
            svc = EnvioService(self._cfg, crono, self._ag_repo.a_directorio(), self._registro, self._respaldo(),
                               self._puerta, perfil, logo=self._logo(perfil), hoy=self._hoy,
                               carpeta_temporal=self._temp)
            self._svc = (clave, svc)
            return svc

    # ------------------------------------------------------------------
    # Arranque
    # ------------------------------------------------------------------
    @_api
    def iniciar(self) -> dict:
        perfil = self._perfil()
        outlook = self._limitado(self._puerta.disponible, ESPERA_OUTLOOK, None)
        entrega = self._limitado(self._entrega_vigente, ESPERA_RED, None)
        if self._vigilar:
            self._vigilancia.iniciar()                     # revisar Enviados y, si se pidió, el envío automático
        red_lenta = entrega is None
        entrega = entrega or ""
        return {
            "red_lenta": red_lenta,
            "version": __version__,
            "equipo": nombre_equipo(),
            "entrega_archivo": Path(entrega).name if entrega else "",
            "agencias_n": len(self._ag_repo.agencias()),
            "usuario": self._usuario,
            "nombre": perfil.nombre or separar_cargo_y_nombre(nombre_completo_windows())[1] or self._usuario,
            "hoy": _iso(self._hoy()),
            "hoy_largo": _largo(self._hoy()),
            "outlook": bool(outlook),
            "outlook_lento": outlook is None,
            "compartida": str(self._compartida),
            "compartida_ok": self._compartida_ok,
            "perfil_completo": perfil.completo,
            "hay_entrega": bool(entrega),
            "hay_agencias": bool(self._ag_repo.agencias()),
            "minutos_anulacion": self._cfg.minutos_anulacion,
            "aviso": self._aviso_inicio,
        }

    # ------------------------------------------------------------------
    # Tablero
    # ------------------------------------------------------------------
    @_api
    def estado_campana(self, refrescar: bool = False) -> dict:
        if refrescar:
            self._invalidar()
        crono = self._cronograma()
        campana, hoy = crono.campana, self._hoy()
        cal = CalendarioHabil(self._cfg.feriados_como_fechas())
        fechas = crono.fechas_objetivo()
        objetivo = next((f for f in fechas if cal.fecha_de_aviso(f) >= hoy), None)
        directorio = self._ag_repo.a_directorio()
        eventos = self._registro.estados(campana.nombre)
        inicios = self._inicios_respaldo(crono)

        agencias = []
        for nombre in crono.agencias():
            filas = crono.filas(nombre)
            dest = directorio.buscar(nombre)
            bloqueo = self._motivo_bloqueo(dest)
            etvs = sorted({str(v).strip() for v in filas.get("ETV", []) if str(v).strip() and str(v) != "nan"})
            celdas = {}
            ev = eventos.get(ClaveAviso.crear(campana.nombre, nombre, TipoAviso.INICIO))
            respaldo_dt = inicios.get(nombre)
            if ev is not None:
                celdas["inicio"] = self._celda_evento(ev)
            elif bloqueo:
                celdas["inicio"] = {"estado": "bloq", "motivo": bloqueo}
            elif respaldo_dt is not None:
                celdas["inicio"] = {"estado": "env", "motivo": f"Respaldo del inicio del {respaldo_dt:%d/%m/%Y}"}
            elif objetivo is not None:                       # la campaña sigue en curso: el inicio sin registrar se puede preparar
                celdas["inicio"] = {"estado": "hoy", "motivo": "Debe prepararse: correo de inicio de la campaña"}
            else:
                celdas["inicio"] = {"estado": "venc", "motivo": "Sin registro del correo de inicio"}
            for f in sorted({d for d in filas[COL_OBJETIVO].dropna()}):
                ev = eventos.get(ClaveAviso.crear(campana.nombre, nombre, TipoAviso.RECORDATORIO, f))
                aviso = cal.fecha_de_aviso(f)
                if ev is not None:
                    celdas[_iso(f)] = self._celda_evento(ev)
                elif bloqueo:
                    celdas[_iso(f)] = {"estado": "bloq", "motivo": bloqueo}
                elif aviso == hoy or (f == objetivo and aviso < hoy):
                    celdas[_iso(f)] = {"estado": "hoy", "motivo": "Debe prepararse hoy"}
                elif aviso < hoy:
                    celdas[_iso(f)] = {"estado": "venc",
                                       "motivo": "La fecha pasó y no hay registro (puede haberse enviado antes de v2)"}
                else:
                    celdas[_iso(f)] = {"estado": "pend", "motivo": f"Se preparará el {aviso:%d/%m/%Y}"}
            agencias.append({
                "nombre": nombre, "etvs": etvs, "celdas": celdas,
                "para": list(dest.para) if dest else [], "cc": list(dest.cc) if dest else [],
                "sin_correo": bool(bloqueo), "motivo_bloqueo": bloqueo,
                "n_filas": int(len(filas)),
            })

        return {
            "campana": campana.nombre, "coherencia": crono.aviso_de_coherencia(),
            "archivo": Path(crono.ruta).name, "hoja": crono.hoja, "hay_agencias": bool(self._ag_repo.agencias()),
            "entrega_nueva": self._limitado(lambda: self._entrega_mas_reciente(str(crono.ruta)), ESPERA_RED, None),
            "hoy": _iso(hoy), "hoy_largo": _largo(hoy),
            "objetivo": _iso(objetivo),
            "objetivo_largo": _largo(objetivo) if objetivo else "",
            "aviso_objetivo": _iso(cal.fecha_de_aviso(objetivo)) if objetivo else None,
            "fechas": [{"fecha": _iso(f), "aviso": _iso(cal.fecha_de_aviso(f)),
                        "dia": DIAS[f.weekday()][:3].upper(), "d": f"{f.day:02d}/{f.month:02d}",
                        "largo": _largo(f)} for f in fechas],
            "agencias": agencias,
            "hay_respaldos": any(v is not None for v in inicios.values()),
        }

    @staticmethod
    def _celda_evento(ev: EventoAviso) -> dict:
        etiqueta = {EstadoAviso.ENVIADO: "Enviado", EstadoAviso.BORRADOR: "Borrador en Outlook",
                    EstadoAviso.ENVIANDO: "Envío en curso o interrumpido", EstadoAviso.ERROR: "Falló el intento"}
        cuando = f"{ev.creado_en:%d/%m/%Y %H:%M}" if ev.creado_en else ""
        motivo = f"{etiqueta.get(ev.estado, ev.estado.value)} por {ev.usuario} el {cuando}".strip()
        if ev.estado is EstadoAviso.ERROR and ev.detalle:
            motivo += f": {ev.detalle}"
        return {"estado": _UI.get(ev.estado, "pend"), "motivo": motivo}

    @staticmethod
    def _motivo_bloqueo(dest) -> str:
        if dest is None:
            return "La agencia no figura en la lista de correos"
        if dest.invalidos:
            return "Correo con formato inválido: " + ", ".join(dest.invalidos)
        if not dest.para:
            return "Sin correo registrado"
        return ""

    def _inicios_respaldo(self, crono: Cronograma) -> Dict[str, Optional[datetime]]:
        clave = (crono.ruta, crono.campana.nombre)
        with self._lock:
            if self._inicios and self._inicios[0] == clave:
                return self._inicios[1]
        datos = self._respaldo().inicios(crono.campana, crono.agencias())
        with self._lock:
            self._inicios = (clave, datos)
        return datos

    # ------------------------------------------------------------------
    # Revisión previa y vista previa
    # ------------------------------------------------------------------
    @_api
    def preparar_revision(self, tipo: str = "recordatorio", fecha: Optional[str] = None) -> dict:
        crono = self._cronograma()
        tipo_aviso = TipoAviso(tipo)
        objetivo = date.fromisoformat(fecha) if fecha else None
        validador = PreflightValidator(
            crono, self._ag_repo.a_directorio(), self._registro, self._cfg,
            respaldo_inicios=lambda agencias: self._respaldo().inicios(crono.campana, agencias))
        svc = self._servicio()
        filas = []
        for r in validador.evaluar(tipo_aviso, objetivo):
            hilo = {"estado": "no_aplica", "candidatos": []}
            veredicto, motivo = r.veredicto.value, r.motivo
            if tipo_aviso is TipoAviso.RECORDATORIO and r.veredicto is Veredicto.LISTA:
                try:
                    b = svc.buscar_hilo(r.agencia)
                    hilo = {"estado": b.estado, "candidatos": [self._cand(m) for m in b.candidatos],
                            "elegido": b.elegido.id if b.elegido else None}
                    if b.estado == "ambiguo":
                        veredicto, motivo = "revisar", f"Hay {len(b.candidatos)} hilos posibles: elija uno"
                except ErrorCorreo as exc:
                    hilo = {"estado": "sin_outlook", "candidatos": [], "error": str(exc)}
            filas.append({
                "agencia": r.agencia, "veredicto": veredicto, "motivo": motivo, "advertencias": r.advertencias,
                "n_filas": r.filas, "para": list(r.destinatarios.para), "cc": list(r.destinatarios.cc),
                "hilo": hilo,
            })
        return {"tipo": tipo, "fecha": fecha, "filas": filas,
                "minutos_anulacion": self._cfg.minutos_anulacion,
                "confirmacion_lectura": self._cfg.confirmacion_lectura}

    @staticmethod
    def _cand(m: MensajeEncontrado) -> dict:
        return {"id": m.id, "asunto": m.asunto,
                "enviado_en": m.enviado_en.strftime("%d/%m/%Y %H:%M") if m.enviado_en else "",
                "almacen": m.almacen}

    @_api
    def vista_previa(self, agencia: str, tipo: str = "recordatorio", fecha: Optional[str] = None,
                     id_hilo: Optional[str] = None) -> dict:
        svc = self._servicio()
        sol = SolicitudAviso(agencia, TipoAviso(tipo), date.fromisoformat(fecha) if fecha else None, id_hilo)
        correo = svc.preparar(sol, con_adjunto=False)
        html = correo.html
        if correo.logo is not None:
            html = html.replace(f"cid:{CID_LOGO}", logo_como_data_uri(correo.logo) or "")
        nombre_adjunto = Path(svc._crono.ruta).name
        n = len(svc._crono.filas(agencia))
        return {
            "asunto": correo.asunto, "modo": correo.modo, "advertencias": correo.advertencias,
            "para": correo.para, "cc": correo.cc,
            "html": '<html><body style="font-family:Calibri,Arial,sans-serif;font-size:11pt;margin:12px">'
                    + html + "</body></html>",
            "adjunto": {"nombre": nombre_adjunto, "filas": n},
            "firma": self._perfil().modo_firma,
        }

    # ------------------------------------------------------------------
    # Envío
    # ------------------------------------------------------------------
    @_api
    def confirmar_envio(self, selecciones: List[dict], accion: str = "enviar",
                        confirmar_lectura: Optional[bool] = None) -> dict:
        if accion not in ("enviar", "borrador"):
            raise ErrorUsuario("Acción no válida.")
        if accion == "enviar" and not self._compartida_ok:
            raise ErrorUsuario("Sin acceso a la carpeta compartida: no se puede enviar para no duplicar avisos. "
                               "Puede dejar borradores.")
        if not selecciones:
            raise ErrorUsuario("No hay avisos seleccionados.")
        solicitudes = [SolicitudAviso(s["agencia"], TipoAviso(s.get("tipo", "recordatorio")),
                                      date.fromisoformat(s["fecha"]) if s.get("fecha") else None, s.get("id_hilo"))
                       for s in selecciones]
        lectura = self._cfg.confirmacion_lectura if confirmar_lectura is None else bool(confirmar_lectura)
        lote = self._iniciar_lote(solicitudes, accion, lectura)
        return {"lote": lote.id, "total": lote.total}

    def _iniciar_lote(self, solicitudes: List[SolicitudAviso], accion: str, lectura: bool) -> _Lote:
        """Envía (o deja como borradores) en un hilo aparte; la pantalla consulta el avance con `progreso`.
        Lo usan tanto el envío con confirmación como el modo automático."""
        svc = self._servicio()
        lote = _Lote(len(solicitudes), accion)
        self._lotes[lote.id] = lote
        espera = self._cfg.minutos_anulacion if accion == "enviar" else 0
        campana = self._cronograma().campana.nombre

        def trabajo():
            try:
                def progreso(hechos, total, actual):
                    lote.hechos, lote.actual = hechos, actual
                res = svc.ejecutar(solicitudes, accion, espera, progreso=progreso,
                                   cancelar=lambda: lote.cancelar, confirmar_lectura=lectura)
                for r, s in zip(res, solicitudes):
                    lote.resultados.append({
                        "agencia": r.agencia, "estado": _UI.get(r.estado, "dec"), "estado_real": r.estado.value,
                        "detalle": r.detalle, "modo": r.modo, "para": r.para, "advertencias": r.advertencias})
                    if r.estado is EstadoAviso.ENVIADO:
                        lote.claves[r.agencia] = ClaveAviso.crear(campana, s.agencia, s.tipo, s.fecha_objetivo)
                if espera and any(r.estado is EstadoAviso.ENVIADO for r in res):
                    lote.anulable_hasta = datetime.now() + timedelta(minutes=espera)
                lote.hechos = lote.total
            except Exception as exc:
                log.exception("Lote %s", lote.id)
                lote.error = str(exc)
            finally:
                lote.terminado = True
                self._inicios = None            # el inicio recién respaldado cuenta en el tablero

        threading.Thread(target=trabajo, daemon=True).start()
        return lote

    @_api
    def progreso(self, lote_id: str) -> dict:
        lote = self._lotes.get(lote_id)
        if lote is None:
            raise ErrorUsuario("Lote desconocido.")
        return {"hechos": lote.hechos, "total": lote.total, "actual": lote.actual, "terminado": lote.terminado,
                "error": lote.error, "resultados": lote.resultados, "accion": lote.accion,
                "anulable_hasta": lote.anulable_hasta.isoformat() if lote.anulable_hasta else None}

    @_api
    def cancelar_envio(self, lote_id: str) -> bool:
        lote = self._lotes.get(lote_id)
        if lote:
            lote.cancelar = True
        return True

    @_api
    def anular_envio(self, lote_id: str) -> dict:
        lote = self._lotes.get(lote_id)
        if lote is None or lote.anulable_hasta is None:
            raise ErrorUsuario("Este envío no se puede anular.")
        if datetime.now() >= lote.anulable_hasta:
            raise ErrorUsuario("Pasó el tiempo de espera: los correos ya salieron.")
        svc = self._servicio()
        pares = []
        for r in lote.resultados:
            if r["estado_real"] == EstadoAviso.ENVIADO.value and r["agencia"] in lote.claves:
                solicitud = SolicitudAviso(r["agencia"], lote.claves[r["agencia"]].tipo,
                                           lote.claves[r["agencia"]].fecha_objetivo)
                correo = svc.preparar(solicitud, con_adjunto=False)
                pares.append((correo.asunto, r["para"] or "; ".join(correo.para)))
        anulados = self._puerta.anular(pares)
        self._registro.registrar_lote(
            EventoAviso(clave=c, estado=EstadoAviso.ANULADO, detalle="anulado por la persona")
            for c in lote.claves.values())
        campana = self._cronograma().campana
        for agencia, clave in lote.claves.items():
            if clave.tipo is TipoAviso.INICIO:               # el respaldo de un inicio anulado no debe contar como enviado
                self._respaldo().retirar(campana, agencia)
        self._inicios = None
        lote.anulable_hasta = None
        return {"anulados": anulados, "solicitados": len(pares)}

    @_api
    def enviarme_prueba(self, agencia: str, tipo: str = "recordatorio", fecha: Optional[str] = None,
                        id_hilo: Optional[str] = None) -> dict:
        propio = self._puerta.identidad().correo
        if not propio:
            raise ErrorUsuario("No se pudo obtener su correo desde Outlook.")
        sol = SolicitudAviso(agencia, TipoAviso(tipo), date.fromisoformat(fecha) if fecha else None, id_hilo)
        correo = self._servicio().preparar(sol, con_adjunto=True)
        self._puerta.crear(correo, "prueba", prueba_para=propio)
        return {"enviado_a": propio}

    # ------------------------------------------------------------------
    # Segundo plano: revisar Enviados y envío automático
    # ------------------------------------------------------------------
    def listo_para_vigilar(self) -> bool:
        return self._listo

    def _traer_al_frente(self) -> None:
        """Avisa a la persona que empezó una cuenta regresiva: sonido y ventana al frente."""
        try:
            import winsound
            winsound.MessageBeep(0x30)
        except Exception:
            pass
        try:
            if self._ventana is not None:
                self._ventana.restore()
        except Exception:
            log.debug("No se pudo traer la ventana al frente", exc_info=True)

    @_api
    def vigilancia_estado(self) -> dict:
        return self._vigilancia.estado()

    @_api
    def auto_ajustes_obtener(self) -> dict:
        return self._vigilancia.ajustes()

    @_api
    def auto_ajustes_guardar(self, valores: dict) -> dict:
        return self._vigilancia.guardar_ajustes(valores)

    @_api
    def auto_probar(self) -> dict:
        return self._vigilancia.probar_ahora()

    @_api
    def auto_cancelar(self) -> dict:
        return self._vigilancia.cancelar()

    @_api
    def auto_enviar_ya(self) -> dict:
        return self._vigilancia.enviar_ya()

    @_api
    def auto_descartar(self) -> dict:
        return self._vigilancia.descartar()

    @_api
    def enviados_revisar(self) -> dict:
        return self._vigilancia.revisar_ahora()

    # ------------------------------------------------------------------
    # Historial
    # ------------------------------------------------------------------
    @_api
    def historial(self, agencia: str = "", estado: str = "", texto: str = "") -> dict:
        crono_campana = self._cronograma().campana.nombre
        eventos = self._registro.eventos(crono_campana)
        q = texto.strip().upper()
        filas = []
        for ev in reversed(eventos):
            ui = _UI.get(ev.estado, "dec")
            if agencia and normalizar_agencia(ev.clave.agencia) != normalizar_agencia(agencia):
                continue
            if estado and ui != estado:
                continue
            if q and q not in f"{ev.clave.agencia} {ev.usuario} {ev.detalle} {ev.asunto}".upper():
                continue
            tipo = "Inicio de campaña" if ev.clave.tipo is TipoAviso.INICIO else \
                f"Recordatorio · pago {ev.clave.fecha_objetivo:%d/%m}"
            filas.append({"fecha": ev.creado_en.strftime("%d/%m/%Y") if ev.creado_en else "",
                          "hora": ev.creado_en.strftime("%H:%M") if ev.creado_en else "",
                          "usuario": ev.usuario, "agencia": ev.clave.agencia, "tipo": tipo, "estado": ui,
                          "detalle": ev.detalle or ev.estado.value})
        return {"campana": crono_campana, "total": len(eventos), "filas": filas}

    # ------------------------------------------------------------------
    # Preparar entrega
    # ------------------------------------------------------------------
    @_api
    def entrega_elegir_original(self) -> dict:
        ruta = self._dialogos.abrir_archivo(self._cfg.carpeta_original)
        if not ruta:
            return {"cancelado": True}
        return self._leer_original(Path(ruta))

    @_api
    def entrega_subir_original(self, nombre: str, base64_datos: str) -> dict:
        """Archivo arrastrado a la zona: el navegador no entrega la ruta, solo el contenido."""
        self._temp.mkdir(parents=True, exist_ok=True)
        destino = self._temp / f"original_{uuid.uuid4().hex[:6]}_{Path(nombre).name}"
        destino.write_bytes(base64.b64decode(base64_datos))
        return self._leer_original(destino, nombre_visible=Path(nombre).name)

    def _leer_original(self, ruta: Path, nombre_visible: str = "") -> dict:
        crono = CronogramaLoader().cargar(ruta, hoy=self._hoy())
        if COL_PUNTO not in crono.df.columns:
            raise ErrorUsuario("El archivo no tiene las columnas de código de pueblo y punto de pago.")
        token = uuid.uuid4().hex[:8]
        self._entregas[token] = ruta
        sugeridos = set(sugerir_suspendidos(ruta, crono))
        puntos = []
        for _, f in crono.df.iterrows():
            puntos.append({
                "clave": f[COL_PUNTO], "agencia": str(f["Agencia"]),
                "distrito": str(f.get("Distrito", "")), "punto": str(f.get("Punto_de_Pago", "")),
                "fecha": _iso(f[COL_OBJETIVO]) if f[COL_OBJETIVO] else None,
                "etv": str(f.get("ETV", "")) if str(f.get("ETV", "")) != "nan" else "",
                "sugerido": f[COL_PUNTO] in sugeridos})
        nombre = nombre_visible or ruta.name
        return {
            "token": token, "nombre": nombre, "campana": crono.campana.nombre,
            "coherencia": crono.aviso_de_coherencia(), "filas": len(puntos),
            "agencias": len(crono.agencias()), "puntos": puntos,
            "nombre_sugerido": nombre_sugerido_entrega(nombre),
            "carpeta_sugerida": self._cfg.carpeta_entrega or str(self._raiz_entrega()),
            "campos": list(CAMPOS_REPROGRAMABLES),
        }

    @_api
    def entrega_elegir_destino(self, nombre: str, carpeta: str = "") -> dict:
        ruta = self._dialogos.guardar_como(nombre, carpeta or self._cfg.carpeta_entrega)
        return {"ruta": ruta or "", "cancelado": not ruta}

    @_api
    def entrega_generar(self, token: str, destino: str, suspendidos: List[dict],
                        reprogramaciones: List[dict], usar_como_vigente: bool = True) -> dict:
        original = self._entregas.get(token)
        if original is None or not original.exists():
            raise ErrorUsuario("El original ya no está cargado. Vuelva a arrastrarlo.")
        cambios = CambiosEntrega(
            suspendidos=[Suspension(s["clave"], s.get("origen", "")) for s in suspendidos],
            reprogramaciones=[Reprogramacion(r["clave"], r["campo"], datetime.fromisoformat(r["valor"]),
                                             r.get("origen", "")) for r in reprogramaciones])
        resumen = GeneradorEntrega().generar(original, destino, cambios, usuario=self._usuario)
        nueva = Configuracion(**{**asdict(self._cfg), "carpeta_entrega": str(Path(destino).parent)})
        if usar_como_vigente:
            nueva.cronograma_path = str(destino)
        self._cfg_repo.guardar(nueva)
        self._invalidar()
        return {"destino": resumen.destino, "filas_original": resumen.filas_original,
                "filas_entrega": resumen.filas_entrega, "filas_quitadas": resumen.filas_quitadas,
                "importe_original": resumen.importe_p65_original, "importe_entrega": resumen.importe_p65_entrega,
                "columnas_quitadas": resumen.columnas_quitadas, "bitacora": resumen.bitacora,
                "vigente": usar_como_vigente}

    @_api
    def entrega_cambiar(self, ruta: str) -> dict:
        """Pasa a usar otra entrega (por ejemplo, la de la campaña nueva). Solo cambia este equipo."""
        if not Path(ruta).is_file():
            raise ErrorUsuario("Ese archivo ya no está disponible.")
        crono = CronogramaLoader().cargar(ruta, hoy=self._hoy())
        self._cfg_repo.guardar(Configuracion(**{**asdict(self._cfg), "cronograma_path": str(ruta)}))
        self._invalidar()
        return {"archivo": Path(ruta).name, "campana": crono.campana.nombre}

    @_api
    def entrega_usar_existente(self) -> dict:
        """Primer uso: la persona señala una entrega ya hecha (la comprueba leyéndola y la deja como vigente)."""
        inicio = self._cfg.carpeta_entrega or str(self._raiz_entrega())
        ruta = self._dialogos.abrir_archivo(inicio)
        if not ruta:
            return {"cancelado": True}
        crono = CronogramaLoader().cargar(ruta, hoy=self._hoy())            # lanza CronogramaError si no sirve
        valores = {**asdict(self._cfg), "cronograma_path": str(ruta)}
        if not self._cfg.carpeta_entrega:
            valores["carpeta_entrega"] = str(Path(ruta).parent)
        self._cfg_repo.guardar(Configuracion(**valores))
        self._invalidar()
        return {"cancelado": False, "archivo": Path(ruta).name, "campana": crono.campana.nombre}

    # ------------------------------------------------------------------
    # Soporte
    # ------------------------------------------------------------------
    @_api
    def diagnostico_exportar(self) -> dict:
        """Zip con el log y un resumen del equipo, para poder revisar un fallo sin acceso al equipo del banco.
        No incluye correos de agencias ni el contenido de los avisos."""
        nombre = f"Diagnostico_AgenteCorreos_{self._usuario}_{self._hoy().strftime('%Y%m%d')}.zip"
        destino = self._dialogos.guardar_como(nombre, str(Path.home() / "Desktop"), tipos=("Zip (*.zip)",))
        if not destino:
            return {"cancelado": True}
        estados = self._limitado(lambda: estado_de_rutas(self._cfg), 15.0, []) or []
        rutas = "\n".join(f"  {e.etiqueta}: {e.estado} · {e.valor or '(vacío)'}" for e in estados)
        resumen = "\n".join([
            f"Agente de Correos BN {__version__}",
            f"Generado: {datetime.now():%Y-%m-%d %H:%M:%S}",
            f"Usuario: {self._usuario} · Equipo: {nombre_equipo()}",
            f"Windows: {platform.platform()} · Python {platform.python_version()}"
            + (" (empaquetado)" if getattr(sys, "frozen", False) else ""),
            f"Outlook disponible: {self._limitado(self._puerta.disponible, ESPERA_OUTLOOK, 'sin respuesta')}",
            f"Carpeta compartida: {self._compartida} (accesible: {self._compartida_ok})",
            f"Agencias cargadas: {len(self._ag_repo.agencias())}",
            f"Minutos de anulación: {self._cfg.minutos_anulacion} · Confirmación de lectura: {self._cfg.confirmacion_lectura}",
            "Rutas:", rutas, ""])
        with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("resumen.txt", resumen)
            for archivo in ("agente_correos.log", "local.json"):
                ruta = self._locales / archivo
                if ruta.is_file():
                    z.write(ruta, archivo)
        return {"cancelado": False, "ruta": str(destino)}

    # ------------------------------------------------------------------
    # Agencias
    # ------------------------------------------------------------------
    @_api
    def agencias_listar(self, inactivas: bool = True) -> dict:
        self._ag_repo.cargar()
        return {"agencias": [asdict(a) for a in self._ag_repo.agencias(incluir_inactivas=inactivas)],
                "importable": bool(self._ruta_agencias_v1())}

    def _ruta_agencias_v1(self) -> Optional[Path]:
        """El Excel de agencias de v1, buscado en los mismos lugares que v1 (junto al programa, data/, docs/)."""
        candidatas = [Path(self._cfg.agencias_path)] if self._cfg.agencias_path else []
        bases = self._carpetas_agencias if self._carpetas_agencias is not None else [
            carpeta_base(), carpeta_base().parent, Path.cwd(), Path.cwd().parent, Path(sys.executable).parent]
        for base in bases:
            for carpeta in (base, base / "data", base / "docs"):
                # primero el JSON del programa; luego el Excel de v1 con su nombre o uno parecido
                candidatas += [carpeta / "agencias.json", carpeta / "agencias_correos.xlsx"]
                try:
                    candidatas += sorted(carpeta.glob("agencias*.xlsx"))
                except OSError:
                    pass
        return next((p for p in candidatas if p.is_file()), None)

    def _sembrar_agencias(self) -> None:
        """Primera vez: si todavía no hay agencias, convierte a JSON la lista que ya existe de v1."""
        try:
            if self._ag_repo.agencias(incluir_inactivas=True):
                return
            ruta = self._ruta_agencias_v1()
            if ruta is None:
                return
            r = self._ag_repo.importar(ruta)
            self._aviso_inicio = f"Se cargaron {len(r.agregadas)} agencias de la lista que ya existía."
            if r.agregadas and not self._cfg.agencias_path:
                self._cfg_repo.guardar(Configuracion(**{**asdict(self._cfg), "agencias_path": str(ruta)}))
        except Exception:
            log.warning("No se pudo cargar la lista de agencias de la versión anterior", exc_info=True)

    @_api
    def agencia_agregar(self, nombre: str, para: List[str], cc: List[str] = (), nota: str = "") -> dict:
        self._ag_repo.agregar(nombre, para, cc, nota)
        self._invalidar()
        return {"agencia": nombre}

    @_api
    def agencia_actualizar(self, nombre: str, para: List[str], cc: List[str], nota: str = "") -> dict:
        self._ag_repo.actualizar(nombre, para=para, cc=cc, nota=nota)
        self._invalidar()
        return {"agencia": nombre}

    @_api
    def agencia_eliminar(self, nombre: str) -> dict:
        self._ag_repo.eliminar(nombre)
        self._invalidar()
        return {"agencia": nombre}

    @_api
    def agencia_estado(self, nombre: str, activa: bool) -> dict:
        self._ag_repo.cambiar_estado(nombre, activa)
        self._invalidar()
        return {"agencia": nombre, "activa": activa}

    @_api
    def agencias_historial(self, nombre: str = "") -> dict:
        return {"cambios": [asdict(c) for c in reversed(self._ag_repo.historial(nombre or None))]}

    @_api
    def agencias_importar(self) -> dict:
        ruta = self._ruta_agencias_v1()
        if ruta is None and self._dialogos is not None:
            elegido = self._dialogos.abrir_archivo("")
            ruta = Path(elegido) if elegido else None
        if not ruta:
            raise ErrorUsuario("No se eligió el archivo con la lista de agencias.")
        r = self._ag_repo.importar(ruta)
        self._invalidar()
        return {"agregadas": r.agregadas, "actualizadas": r.actualizadas, "sin_cambio": r.sin_cambio,
                "rechazadas": r.rechazadas, "origen": str(ruta)}

    # ------------------------------------------------------------------
    # Configuración, rutas y perfil
    # ------------------------------------------------------------------
    @_api
    def config_obtener(self) -> dict:
        self._cfg_repo.cargar()
        return {"valores": asdict(self._cfg),
                "rutas": [asdict(e) for e in (self._limitado(lambda: estado_de_rutas(self._cfg), 15.0, []) or [])],
                "historial": [asdict(c) for c in reversed(self._cfg_repo.historial())][:200],
                "compartida": str(self._compartida), "compartida_ok": self._compartida_ok}

    @_api
    def config_guardar(self, valores: dict) -> dict:
        actual = asdict(self._cfg)
        nuevos = {k: v for k, v in valores.items() if k in actual}
        dominio = "@" + str(nuevos.get("dominio_interno", actual["dominio_interno"])).strip().lower().lstrip("@")
        for lista in ("copia_fija", "correos_excluidos"):
            if lista in nuevos:
                limpios = []
                for correo in nuevos[lista]:
                    c = str(correo).strip().lower()
                    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", c) or not c.endswith(dominio):
                        raise ErrorUsuario(f"«{correo}» no es un correo válido de {dominio}.")
                    if c not in limpios:
                        limpios.append(c)
                nuevos[lista] = limpios
        cambios = self._cfg_repo.guardar(Configuracion(**{**actual, **nuevos}))
        self._invalidar()
        return {"cambios": len(cambios), "reiniciar": any(c.campo == "carpeta_compartida" for c in cambios)}

    @_api
    def config_elegir_ruta(self, campo: str) -> dict:
        tipos = {c: t for c, _, t in RUTAS}
        if campo not in tipos:
            raise ErrorUsuario("Ruta desconocida.")
        actual = str(getattr(self._cfg, campo, "") or "")
        if tipos[campo] == "carpeta":
            ruta = self._dialogos.elegir_carpeta(actual)
        else:
            ruta = self._dialogos.abrir_archivo(actual)
        return {"ruta": ruta or "", "cancelado": not ruta}

    @_api
    def perfil_obtener(self) -> dict:
        perfil = self._perfil()
        detectado = "perfil"
        if not perfil.completo:
            ident = self._limitado(lambda: self._puerta.identidad() if self._puerta.disponible() else None,
                                   ESPERA_OUTLOOK, None)
            if ident and ident.nombre:
                perfil = PerfilUsuario.inicial(ident.nombre, ident.correo)
                perfil.cargo = ident.cargo or perfil.cargo
                detectado = "outlook"
            else:
                perfil = PerfilUsuario.inicial(nombre_completo_windows() or self._usuario)
                detectado = "windows"
        logo = self._logo(perfil)
        return {"perfil": asdict(perfil), "detectado_de": detectado, "logo": str(logo) if logo else "",
                "vista_logo": logo_como_data_uri(logo) if logo else None,
                "firma_html": construir_firma(perfil, logo_como_data_uri(logo) if logo else None)}

    @_api
    def perfil_guardar(self, valores: dict) -> dict:
        perfil = PerfilUsuario(**{k: v for k, v in valores.items() if k in PerfilUsuario.__dataclass_fields__})
        if not perfil.completo:
            raise ErrorUsuario("Falta el nombre.")
        perfil.guardar(self._perfil_path())
        self._invalidar()
        return {"guardado": True}

    @_api
    def firma_vista_previa(self, valores: dict) -> dict:
        perfil = PerfilUsuario(**{k: v for k, v in valores.items() if k in PerfilUsuario.__dataclass_fields__})
        logo = self._logo(perfil)
        return {"html": construir_firma(perfil, logo_como_data_uri(logo) if logo else None)}

    # ------------------------------------------------------------------
    def cerrar(self) -> None:
        self._vigilancia.detener()
        shutil.rmtree(self._temp, ignore_errors=True)
