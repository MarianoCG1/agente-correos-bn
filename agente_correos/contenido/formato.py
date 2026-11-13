"""Cómo se muestra cada tipo de dato dentro de las tablas del correo."""

from __future__ import annotations

import pandas as pd


def _vacio(v: object) -> bool:
    try:
        return v is None or bool(pd.isna(v))
    except (TypeError, ValueError):
        return False


def fecha_corta(v: object) -> str:
    """dd/mm/aa. Si no es una fecha, devuelve el texto tal cual; vacío si no hay dato."""
    if _vacio(v):
        return ""
    try:
        return pd.to_datetime(v).strftime("%d/%m/%y")
    except (ValueError, TypeError):
        return str(v)


def hora(v: object) -> str:
    """hh:mm AM/PM."""
    if _vacio(v):
        return ""
    if hasattr(v, "strftime"):
        return v.strftime("%I:%M %p")
    return str(v)


def importe(v: object) -> str:
    """1,234.50; vacío si es cero o no es número."""
    try:
        valor = float(v)
    except (ValueError, TypeError):
        return ""
    return "" if pd.isna(valor) or valor == 0 else f"{valor:,.2f}"


def entero(v: object) -> str:
    try:
        valor = float(v)
    except (ValueError, TypeError):
        return ""
    return "" if pd.isna(valor) or valor == 0 else str(int(valor))


def codigo(v: object) -> str:
    """Código con ceros a la izquierda a 4 cifras (664 → 0664)."""
    if _vacio(v) or str(v).strip() in ("", "nan", "None"):
        return ""
    crudo = str(v).strip()
    try:
        return str(int(float(crudo))).zfill(4)
    except (ValueError, TypeError):
        return crudo


def texto(v: object) -> str:
    return "" if _vacio(v) else str(v).strip()
