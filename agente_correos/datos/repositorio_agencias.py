"""Lista de agencias y sus correos, editable desde el programa y con historial de cambios.

Vive en un archivo compartido (carpeta del programa en SharePoint) para que todos vean lo mismo.
Cada cambio queda registrado con quién, cuándo y qué valor tenía antes. Las agencias no se
borran: se desactivan, así el historial conserva su rastro.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from ..dominio.avisos import normalizar_agencia
from ..entorno import usuario_windows
from .directorio_agencias import DirectorioAgencias, Destinatarios, separar_correos

VERSION_FORMATO = 1


class AgenciaInvalida(ValueError):
    """Los datos de la agencia no son válidos; el mensaje se puede mostrar tal cual."""


class ConflictoEdicion(RuntimeError):
    """Otra persona modificó la lista mientras esta pantalla estaba abierta."""


@dataclass
class AgenciaRegistro:
    nombre: str
    para: List[str] = field(default_factory=list)
    cc: List[str] = field(default_factory=list)
    activa: bool = True
    nota: str = ""

    def como_destinatarios(self) -> Destinatarios:
        return Destinatarios(tuple(self.para), tuple(self.cc), ())


@dataclass
class CambioAgencia:
    cuando: str
    usuario: str
    agencia: str
    campo: str          # 'alta', 'para', 'cc', 'nota', 'activa'
    antes: str
    despues: str


@dataclass
class ResumenImportacion:
    agregadas: List[str] = field(default_factory=list)
    actualizadas: List[str] = field(default_factory=list)
    sin_cambio: List[str] = field(default_factory=list)
    rechazadas: Dict[str, str] = field(default_factory=dict)


class RepositorioAgencias:
    def __init__(self, ruta: str | Path, usuario: Optional[str] = None, dominio: str = "bn.com.pe",
                 reloj: Callable[[], datetime] = datetime.now):
        self._ruta = Path(ruta)
        self._usuario = (usuario or usuario_windows()).strip()
        self._dominio = "@" + dominio.strip().lower().lstrip("@")
        self._reloj = reloj
        self._version = 0
        self._agencias: Dict[str, AgenciaRegistro] = {}
        self._historial: List[CambioAgencia] = []
        self.cargar()

    # ---- lectura ------------------------------------------------------
    def cargar(self) -> None:
        self._version, self._agencias, self._historial = self._leer_disco()

    def _leer_disco(self) -> Tuple[int, Dict[str, AgenciaRegistro], List[CambioAgencia]]:
        if not self._ruta.is_file():
            return 0, {}, []
        crudo = json.loads(self._ruta.read_text(encoding="utf-8"))
        agencias = {}
        for a in crudo.get("agencias", []):
            reg = AgenciaRegistro(a["nombre"], list(a.get("para", [])), list(a.get("cc", [])),
                                  bool(a.get("activa", True)), a.get("nota", ""))
            agencias[normalizar_agencia(reg.nombre)] = reg
        historial = [CambioAgencia(**c) for c in crudo.get("historial", [])]
        return int(crudo.get("version", 0)), agencias, historial

    def agencias(self, incluir_inactivas: bool = False) -> List[AgenciaRegistro]:
        lista = [a for a in self._agencias.values() if incluir_inactivas or a.activa]
        return sorted(lista, key=lambda a: normalizar_agencia(a.nombre))

    def obtener(self, nombre: str) -> Optional[AgenciaRegistro]:
        return self._agencias.get(normalizar_agencia(nombre))

    def historial(self, agencia: Optional[str] = None) -> List[CambioAgencia]:
        if agencia is None:
            return list(self._historial)
        clave = normalizar_agencia(agencia)
        return [c for c in self._historial if normalizar_agencia(c.agencia) == clave]

    def a_directorio(self) -> DirectorioAgencias:
        """Vista que usa la revisión previa. Las agencias desactivadas no aparecen."""
        filas = {normalizar_agencia(a.nombre): (a.nombre, a.como_destinatarios()) for a in self.agencias()}
        return DirectorioAgencias(filas, [])

    # ---- edición --------------------------------------------------------
    def agregar(self, nombre: str, para: Iterable[str], cc: Iterable[str] = (), nota: str = "") -> AgenciaRegistro:
        nombre = " ".join(str(nombre).split())
        if not nombre:
            raise AgenciaInvalida("Falta el nombre de la agencia.")
        self._asegurar_vigente()
        reg = self._alta(nombre, para, cc, nota)
        self._guardar()
        return reg

    def _alta(self, nombre: str, para: Iterable[str], cc: Iterable[str] = (), nota: str = "") -> AgenciaRegistro:
        """Agrega en memoria y anota el cambio; quien llama decide cuándo guardar."""
        nombre = " ".join(str(nombre).split())
        if not nombre:
            raise AgenciaInvalida("Falta el nombre de la agencia.")
        if normalizar_agencia(nombre) in self._agencias:
            raise AgenciaInvalida(f"La agencia {nombre} ya existe.")
        reg = AgenciaRegistro(nombre, self._validar(para, "Para", obligatorio=True),
                              self._validar(cc, "CC"), True, nota.strip())
        self._agencias[normalizar_agencia(nombre)] = reg
        self._anotar(nombre, "alta", "", "; ".join(reg.para))
        return reg

    def actualizar(self, nombre: str, para: Optional[Iterable[str]] = None, cc: Optional[Iterable[str]] = None,
                   nota: Optional[str] = None) -> AgenciaRegistro:
        self._asegurar_vigente()
        reg = self._existente(nombre)
        if para is not None:
            nuevo = self._validar(para, "Para", obligatorio=True)
            if nuevo != reg.para:
                self._anotar(reg.nombre, "para", "; ".join(reg.para), "; ".join(nuevo))
                reg.para = nuevo
        if cc is not None:
            nuevo = self._validar(cc, "CC")
            if nuevo != reg.cc:
                self._anotar(reg.nombre, "cc", "; ".join(reg.cc), "; ".join(nuevo))
                reg.cc = nuevo
        if nota is not None and nota.strip() != reg.nota:
            self._anotar(reg.nombre, "nota", reg.nota, nota.strip())
            reg.nota = nota.strip()
        self._guardar()
        return reg

    def cambiar_estado(self, nombre: str, activa: bool) -> AgenciaRegistro:
        self._asegurar_vigente()
        reg = self._existente(nombre)
        if reg.activa != activa:
            self._anotar(reg.nombre, "activa", "sí" if reg.activa else "no", "sí" if activa else "no")
            reg.activa = activa
            self._guardar()
        return reg

    # ---- Excel ------------------------------------------------------------
    def importar_xlsx(self, ruta: str | Path, actualizar_existentes: bool = False) -> ResumenImportacion:
        """Carga agencias desde el Excel de v1 (agencias_correos.xlsx). Útil la primera vez."""
        origen = DirectorioAgencias.cargar(ruta)
        resumen = ResumenImportacion()
        self._asegurar_vigente()
        for nombre in origen.agencias():
            dest = origen.buscar(nombre)
            try:
                reg = self.obtener(nombre)
                if reg is None:
                    self._alta(nombre, dest.para, dest.cc)
                    resumen.agregadas.append(nombre)
                elif actualizar_existentes and (list(dest.para) != reg.para or list(dest.cc) != reg.cc):
                    nuevo_para, nuevo_cc = self._validar(dest.para, "Para", True), self._validar(dest.cc, "CC")
                    self._anotar(reg.nombre, "para", "; ".join(reg.para), "; ".join(nuevo_para))
                    reg.para, reg.cc = nuevo_para, nuevo_cc
                    resumen.actualizadas.append(nombre)
                else:
                    resumen.sin_cambio.append(nombre)
            except AgenciaInvalida as exc:
                resumen.rechazadas[nombre] = str(exc)
        if resumen.agregadas or resumen.actualizadas:
            self._guardar()                 # una sola escritura para toda la importación
        return resumen

    def importar_json(self, ruta: str | Path) -> ResumenImportacion:
        """Suma las agencias de otro archivo agencias.json (por ejemplo el que se prepara una vez para todos)."""
        origen = RepositorioAgencias(ruta, usuario=self._usuario, reloj=self._reloj)
        resumen = ResumenImportacion()
        self._asegurar_vigente()
        for a in origen.agencias(incluir_inactivas=True):
            try:
                if self.obtener(a.nombre) is None:
                    reg = self._alta(a.nombre, a.para, a.cc, a.nota)
                    reg.activa = a.activa
                    resumen.agregadas.append(a.nombre)
                else:
                    resumen.sin_cambio.append(a.nombre)
            except AgenciaInvalida as exc:
                resumen.rechazadas[a.nombre] = str(exc)
        if resumen.agregadas:
            self._guardar()
        return resumen

    def importar(self, ruta: str | Path) -> ResumenImportacion:
        """Excel de v1 (.xlsx) o archivo del programa (.json), según la extensión."""
        if str(ruta).lower().endswith(".json"):
            return self.importar_json(ruta)
        return self.importar_xlsx(ruta)

    def eliminar(self, nombre: str) -> None:
        """Quita la agencia de la lista. El historial conserva quién la quitó y con qué correos estaba."""
        self._asegurar_vigente()
        reg = self._existente(nombre)
        self._anotar(reg.nombre, "baja", "; ".join(reg.para), "")
        del self._agencias[normalizar_agencia(reg.nombre)]
        self._guardar()

    def exportar_xlsx(self, destino: str | Path) -> Path:
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Agencias"
        ws.append(["AGENCIAS", "JEFE DE PAGO", "ADMINISTRADOR", "ACTIVA", "NOTA"])
        for a in self.agencias(incluir_inactivas=True):
            ws.append([a.nombre, "; ".join(a.para), "; ".join(a.cc), "sí" if a.activa else "no", a.nota])
        destino = Path(destino)
        wb.save(destino)
        return destino

    # ---- internos ---------------------------------------------------------
    def _validar(self, correos: Iterable[str], rotulo: str, obligatorio: bool = False) -> List[str]:
        texto = "; ".join(correos) if not isinstance(correos, str) else correos
        validos, malos = separar_correos(texto)
        if malos:
            raise AgenciaInvalida(f"{rotulo}: correo con formato inválido ({', '.join(malos)}).")
        fuera = [c for c in validos if not c.endswith(self._dominio)]
        if fuera:
            raise AgenciaInvalida(f"{rotulo}: fuera de {self._dominio} ({', '.join(fuera)}).")
        if obligatorio and not validos:
            raise AgenciaInvalida(f"{rotulo}: debe tener al menos un correo.")
        return validos

    def _existente(self, nombre: str) -> AgenciaRegistro:
        reg = self.obtener(nombre)
        if reg is None:
            raise AgenciaInvalida(f"La agencia {nombre} no existe.")
        return reg

    def _anotar(self, agencia: str, campo: str, antes: str, despues: str) -> None:
        self._historial.append(CambioAgencia(self._reloj().isoformat(timespec="seconds"), self._usuario,
                                             agencia, campo, antes, despues))

    def _asegurar_vigente(self) -> None:
        version_disco, _, _ = self._leer_disco()
        if version_disco != self._version:
            raise ConflictoEdicion("Otra persona modificó la lista de agencias. Vuelva a cargarla antes de editar.")

    def _guardar(self) -> None:
        self._version += 1
        contenido = {
            "formato": VERSION_FORMATO,
            "version": self._version,
            "agencias": [asdict(a) for a in self._agencias.values()],
            "historial": [asdict(c) for c in self._historial],
        }
        self._ruta.parent.mkdir(parents=True, exist_ok=True)
        self._ruta.write_text(json.dumps(contenido, ensure_ascii=False, indent=1), encoding="utf-8")
