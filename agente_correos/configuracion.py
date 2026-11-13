"""Ajustes de la aplicación: lo que en v1 estaba escrito dentro del código."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from datetime import date
from pathlib import Path
from typing import List

from . import institucional as _inst


@dataclass
class Configuracion:
    # Rutas (todas se pueden auditar y cambiar desde la configuración)
    cronograma_path: str = ""        # entrega vigente, la que alimenta los correos
    carpeta_original: str = ""       # última carpeta de donde se tomó el cronograma original
    carpeta_entrega: str = ""        # donde la persona eligió guardar la entrega generada
    respaldo_path: str = ""          # respaldo de correos (BACKUP_CORREOS)
    carpeta_compartida: str = ""     # registro de avisos, lista de agencias y perfiles
    agencias_path: str = ""          # Excel de origen de la lista de agencias (solo para importar)

    # Texto del correo de inicio ("Por encargo del Sr. …")
    por_encargo_nombre: str = _inst.valor("por_encargo_nombre", "Nombre y Apellidos")
    por_encargo_cargo: str = _inst.valor("por_encargo_cargo", "Jefe de Caja y Valores")

    # Destinatarios
    correos_excluidos: List[str] = field(default_factory=lambda: _inst.lista("correos_excluidos", ["jefe@bn.com.pe"]))
    dominio_interno: str = _inst.valor("dominio_interno", "bn.com.pe")
    # Copia fija: reciben copia (CC) del correo de inicio y de los recordatorios que no van como respuesta
    # al hilo (en una respuesta, la copia ya viene del correo de inicio). Se quitan los «excluidos».
    # De fábrica son direcciones de ejemplo; cada despliegue pone las suyas en data/institucional.json.
    copia_fija: List[str] = field(default_factory=lambda: _inst.lista("copia_fija", [
        "jefe@bn.com.pe", "integrante1@bn.com.pe", "integrante2@bn.com.pe", "integrante3@bn.com.pe"]))

    # Observaciones sobre la ETV Prosegur (distintas en inicio y recordatorio, como en v1)
    obs_prosegur_inicio: str = (
        "En el caso de la ETV PROSEGUR, se deberá imprimir y entregar las planillas, "
        "usando el aplicativo PSJN."
    )
    obs_prosegur_recordatorio: str = (
        "En el caso de la ETV PROSEGUR, se deberá imprimir y entregar las planillas."
    )

    # Calendario: feriados adicionales a sábado y domingo, en formato AAAA-MM-DD
    feriados: List[str] = field(default_factory=list)

    # Envío
    minutos_anulacion: int = 2       # ventana para anular un envío (entrega diferida de Outlook)
    confirmacion_lectura: bool = True   # valor inicial de «Pedir confirmación de lectura» al enviar

    # ------------------------------------------------------------------
    def feriados_como_fechas(self) -> List[date]:
        salida = []
        for texto in self.feriados:
            try:
                salida.append(date.fromisoformat(str(texto).strip()))
            except ValueError:
                continue
        return salida

    def dominio_con_arroba(self) -> str:
        return "@" + self.dominio_interno.strip().lower().lstrip("@")

    # ------------------------------------------------------------------
    @classmethod
    def cargar(cls, ruta: Path) -> "Configuracion":
        ruta = Path(ruta)
        if not ruta.exists():
            return cls()
        try:
            crudo = json.loads(ruta.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        conocidos = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in crudo.items() if k in conocidos})

    def guardar(self, ruta: Path) -> None:
        ruta = Path(ruta)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
