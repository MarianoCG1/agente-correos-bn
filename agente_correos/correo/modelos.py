"""Tipos que comparten las piezas de correo. No dependen de Outlook."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional

from ..dominio.avisos import TipoAviso


@dataclass
class MensajeEncontrado:
    """Un correo localizado en Outlook (solo lo necesario para decidir si es el hilo)."""
    id: str
    asunto: str
    para: str = ""
    enviado_en: Optional[datetime] = None
    es_enviado: bool = True          # vino de la carpeta Enviados (no de Entrada)
    almacen: str = ""


@dataclass
class CorreoEnviado:
    """Un correo de la carpeta Enviados de la persona, con lo mínimo para saber qué aviso fue."""
    id: str
    asunto: str
    enviado_en: Optional[datetime] = None
    para: str = ""
    texto: str = ""                  # comienzo del cuerpo en texto plano; solo se lee en los recordatorios


@dataclass
class CorreoPreparado:
    agencia: str
    tipo: TipoAviso
    asunto: str
    para: List[str]
    cc: List[str]
    html: str                                   # cuerpo + firma (+ cita si se reconstruye el hilo)
    modo: str                                   # 'nuevo' | 'respuesta' | 'reconstruido'
    fecha_objetivo: Optional[date] = None
    adjuntos: List[Path] = field(default_factory=list)
    logo: Optional[Path] = None                 # se incrusta como imagen en la firma
    firma_outlook: bool = False                 # usar la firma predeterminada de Outlook, no la de la app
    id_hilo: Optional[str] = None               # solo en modo 'respuesta'
    excluir: List[str] = field(default_factory=list)   # correos que se quitan de una respuesta
    dominio: str = ""                                  # lo externo se quita de una respuesta
    advertencias: List[str] = field(default_factory=list)
    confirmar_lectura: bool = False                    # Outlook pide al destinatario el acuse de lectura


@dataclass
class ResultadoPuerta:
    id_outlook: str
    para_final: str
    cc_final: str
    advertencias: List[str] = field(default_factory=list)


@dataclass
class IdentidadOutlook:
    nombre: str = ""
    correo: str = ""
    cargo: str = ""
    telefono: str = ""
    oficina: str = ""
    departamento: str = ""
