"""Un aviso es lo que se le comunica a una agencia: el inicio de campaña o un recordatorio."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Optional


class TipoAviso(str, Enum):
    INICIO = "inicio"
    RECORDATORIO = "recordatorio"


class EstadoAviso(str, Enum):
    PENDIENTE = "pendiente"      # fecha futura
    HOY = "hoy"                  # toca prepararlo hoy
    ENVIANDO = "enviando"        # registrado antes de enviar; si queda así, el envío se interrumpió
    BORRADOR = "borrador"
    ENVIADO = "enviado"
    OMITIDO = "omitido"
    BLOQUEADO = "bloqueado"
    DECISION = "decision"        # requiere que la persona decida (p. ej. hilo ambiguo)
    VENCIDO = "vencido"          # la fecha pasó y no hay registro de aviso
    ERROR = "error"
    ANULADO = "anulado"          # se envió con espera y la persona lo anuló a tiempo


def normalizar_agencia(nombre: object) -> str:
    """Clave de comparación: sin tildes, en mayúsculas, espacios colapsados."""
    texto = unicodedata.normalize("NFKD", str(nombre or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto).strip().upper()


@dataclass(frozen=True)
class ClaveAviso:
    campana: str
    agencia: str                          # ya normalizada
    tipo: TipoAviso
    fecha_objetivo: Optional[date] = None  # None para el aviso de inicio

    @classmethod
    def crear(cls, campana: str, agencia: str, tipo: TipoAviso,
              fecha_objetivo: Optional[date] = None) -> "ClaveAviso":
        return cls(campana, normalizar_agencia(agencia), tipo,
                   fecha_objetivo if tipo is TipoAviso.RECORDATORIO else None)


@dataclass
class EventoAviso:
    """Una línea del historial. Nunca se modifica: el estado vigente es el último evento."""
    clave: ClaveAviso
    estado: EstadoAviso
    usuario: str = ""
    equipo: str = ""
    creado_en: Optional[datetime] = None
    asunto: str = ""
    para: str = ""
    cc: str = ""
    detalle: str = ""
    id_outlook: str = ""
    id_evento: str = ""

    def a_dict(self) -> dict:
        return {
            "campana": self.clave.campana,
            "agencia": self.clave.agencia,
            "tipo": self.clave.tipo.value,
            "fecha_objetivo": self.clave.fecha_objetivo.isoformat() if self.clave.fecha_objetivo else None,
            "estado": self.estado.value,
            "usuario": self.usuario,
            "equipo": self.equipo,
            "creado_en": self.creado_en.isoformat() if self.creado_en else None,
            "asunto": self.asunto,
            "para": self.para,
            "cc": self.cc,
            "detalle": self.detalle,
            "id_outlook": self.id_outlook,
            "id_evento": self.id_evento,
        }

    @classmethod
    def desde_dict(cls, d: dict) -> "EventoAviso":
        fecha = d.get("fecha_objetivo")
        creado = d.get("creado_en")
        return cls(
            clave=ClaveAviso(
                campana=d["campana"],
                agencia=d["agencia"],
                tipo=TipoAviso(d["tipo"]),
                fecha_objetivo=date.fromisoformat(fecha) if fecha else None,
            ),
            estado=EstadoAviso(d["estado"]),
            usuario=d.get("usuario", ""),
            equipo=d.get("equipo", ""),
            creado_en=datetime.fromisoformat(creado) if creado else None,
            asunto=d.get("asunto", ""),
            para=d.get("para", ""),
            cc=d.get("cc", ""),
            detalle=d.get("detalle", ""),
            id_outlook=d.get("id_outlook", ""),
            id_evento=d.get("id_evento", ""),
        )
