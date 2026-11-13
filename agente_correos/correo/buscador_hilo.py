"""Decide cuál es el correo de inicio de una agencia. Coincidencia exacta del asunto, no por subcadena."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from .modelos import MensajeEncontrado

_PREFIJOS = re.compile(r"^\s*(re|rv|fw|fwd|r|f|res|enc)\s*:\s*", re.IGNORECASE)


def sin_prefijos(asunto: str) -> str:
    """Quita RE:, RV:, FW: y similares, las veces que estén repetidos."""
    anterior = None
    texto = asunto or ""
    while anterior != texto:
        anterior, texto = texto, _PREFIJOS.sub("", texto)
    return texto.strip()


def normalizar_asunto(asunto: str) -> str:
    return re.sub(r"\s+", " ", sin_prefijos(asunto)).strip().upper()


def _es_original(m: MensajeEncontrado) -> bool:
    return m.es_enviado and not _PREFIJOS.match(m.asunto or "")


@dataclass
class ResultadoHilo:
    estado: str                                     # 'unico' | 'ninguno' | 'ambiguo'
    elegido: Optional[MensajeEncontrado] = None
    candidatos: List[MensajeEncontrado] = field(default_factory=list)


def elegir_hilo(mensajes: Sequence[MensajeEncontrado], asunto_inicio: str) -> ResultadoHilo:
    """Entre los mensajes con el asunto de inicio de la agencia, el original enviado por esta cuenta.

    Si hay un solo original, es ese. Si hay varios candidatos y no se puede distinguir, es ambiguo y
    lo decide la persona (nunca se adivina).
    """
    objetivo = normalizar_asunto(asunto_inicio)
    candidatos = [m for m in mensajes
                  if normalizar_asunto(m.asunto) == objetivo
                  and not (m.asunto or "").strip().upper().startswith("RECORDATORIO")]
    vistos, unicos = set(), []
    for m in candidatos:
        if m.id not in vistos:
            vistos.add(m.id)
            unicos.append(m)
    unicos.sort(key=lambda m: m.enviado_en or __import__("datetime").datetime.min, reverse=True)

    if not unicos:
        return ResultadoHilo("ninguno")
    originales = [m for m in unicos if _es_original(m)]
    if len(originales) == 1:
        return ResultadoHilo("unico", originales[0], unicos)
    if len(unicos) == 1:
        return ResultadoHilo("unico", unicos[0], unicos)
    return ResultadoHilo("ambiguo", None, unicos)
