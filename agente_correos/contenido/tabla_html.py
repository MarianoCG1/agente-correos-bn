"""Tabla de programación que va en el cuerpo del correo (colores como el Excel del banco).

Es la misma tabla que ve la persona en la revisión previa: se genera una sola vez.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

import pandas as pd

from . import formato

_FORMATEADORES = {
    "texto": formato.texto,
    "codigo": formato.codigo,
    "importe": formato.importe,
    "entero": formato.entero,
    "fecha": formato.fecha_corta,
    "hora": formato.hora,
}

_AMARILLO = "#FFFF00"
_ESTILO_TH = ("padding:0px 2px;border:1px solid #ccc;text-align:center;font-weight:bold;"
              "font-size:8pt;vertical-align:middle;")
_ESTILO_TD = "padding:0px 2px;border:1px solid #ccc;text-align:center;font-size:8pt;"


@dataclass(frozen=True)
class _Columna:
    grupo: str        # texto de la cabecera superior (puede llevar <br>)
    fondo: str        # color de la cabecera
    etiqueta: str     # texto de la cabecera inferior (solo en grupos de varias columnas)
    clave: str        # nombre de la columna en el DataFrame
    tipo: str         # clave de _FORMATEADORES
    resaltar: bool = False


def _columnas(df: pd.DataFrame, juntos: bool, contigo: bool) -> List[_Columna]:
    c: List[_Columna] = []
    zona, rojo, p65, ver, cel, agua, ent = "#FF9999", "#FF0000", "#FFFF99", "#00B050", "#00B0F0", "#CCFFCC", "#00B0F0"

    # Al frente, para que quien recibe el correo vea de inmediato qué ETV entrega, desde qué base y cuándo
    if "ETV" in df.columns:
        grupo_etv = "Empresa<br>Responsable"
        c.append(_Columna(grupo_etv, ver, "ETV", "ETV", "texto"))
        if "Base" in df.columns:
            c.append(_Columna(grupo_etv, ver, "Base", "Base", "texto"))
        if "N° Pagadores" in df.columns:
            c.append(_Columna(grupo_etv, ver, "N° Pagadores", "N° Pagadores", "entero"))
    grupo_entrega = "Preparación y ENTREGA DE FONDOS"
    c.append(_Columna(grupo_entrega, ent, "Agencia", "Agencia", "texto"))
    if "Fecha_Entrega" in df.columns:
        c.append(_Columna(grupo_entrega, ent, "Fecha", "Fecha_Entrega", "fecha", resaltar=True))
    if "Hora_Entrega" in df.columns:
        c.append(_Columna(grupo_entrega, ent, "Hora", "Hora_Entrega", "hora", resaltar=True))

    c.append(_Columna("Departamento", zona, "Departamento", "Departamento", "texto"))
    c.append(_Columna("Provincia", zona, "Provincia", "Provincia", "texto"))
    if "Cod_Pueblo" in df.columns:
        c.append(_Columna("Cod.<br>Pueblo", zona, "Cod_Pueblo", "Cod_Pueblo", "codigo"))
    c.append(_Columna("Distrito", zona, "Distrito", "Distrito", "texto"))
    if "Cod_Pto_Pago" in df.columns:
        c.append(_Columna("Cod.<br>Pto.Pago", zona, "Cod_Pto_Pago", "Cod_Pto_Pago", "codigo"))
    c.append(_Columna("Punto de Pago", rojo, "Punto de Pago", "Punto_de_Pago", "texto"))

    c.append(_Columna("Pensión 65", p65, "N° Usuarios", "P65_Usuarios", "entero"))
    c.append(_Columna("Pensión 65", p65, "Importe", "P65_Importe", "importe"))
    if juntos:
        c.append(_Columna("Juntos", ver, "N° Usuarios", "Juntos_Usuarios", "entero"))
        c.append(_Columna("Juntos", ver, "Importe", "Juntos_Importe", "importe"))
    if contigo:
        c.append(_Columna("Contigo", cel, "N° Usuarios", "Contigo_Usuarios", "entero"))
        c.append(_Columna("Contigo", cel, "Importe", "Contigo_Importe", "importe"))

    grupo_pago = "Fecha y Hora de<br>Pago PP65"
    c.append(_Columna(grupo_pago, agua, "Fecha Pago", "Fecha_Pago", "fecha"))
    if "Hora_Pago" in df.columns:
        c.append(_Columna(grupo_pago, agua, "Hora", "Hora_Pago", "hora"))
    return c


def ordenar_por_fecha(df: pd.DataFrame) -> pd.DataFrame:
    """Filas por fecha y hora de entrega (si no hay, por fecha de pago); a igualdad, por ETV, distrito y punto.
    El orden es estable y lo vacío va al final."""
    clave_fecha = "Fecha_Entrega" if "Fecha_Entrega" in df.columns else "Fecha_Pago"
    clave_hora = "Hora_Entrega" if "Hora_Entrega" in df.columns else "Hora_Pago"
    if clave_fecha not in df.columns:
        return df
    aux = pd.DataFrame(index=df.index)
    aux["_f"] = pd.to_datetime(df[clave_fecha], errors="coerce")
    aux["_h"] = (pd.to_timedelta(df[clave_hora].astype(str), errors="coerce")
                 if clave_hora in df.columns else pd.NaT)
    desempate = []
    for nombre in ("ETV", "Distrito", "Punto_de_Pago"):
        if nombre in df.columns:
            aux["_" + nombre] = df[nombre].astype(str).str.upper()
            desempate.append("_" + nombre)
    orden = aux.sort_values(["_f", "_h"] + desempate, kind="stable", na_position="last").index
    return df.loc[orden]


def construir_tabla(df: pd.DataFrame, juntos: bool, contigo: bool, es_recordatorio: bool = False) -> str:
    df = ordenar_por_fecha(df)
    columnas = _columnas(df, juntos, contigo)

    grupos: dict = {}
    for col in columnas:
        grupos.setdefault(col.grupo, []).append(col)

    html = ['<table style="border-collapse:collapse;font-family:Calibri;width:100%;"><thead><tr>']
    segunda_fila: List[_Columna] = []
    for nombre, cols in grupos.items():
        fondo = cols[0].fondo
        if len(cols) == 1:
            html.append(f'<td rowspan="2" style="background:{fondo};color:black;{_ESTILO_TH}">{nombre}</td>')
        else:
            html.append(f'<td colspan="{len(cols)}" style="background:{fondo};color:black;{_ESTILO_TH}">{nombre}</td>')
            segunda_fila.extend(cols)
    html.append("</tr><tr>")
    for col in segunda_fila:
        html.append(f'<td style="background:{col.fondo};color:black;{_ESTILO_TH}">{col.etiqueta}</td>')
    html.append("</tr></thead><tbody>")

    for i, (_, fila) in enumerate(df.iterrows()):
        fondo_fila = "background:#f9f0f0;" if (not es_recordatorio and i % 2 == 1) else ""
        html.append(f'<tr style="{fondo_fila}">')
        for col in columnas:
            valor = _FORMATEADORES[col.tipo](fila.get(col.clave, ""))
            estilo = _ESTILO_TD
            if col.tipo == "importe" and valor:
                estilo += f"background:{_AMARILLO};font-weight:bold;"
            elif col.resaltar:
                estilo += f"background:{_AMARILLO};font-weight:bold;"
            if valor:
                html.append(f'<td style="{estilo}">{valor}</td>')
            else:
                html.append(f'<td style="{estilo}background:red;"></td>')   # dato faltante = celda roja
        html.append("</tr>")
    html.append("</tbody></table>")
    return "".join(html)
