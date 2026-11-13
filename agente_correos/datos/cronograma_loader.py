"""Carga flexible del cronograma de entrega de fondos (Excel con estructura variable)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import List, Optional, Tuple

import pandas as pd

from ..dominio.avisos import normalizar_agencia
from ..dominio.campana import Campana
from .columnas import (COLUMNAS_OPCIONALES, COLUMNAS_REQUERIDAS, HOJAS_PREFERIDAS,
                       PALABRAS_ENCABEZADO)

log = logging.getLogger(__name__)

COL_CLAVE = "_agencia_clave"
COL_OBJETIVO = "Target_Date_Calc"
COL_FILA = "FilaExcel"          # número de fila en la hoja (base 1); sirve para ubicar el punto en el archivo
COL_PUNTO = "ClavePunto"        # 'cod. pueblo|cod. punto de pago', con ceros a la izquierda


def normalizar_codigo(valor: object) -> str:
    """'9' / 9 / 9.0 / '0009' → '0009'. Vacío si no hay dato."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return ""
    texto = str(valor).strip()
    if texto.lower() in ("", "nan", "none"):
        return ""
    if texto.endswith(".0"):
        texto = texto[:-2]
    return texto.zfill(4)


def clave_punto(cod_pueblo: object, cod_pto_pago: object) -> str:
    return f"{normalizar_codigo(cod_pueblo)}|{normalizar_codigo(cod_pto_pago)}"


class CronogramaError(Exception):
    """El archivo no se pudo interpretar como cronograma."""


@dataclass
class Cronograma:
    ruta: str
    hoja: str
    fila_encabezado: int
    campana: Campana
    df: pd.DataFrame
    columnas_faltantes: List[str]
    columnas_hoja: List[str] = None     # nombres estándar en el orden de las columnas de la hoja

    def columna_excel(self, nombre: str) -> Optional[int]:
        """Número de columna (base 1) de un campo estándar en la hoja, o None si no existe."""
        if not self.columnas_hoja or nombre not in self.columnas_hoja:
            return None
        return self.columnas_hoja.index(nombre) + 1

    # ---- consultas -----------------------------------------------------
    def agencias(self) -> List[str]:
        """Nombres de agencia tal como figuran en el cronograma, sin repetir."""
        return sorted(self.df["Agencia"].dropna().unique().tolist()) if "Agencia" in self.df else []

    def fechas_objetivo(self) -> List[date]:
        if COL_OBJETIVO not in self.df:
            return []
        return sorted({d for d in self.df[COL_OBJETIVO].dropna()})

    def filas(self, agencia: str, fecha: Optional[date] = None) -> pd.DataFrame:
        df = self.df[self.df[COL_CLAVE] == normalizar_agencia(agencia)]
        if fecha is not None:
            df = df[df[COL_OBJETIVO] == fecha]
        return df

    def agencias_en_fecha(self, fecha: date) -> List[str]:
        df = self.df[self.df[COL_OBJETIVO] == fecha]
        return sorted(df["Agencia"].unique().tolist())

    @property
    def es_valido(self) -> bool:
        return "Agencia" in self.df and not self.df.empty

    def aviso_de_coherencia(self) -> Optional[str]:
        """Texto de advertencia si las fechas no corresponden a la campaña del nombre del archivo."""
        meses = self.campana.meses_de_pago
        fechas = [d for d in self.df[COL_OBJETIVO].dropna()] if COL_OBJETIVO in self.df else []
        if not meses or not fechas:
            return None
        dentro = sum(1 for d in fechas if d.month in meses)
        if dentro / len(fechas) >= 0.5:
            return None
        return (f"El archivo indica la campaña {self.campana.nombre}, que se paga en "
                f"{self.campana.meses_de_pago_texto}, pero sus fechas van de "
                f"{min(fechas):%d/%m/%Y} a {max(fechas):%d/%m/%Y}. Verifique que sea el cronograma correcto.")


# ----------------------------------------------------------------------
# Programas sociales activos en un conjunto de filas
# ----------------------------------------------------------------------
def _tiene_usuarios(df: pd.DataFrame, columna: str) -> bool:
    if columna not in df.columns:
        return False
    return bool((pd.to_numeric(df[columna], errors="coerce").fillna(0) > 0).any())


def programas_activos(df: pd.DataFrame) -> Tuple[bool, bool]:
    """(hay Juntos, hay Contigo): solo se mencionan si algún punto tiene usuarios."""
    return _tiene_usuarios(df, "Juntos_Usuarios"), _tiene_usuarios(df, "Contigo_Usuarios")


# ----------------------------------------------------------------------
# Piezas del loader (separadas para poder probarlas una por una)
# ----------------------------------------------------------------------
_EVITAR = ("ORIGINAL", "COPIA", "RESPALDO", "BACKUP", "ANTIGU", "OLD", "TEMP", "PRUEBA")


def elegir_hoja(nombres: List[str]) -> str:
    """La hoja de trabajo: 'CRONOGRAMA ETV' si existe; si no, la primera que parezca cronograma y no
    sea una copia de referencia (original, respaldo, prueba...)."""
    normalizados = [(n, normalizar_agencia(n)) for n in nombres]
    for n, u in normalizados:
        if u == "CRONOGRAMA ETV":
            return n
    for n, u in normalizados:
        if any(k in u for k in HOJAS_PREFERIDAS) and not any(e in u for e in _EVITAR):
            return n
    for n, u in normalizados:
        if any(k in u for k in HOJAS_PREFERIDAS):
            return n
    return nombres[0]


def detectar_fila_encabezado(raw: pd.DataFrame, max_filas: int = 30) -> int:
    """Fila con más palabras de encabezado y más celdas con contenido."""
    mejor_fila, mejor_puntaje = 0, 0
    for i in range(min(max_filas, len(raw))):
        fila = raw.iloc[i]
        vacias = int(fila.isna().sum())
        textos = [str(v) for v in fila.dropna()]
        coincidencias = sum(
            1 for t in textos if any(p in t.lower() for p in PALABRAS_ENCABEZADO)
        )
        con_nombre = sum(1 for t in textos if t.strip() and "unnamed" not in t.lower())
        puntaje = coincidencias * 10 + con_nombre - vacias * 2
        if puntaje > mejor_puntaje:
            mejor_puntaje, mejor_fila = puntaje, i
    return mejor_fila


def _limpio(nombre: object) -> str:
    return (str(nombre).strip().replace(" ", "").replace(".", "")
            .replace("°", "").replace("\n", "").lower())


def encontrar_columna(df: pd.DataFrame, alias: List[str], ignorar: set) -> Optional[object]:
    """Primera columna cuyo nombre (sin espacios, puntos ni mayúsculas) coincide con un alias."""
    por_nombre = {}
    for col in df.columns:
        if col in ignorar:
            continue
        por_nombre.setdefault(_limpio(col), col)
    for nombre in alias:
        hallada = por_nombre.get(_limpio(nombre))
        if hallada is not None:
            return hallada
    return None


def mapear_columnas(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
    """Renombra a nombres estándar. Devuelve el df y las columnas requeridas que faltan."""
    cambios, faltantes, usadas = {}, [], set()

    for estandar, alias in COLUMNAS_REQUERIDAS.items():
        col = encontrar_columna(df, alias, usadas)
        if col is None:
            faltantes.append(estandar)
        else:
            cambios[col] = estandar
            usadas.add(col)

    df = df.rename(columns=cambios)

    if "Agencia" not in df.columns:
        candidatas = [c for c in df.columns
                      if "agencia" in str(c).lower() and "unnamed" not in str(c).lower()
                      and c not in usadas]
        if candidatas:
            df = df.rename(columns={candidatas[0]: "Agencia"})
            usadas.add(candidatas[0])
            if "Agencia" in faltantes:
                faltantes.remove("Agencia")

    opcionales = {}
    for estandar, alias in COLUMNAS_OPCIONALES.items():
        col = encontrar_columna(df, alias, usadas)
        if col is not None and col != estandar:
            opcionales[col] = estandar
            usadas.add(col)
    return df.rename(columns=opcionales), faltantes


def calcular_fecha_objetivo(df: pd.DataFrame) -> pd.Series:
    """Fecha más temprana entre las columnas de fecha de cada fila (pago / entrega)."""
    columnas = [c for c in ("Fecha_Pago", "Fecha_Entrega") if c in df.columns]
    if len(columnas) < 2:
        for col in df.columns:
            nombre = str(col).upper()
            if col in columnas or "UNNAMED" in nombre or "HORA" in nombre:
                continue
            if any(k in nombre for k in ("FECHA", "FEC", "PROPUESTA")):
                columnas.append(col)
    if not columnas:
        return pd.Series([None] * len(df), index=df.index, dtype=object)

    fechas = pd.concat(
        [pd.to_datetime(df[c], errors="coerce", dayfirst=True, format="mixed") for c in columnas],
        axis=1,
    )
    minima = fechas.min(axis=1)
    return minima.apply(lambda v: v.date() if pd.notna(v) else None)


# ----------------------------------------------------------------------
class CronogramaLoader:
    """Lee el Excel una sola vez y devuelve un `Cronograma` listo para consultar."""

    def cargar(self, ruta: str | Path, hoy: Optional[date] = None) -> Cronograma:
        ruta = str(ruta)
        try:
            xls = pd.ExcelFile(ruta)
        except Exception as exc:
            raise CronogramaError(f"No se pudo abrir el cronograma: {exc}") from exc

        hoja = elegir_hoja(xls.sheet_names)
        raw = xls.parse(hoja, header=None)
        fila = detectar_fila_encabezado(raw)
        df = xls.parse(hoja, header=fila)
        log.info("Hoja '%s', encabezado en la fila %s", hoja, fila)

        df, faltantes = mapear_columnas(df)
        if "Agencia" not in df.columns:
            raise CronogramaError("El archivo no tiene una columna de agencia reconocible.")

        df = df.copy()
        columnas_hoja = [str(c) for c in df.columns]
        df[COL_FILA] = df.index + fila + 2            # la fila de encabezado es la (fila + 1); los datos siguen
        df[COL_OBJETIVO] = calcular_fecha_objetivo(df)
        if "Cod_Pueblo" in df.columns and "Cod_Pto_Pago" in df.columns:
            df[COL_PUNTO] = [clave_punto(a, b) for a, b in zip(df["Cod_Pueblo"], df["Cod_Pto_Pago"])]

        agencia = df["Agencia"].astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
        valida = df["Agencia"].notna() & ~agencia.str.lower().isin(["", "nan", "none"])
        df = df[valida].copy()
        df["Agencia"] = agencia[valida]
        df[COL_CLAVE] = df["Agencia"].map(normalizar_agencia)

        return Cronograma(
            ruta=ruta,
            hoja=hoja,
            fila_encabezado=fila,
            campana=Campana.desde_archivo(ruta, hoy),
            df=df.reset_index(drop=True),
            columnas_faltantes=faltantes,
            columnas_hoja=columnas_hoja,
        )
