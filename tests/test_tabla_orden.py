"""La tabla del correo: columnas de la ETV y de la entrega al frente, y filas por fecha y hora."""

import re
from datetime import datetime, time

import pandas as pd

from agente_correos.contenido.tabla_html import construir_tabla, ordenar_por_fecha


def _filas(*datos, con_base=True):
    """datos: (ETV, distrito, fecha de entrega, hora de entrega)."""
    registros = []
    for etv, distrito, fecha, hora in datos:
        r = {"Departamento": "CUSCO", "Provincia": "CUSCO", "Distrito": distrito, "Punto_de_Pago": "PTO " + distrito,
             "P65_Usuarios": 10, "P65_Importe": 1000.0, "Fecha_Pago": datetime(2026, 12, 20), "Hora_Pago": time(9, 0),
             "ETV": etv, "Agencia": "CUSCO", "Fecha_Entrega": fecha, "Hora_Entrega": hora}
        if con_base:
            r.update({"Base": "CUSCO", "N° Pagadores": 4})
        registros.append(r)
    return pd.DataFrame(registros)


def _cabeceras(html):
    """(grupos de la primera fila, etiquetas de la segunda fila) de la cabecera."""
    cabecera = html.split("<thead>", 1)[1].split("</thead>", 1)[0]
    primera, segunda = cabecera.split("</tr>")[:2]
    limpiar = lambda t: re.sub(r"\s+", " ", t.replace("<br>", " ")).strip()
    return ([limpiar(g) for g in re.findall(r"<td[^>]*>(.*?)</td>", primera)],
            [limpiar(g) for g in re.findall(r"<td[^>]*>(.*?)</td>", segunda)])


def _columna(html, indice):
    cuerpo = html.split("<tbody>", 1)[1]
    return [re.findall(r"<td[^>]*>(.*?)</td>", f)[indice] for f in cuerpo.split("</tr>") if "<td" in f]


DESORDENADO = _filas(
    ("PROSEGUR", "C", datetime(2026, 12, 3), time(8, 30)),
    ("HERMES", "A", datetime(2026, 11, 12), time(10, 0)),
    ("HERMES", "B", datetime(2026, 11, 12), time(8, 30)),
    ("PROSEGUR", "D", datetime(2026, 11, 5), time(9, 0)),
)


def test_las_columnas_de_la_etv_y_la_entrega_van_al_frente():
    grupos, sub = _cabeceras(construir_tabla(DESORDENADO, False, False))
    assert grupos[:3] == ["Empresa Responsable", "Preparación y ENTREGA DE FONDOS", "Departamento"]
    assert sub[:6] == ["ETV", "Base", "N° Pagadores", "Agencia", "Fecha", "Hora"]


def test_lo_que_se_movio_al_frente_no_se_repite_al_final():
    grupos, sub = _cabeceras(construir_tabla(DESORDENADO, False, False))
    assert grupos.count("Empresa Responsable") == 1 and grupos.count("Preparación y ENTREGA DE FONDOS") == 1
    for etiqueta in ("ETV", "Base", "N° Pagadores", "Agencia"):
        assert sub.count(etiqueta) == 1
    assert sub[-2:] == ["Fecha Pago", "Hora"]                      # lo demás sigue igual; termina con el pago


def test_las_filas_van_por_fecha_y_luego_por_hora():
    html = construir_tabla(DESORDENADO, False, False)
    assert _columna(html, 4) == ["05/11/26", "12/11/26", "12/11/26", "03/12/26"]      # fecha de entrega
    assert _columna(html, 5) == ["09:00 AM", "08:30 AM", "10:00 AM", "08:30 AM"]      # el 12/11: 08:30 antes que 10:00
    assert _columna(html, 0) == ["PROSEGUR", "HERMES", "HERMES", "PROSEGUR"]


def test_lo_que_no_tiene_fecha_va_al_final():
    df = _filas(("HERMES", "A", None, None), ("PROSEGUR", "B", datetime(2026, 11, 5), time(9, 0)))
    assert list(ordenar_por_fecha(df)["Distrito"]) == ["B", "A"]


def test_ordenar_no_pierde_filas_ni_modifica_el_original():
    ordenado = ordenar_por_fecha(DESORDENADO)
    assert len(ordenado) == len(DESORDENADO) and sorted(ordenado["Distrito"]) == ["A", "B", "C", "D"]
    assert list(DESORDENADO["Distrito"]) == ["C", "A", "B", "D"]


def test_un_archivo_sin_base_ni_pagadores_sigue_funcionando():
    df = _filas(("HERMES", "A", datetime(2026, 11, 5), time(9, 0)), con_base=False)
    grupos, sub = _cabeceras(construir_tabla(df, False, False))
    assert grupos[:2] == ["Empresa Responsable", "Preparación y ENTREGA DE FONDOS"]    # la ETV sola ocupa su propia celda
    assert sub[:3] == ["Agencia", "Fecha", "Hora"] and "Base" not in sub


def test_un_dato_faltante_sigue_siendo_una_celda_roja():
    df = _filas(("HERMES", "A", datetime(2026, 11, 5), time(9, 0)))
    df.loc[0, "Base"] = ""
    assert "background:red" in construir_tabla(df, False, False)
