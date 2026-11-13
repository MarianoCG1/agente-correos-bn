"""Campaña bimensual de pago, deducida del nombre del archivo de cronograma."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

CODIGOS = {
    "EF": "ENERO – FEBRERO",
    "MA": "MARZO – ABRIL",
    "MJ": "MAYO – JUNIO",
    "JA": "JULIO – AGOSTO",
    "SO": "SEPTIEMBRE – OCTUBRE",
    "ND": "NOVIEMBRE – DICIEMBRE",
}

DESFASE_PAGO_MESES = 2
NOMBRES_MES = ("ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO", "AGOSTO",
               "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE")

_SEP = r"(?<![A-Z0-9])"      # el código no puede ir pegado a otra letra o número
_FIN = r"(?![A-Z0-9])"
_CODIGOS_RE = "|".join(CODIGOS)
_CODIGO_Y_ANIO = re.compile(rf"{_SEP}({_CODIGOS_RE}){_FIN}[\s_\-]*(20\d{{2}}){_FIN}")
_SOLO_CODIGO = re.compile(rf"{_SEP}({_CODIGOS_RE}){_FIN}")
_SOLO_ANIO = re.compile(rf"{_SEP}(20\d{{2}}){_FIN}")


@dataclass(frozen=True)
class Campana:
    codigo: str    # 'MJ'; '??' si no se pudo deducir
    anio: int

    @property
    def nombre(self) -> str:
        """Texto que va en asuntos y carpetas, p. ej. 'MAYO – JUNIO 2026'."""
        return f"{CODIGOS.get(self.codigo, 'CAMPAÑA')} {self.anio}"

    @property
    def identificada(self) -> bool:
        return self.codigo in CODIGOS

    @property
    def meses(self) -> tuple:
        """Números de los dos meses que cubre la campaña; vacío si no se identificó."""
        orden = list(CODIGOS)
        if self.codigo not in orden:
            return ()
        i = orden.index(self.codigo)
        return (2 * i + 1, 2 * i + 2)

    @property
    def meses_de_pago(self) -> tuple:
        """Meses en que se paga: el nombre indica el período cubierto y los pagos caen 2 meses después.

        Verificado con cronogramas reales: EF → marzo–abril, MA → mayo–junio, MJ → julio–agosto,
        JA → septiembre–octubre.
        """
        return tuple((m - 1 + DESFASE_PAGO_MESES) % 12 + 1 for m in self.meses)

    @property
    def meses_de_pago_texto(self) -> str:
        if not self.meses_de_pago:
            return ""
        a, b = (NOMBRES_MES[m - 1] for m in self.meses_de_pago)
        return f"{a} – {b}"

    @classmethod
    def desde_archivo(cls, ruta: str | Path, hoy: Optional[date] = None) -> "Campana":
        # Se separa a mano: en Windows Path('//servidor/archivo.xlsx') toma el archivo como recurso compartido
        nombre = re.split(r"[\\/]", str(ruta))[-1].upper()
        hoy = hoy or date.today()

        junto = _CODIGO_Y_ANIO.search(nombre)
        if junto:
            return cls(junto.group(1), int(junto.group(2)))

        codigo = _SOLO_CODIGO.search(nombre)
        anio = _SOLO_ANIO.search(nombre)
        return cls(
            codigo.group(1) if codigo else "??",
            int(anio.group(1)) if anio else hoy.year,
        )
