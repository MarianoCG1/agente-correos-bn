"""Compara una entrega armada a mano con su original: qué cambios se hicieron y si algo quedó roto."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

import pandas as pd
from openpyxl import load_workbook

from .cronograma_loader import COL_PUNTO, CronogramaLoader
from .generador_entrega import CAMPOS_REPROGRAMABLES, CambiosEntrega, Reprogramacion, Suspension

# Campos que, si difieren, no son una suspensión ni una reprogramación conocida
_CAMPOS_A_REVISAR = ("Departamento", "Provincia", "Distrito", "Punto_de_Pago", "P65_Usuarios", "P65_Importe",
                     "Juntos_Usuarios", "Juntos_Importe", "Contigo_Usuarios", "Contigo_Importe", "ETV", "Agencia")


@dataclass
class Inferencia:
    cambios: CambiosEntrega
    otras_diferencias: List[str] = field(default_factory=list)
    solo_en_entrega: List[str] = field(default_factory=list)       # puntos que no están en el original


def inferir_cambios(original: str | Path, entrega: str | Path) -> Inferencia:
    """Deduce qué se quitó y qué fechas se movieron al armar `entrega` a partir de `original`."""
    cargador = CronogramaLoader()
    g, e = cargador.cargar(original), cargador.cargar(entrega)
    gdf, edf = g.df.set_index(COL_PUNTO), e.df.set_index(COL_PUNTO)

    suspendidos = [Suspension(k, "inferido de la entrega manual") for k in gdf.index if k not in edf.index]
    solo_entrega = [k for k in edf.index if k not in gdf.index]

    reprog, otras = [], []
    comunes = [k for k in gdf.index if k in edf.index]
    for campo in CAMPOS_REPROGRAMABLES:
        if campo not in gdf.columns or campo not in edf.columns:
            continue
        for k in comunes:
            a, b = gdf.at[k, campo], edf.at[k, campo]
            if _distinto(a, b):
                reprog.append(Reprogramacion(k, campo, b.to_pydatetime() if isinstance(b, pd.Timestamp) else b,
                                             "inferido de la entrega manual"))
    for campo in _CAMPOS_A_REVISAR:
        if campo not in gdf.columns or campo not in edf.columns:
            continue
        for k in comunes:
            a, b = gdf.at[k, campo], edf.at[k, campo]
            if _distinto(a, b):
                otras.append(f"{k} · {campo}: {a!r} → {b!r}")
    return Inferencia(CambiosEntrega(suspendidos, reprog), otras, solo_entrega)


def _distinto(a, b) -> bool:
    if pd.isna(a) and pd.isna(b):
        return False
    try:
        return float(a) != float(b)
    except (TypeError, ValueError):
        pass
    return str(a).strip() != str(b).strip()


def comparar_archivos(a: str | Path, b: str | Path) -> Tuple[List[str], List[str]]:
    """Compara celda por celda. Devuelve (diferencias de valor, diferencias en fórmulas)."""
    wa, wb = load_workbook(str(a)).active, load_workbook(str(b)).active
    valores, formulas = [], []
    for r in range(1, max(wa.max_row, wb.max_row) + 1):
        for c in range(1, max(wa.max_column, wb.max_column) + 1):
            va, vb = wa.cell(r, c).value, wb.cell(r, c).value
            if va == vb or (va in (None, "") and vb in (None, "")):
                continue
            es_formula = any(isinstance(v, str) and v.startswith("=") for v in (va, vb))
            (formulas if es_formula else valores).append(f"{wa.cell(r, c).coordinate}: {va!r} ≠ {vb!r}")
    return valores, formulas
