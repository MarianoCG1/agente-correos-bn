"""Compara v2 contra la v1 en uso. Se omite solo si v1 no se puede importar (p. ej. sin tkcalendar).

La paridad es el criterio de la Fase 1: mismas agencias, mismas fechas, misma tabla y mismo
cuerpo de correo que ya conocen las agencias.
"""

import importlib.util
import os
import re
import types
from collections import Counter
from pathlib import Path

import pytest

from agente_correos.configuracion import Configuracion
from agente_correos.contenido.plantillas import Plantillas, Programas, fecha_de_inicio
from agente_correos.contenido.tabla_html import construir_tabla
from agente_correos.datos.cronograma_loader import programas_activos

V1 = Path(__file__).resolve().parents[1] / "legacy" / "v1" / "correos.py"


def _contenido_de_filas(html):
    """Qué datos lleva cada fila de la tabla, sin importar el orden de filas ni de columnas
    (v2 ordena por fecha y pone ETV, Base, pagadores, agencia y fecha al frente a propósito)."""
    cuerpo = html.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
    filas = [re.findall(r"<td[^>]*>(.*?)</td>", f) for f in cuerpo.split("</tr>") if "<td" in f]
    return Counter(tuple(sorted(celdas)) for celdas in filas)


def _sin_tabla(html):
    return re.sub(r"<table.*?</table>", "<TABLA>", html, flags=re.S)


@pytest.fixture(scope="module")
def v1(tmp_path_factory):
    if not V1.exists():
        pytest.skip("No está correos.py de v1")
    anterior = os.getcwd()
    os.chdir(tmp_path_factory.mktemp("v1"))        # v1 crea correos_etv.log en el directorio actual
    try:
        spec = importlib.util.spec_from_file_location("correos_v1", V1)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        return modulo
    except Exception as exc:                        # tkinter/tkcalendar ausentes
        pytest.skip(f"v1 no se pudo importar: {exc}")
    finally:
        os.chdir(anterior)


def _stub(v1, campana):
    app = v1.CorreosETVApp
    s = types.SimpleNamespace(campaign=campana, _fmt_amt=app._fmt_amt, _fmt_int=app._fmt_int,
                              _fmt_date=app._fmt_date, _fmt_time=app._fmt_time)
    s._build_html_table = lambda *a, **k: app._build_html_table(s, *a, **k)
    return s


def test_mismas_agencias_y_fechas(v1, crono_path, cronograma):
    df1, faltantes = v1.ExcelLoader.load_flexible(str(crono_path))
    assert faltantes == cronograma.columnas_faltantes
    assert list(df1["Agencia"].astype(str).str.strip()) == list(cronograma.df["Agencia"])
    assert list(df1["Target_Date_Calc"]) == list(cronograma.df["Target_Date_Calc"])


@pytest.mark.parametrize("agencia", ["AG. UNO", "AG. DOS", "AG. TRES"])
@pytest.mark.parametrize("recordatorio", [False, True])
def test_misma_tabla_html(v1, cronograma, agencia, recordatorio):
    filas = cronograma.filas(agencia)
    juntos, contigo = programas_activos(filas)
    esperado = _stub(v1, "X")._build_html_table(filas, juntos, contigo, is_reminder=recordatorio)
    obtenido = construir_tabla(filas, juntos, contigo, es_recordatorio=recordatorio)
    # el contenido de cada fila es el mismo que en v1; solo cambian el orden de filas y de columnas
    assert _contenido_de_filas(obtenido) == _contenido_de_filas(esperado)


def test_mismo_cuerpo_de_inicio(v1, cronograma):
    filas = cronograma.filas("AG. UNO")
    juntos, contigo = programas_activos(filas)
    campana = cronograma.campana.nombre
    inicio = fecha_de_inicio(filas)
    s = _stub(v1, campana)
    v1_html = v1.CorreosETVApp._build_html_body(
        s, "AG. UNO", f"{inicio.day:02d} DE {v1_mes(inicio)} DE {inicio.year}", filas, juntos, contigo)

    tabla = construir_tabla(filas, juntos, contigo)
    v2_html = Plantillas(Configuracion()).cuerpo_inicio("AG. UNO", inicio, campana, tabla, Programas(juntos, contigo))
    assert _sin_tabla(v2_html) == _sin_tabla(v1_html.replace("\n", ""))          # el texto del correo es idéntico
    assert _contenido_de_filas(v2_html) == _contenido_de_filas(v1_html.replace("\n", ""))


def v1_mes(d):
    return ["ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO", "AGOSTO", "SEPTIEMBRE",
            "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"][d.month - 1]
