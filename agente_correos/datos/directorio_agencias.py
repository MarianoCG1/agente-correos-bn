"""Lista de agencias con sus correos (agencias_correos.xlsx)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from ..dominio.avisos import normalizar_agencia
from .columnas import ALIAS_AGENCIA, ALIAS_CC, ALIAS_CORREO
from .cronograma_loader import encontrar_columna

_SEPARADORES = re.compile(r"[;,\s]+")
_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class DirectorioError(Exception):
    """El archivo de agencias no tiene la estructura esperada."""


def separar_correos(texto: object) -> Tuple[List[str], List[str]]:
    """Divide un campo con varios correos. Devuelve (válidos, inválidos), en minúsculas y sin repetir."""
    if texto is None or (isinstance(texto, float) and pd.isna(texto)):
        return [], []
    validos, invalidos = [], []
    for token in _SEPARADORES.split(str(texto).strip()):
        token = token.strip().strip("<>").lower()
        if not token or token == "nan":
            continue
        destino = validos if _CORREO.match(token) else invalidos
        if token not in destino:
            destino.append(token)
    return validos, invalidos


@dataclass(frozen=True)
class Destinatarios:
    para: Tuple[str, ...] = ()
    cc: Tuple[str, ...] = ()
    invalidos: Tuple[str, ...] = ()

    @property
    def para_texto(self) -> str:
        return "; ".join(self.para)

    @property
    def cc_texto(self) -> str:
        return "; ".join(self.cc)

    def fuera_de_dominio(self, dominio: str) -> List[str]:
        """Correos cuyo dominio no es el interno (`dominio` con o sin '@')."""
        sufijo = "@" + dominio.strip().lower().lstrip("@")
        return [c for c in (*self.para, *self.cc) if not c.endswith(sufijo)]


class DirectorioAgencias:
    def __init__(self, filas: Dict[str, Tuple[str, Destinatarios]], duplicadas: List[str]):
        self._filas = filas
        self.duplicadas = duplicadas

    @classmethod
    def cargar(cls, ruta: str | Path) -> "DirectorioAgencias":
        try:
            df = pd.read_excel(str(ruta))
        except Exception as exc:
            raise DirectorioError(f"No se pudo abrir la lista de agencias: {exc}") from exc

        col_ag = encontrar_columna(df, ALIAS_AGENCIA, set())
        col_para = encontrar_columna(df, ALIAS_CORREO, set())
        col_cc = encontrar_columna(df, ALIAS_CC, set())
        if col_ag is None or col_para is None:
            raise DirectorioError(
                "La lista de agencias debe tener una columna de agencia y una de correo "
                f"(columnas encontradas: {list(df.columns)})."
            )

        filas: Dict[str, Tuple[str, Destinatarios]] = {}
        duplicadas: List[str] = []
        for _, fila in df.iterrows():
            nombre = str(fila[col_ag]).strip()
            clave = normalizar_agencia(nombre)
            if not clave or clave == "NAN":
                continue
            para, mal_para = separar_correos(fila[col_para])
            cc, mal_cc = separar_correos(fila[col_cc]) if col_cc is not None else ([], [])
            if clave in filas:
                duplicadas.append(nombre)
                continue
            filas[clave] = (nombre, Destinatarios(tuple(para), tuple(cc), tuple(mal_para + mal_cc)))
        return cls(filas, duplicadas)

    def buscar(self, agencia: str) -> Optional[Destinatarios]:
        encontrada = self._filas.get(normalizar_agencia(agencia))
        return encontrada[1] if encontrada else None

    def existe(self, agencia: str) -> bool:
        return normalizar_agencia(agencia) in self._filas

    def agencias(self) -> List[str]:
        return sorted(nombre for nombre, _ in self._filas.values())
