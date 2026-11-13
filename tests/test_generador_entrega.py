import hashlib
import os
from datetime import date, datetime, time
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook
from openpyxl.formatting.rule import Rule
from openpyxl.styles import PatternFill
from openpyxl.styles.differential import DifferentialStyle

from agente_correos.datos.cronograma_loader import CronogramaLoader, clave_punto, normalizar_codigo
from agente_correos.datos.generador_entrega import (CambiosEntrega, EntregaError, GeneradorEntrega, Reprogramacion,
                                                    Suspension, _Mapa, nombre_sugerido_entrega, remapear_formula,
                                                    sugerir_suspendidos)

ROJO = PatternFill("solid", fgColor="FFFF0000")
SUB = ["N°", "Departamento", "Provincia", "Cod. Pueblo", "Distrito", "Cod. Pto. Pago", "Punto de Pago",
       "N° Usuarios", "Importe", "Fecha Propuesta", "Hora", "ETV", "Categoría", "Cod", "Agencia", "FECHA",
       "Hora", "Días de anticipación", "ddpp", "clave2"]
# (cod. pueblo, cod. pto. pago, agencia, importe)
PUNTOS = [(1, 1, "AG. UNO", 1000.0), (2, 2, "AG. UNO", 2000.0), (3, 3, "AG. DOS", 3000.0),
          (4, 4, "AG. DOS", 4000.0), (5, 5, "AG. TRES", 5000.0), (6, 6, "AG. TRES", 6000.0)]


@pytest.fixture
def original(tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.title = "CRONOGRAMA ETV"
    ws.append([None, None, None, None, None, None, None, "Pensión 65", None, "Fecha y Hora de pago", None, "ETV",
               "Preparación y ENTREGA DE FONDOS", None, None, None, None, None, "Seguimiento", None])
    ws.append(SUB)
    for i, (cp, cpp, ag, imp) in enumerate(PUNTOS, start=1):
        r = i + 2
        ws.append([i, "DEP", "PROV", f"{cp:04d}", f"DIST {i}", f"{cpp:04d}", f"PTO {i}", 100 * i, imp,
                   datetime(2026, 10, 14), time(9, 0), "HERMES", "AGENCIA 2", "0182", ag,
                   datetime(2026, 10, 10), time(8, 30), f"=J{r}-P{r}", f"=D{r}&F{r}", f"=S{r}&N{r}"])
    ws.append([None] * 7 + ["=SUM(H3:H8)", "=SUM(I3:I8)"])
    ws.merge_cells("H1:I1")
    ws.column_dimensions["O"].width = 20
    ws.column_dimensions["A"].width = 5
    ws.row_dimensions[1].height = 40
    ws.auto_filter.ref = "A2:T9"
    ws.conditional_formatting.add("S3:T8", Rule(type="duplicateValues", dxf=DifferentialStyle()))
    for r in (4, 7):                                      # puntos "suspendidos" según la marca roja
        for c in range(4, 14):
            ws.cell(r, c).fill = ROJO
    ruta = tmp_path / "CRONOGRAMA ETV JA 2026 difusion.xlsx"
    wb.save(ruta)
    return ruta


def _hash(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def _cambios():
    return CambiosEntrega(
        suspendidos=[Suspension("0002|0002", "correo Operaciones 10/09"), Suspension("0005|0005", "oficio 112")],
        reprogramaciones=[Reprogramacion("0003|0003", "Fecha_Pago", datetime(2026, 10, 20), "correo ETV 11/09")],
    )


# ---- Resultado --------------------------------------------------------------
def test_genera_entrega_sin_tocar_el_original(original, tmp_path):
    antes = _hash(original)
    destino = tmp_path / "ENTREGA DE FONDOS ETV JA 2026 difusion.xlsx"
    resumen = GeneradorEntrega().generar(original, destino, _cambios(), usuario="mcg22")

    assert _hash(original) == antes                                   # el original no cambia ni un byte
    assert (resumen.filas_original, resumen.filas_entrega, resumen.filas_quitadas) == (6, 4, 2)
    assert resumen.importe_p65_original == 21000.0 and resumen.importe_p65_entrega == 14000.0
    assert resumen.columnas_quitadas == ["Categoría", "Cod", "Días de anticipación"]

    crono = CronogramaLoader().cargar(destino)
    assert "0002|0002" not in set(crono.df["ClavePunto"]) and "0005|0005" not in set(crono.df["ClavePunto"])
    assert len(crono.df) == 4


def test_quita_las_tres_columnas_y_conserva_el_rotulo_del_grupo(original, tmp_path):
    destino = tmp_path / "entrega.xlsx"
    GeneradorEntrega().generar(original, destino, _cambios())
    ws = load_workbook(destino).active
    rotulos = [ws.cell(2, c).value for c in range(1, ws.max_column + 1)]
    assert ws.max_column == 17
    assert "Categoría" not in rotulos and "Cod" not in rotulos and "Días de anticipación" not in rotulos
    assert "Agencia" in rotulos
    col_agencia = rotulos.index("Agencia") + 1
    assert ws.cell(1, col_agencia).value == "Preparación y ENTREGA DE FONDOS"      # el rótulo del grupo no se pierde


def test_ajusta_formulas_totales_anchos_y_combinadas(original, tmp_path):
    destino = tmp_path / "entrega.xlsx"
    resumen = GeneradorEntrega().generar(original, destino, _cambios())
    ws = load_workbook(destino).active

    # filas conservadas: 3, 5, 6, 8 → 3, 4, 5, 6; 'ddpp' pasó de la columna S (19) a la P (16)
    assert ws["P4"].value == "=D4&F4"
    assert ws["Q4"].value in (None, "")                       # la que dependía de la columna quitada pasa a valor
    assert resumen.formulas_convertidas_a_valor == 4
    assert ws["H7"].value == "=SUM(H3:H6)" and ws["I7"].value == "=SUM(I3:I6)"
    assert ws.column_dimensions["M"].width == 20              # 'Agencia' ya no está en O sino en M
    assert ws.column_dimensions["A"].width == 5
    assert ws.row_dimensions[1].height == 40
    assert "H1:I1" in [str(r) for r in ws.merged_cells.ranges]
    assert ws.auto_filter.ref == "A2:Q7"
    assert [str(cf.sqref) for cf in ws.conditional_formatting._cf_rules] == ["P3:Q6"]


def test_aplica_reprogramacion_conservando_el_formato(original, tmp_path):
    destino = tmp_path / "entrega.xlsx"
    GeneradorEntrega().generar(original, destino, _cambios())
    crono = CronogramaLoader().cargar(destino)
    fila = crono.df[crono.df["ClavePunto"] == "0003|0003"].iloc[0]
    assert fila["Fecha_Pago"] == datetime(2026, 10, 20)
    otras = crono.df[crono.df["ClavePunto"] != "0003|0003"]
    assert set(otras["Fecha_Pago"]) == {datetime(2026, 10, 14)}


def test_deja_bitacora_que_permite_regenerar(original, tmp_path):
    destino = tmp_path / "entrega.xlsx"
    resumen = GeneradorEntrega().generar(original, destino, _cambios(), usuario="mcg22")
    bitacora = Path(resumen.bitacora)
    assert bitacora.name == "entrega.cambios.json"
    de_vuelta = CambiosEntrega.desde_bitacora(bitacora)
    assert [s.origen for s in de_vuelta.suspendidos] == ["correo Operaciones 10/09", "oficio 112"]
    assert de_vuelta.reprogramaciones[0].valor == datetime(2026, 10, 20)
    # regenerar desde el original con la misma lista produce la misma entrega
    otro = tmp_path / "entrega2.xlsx"
    r2 = GeneradorEntrega().generar(original, otro, de_vuelta)
    assert (r2.filas_entrega, r2.importe_p65_entrega) == (resumen.filas_entrega, resumen.importe_p65_entrega)


def test_sugiere_como_suspendidos_los_puntos_marcados_en_rojo(original):
    assert sorted(sugerir_suspendidos(original)) == ["0002|0002", "0005|0005"]


# ---- Protecciones -------------------------------------------------------------
def test_no_permite_escribir_sobre_el_original(original):
    with pytest.raises(EntregaError, match="no se modifica"):
        GeneradorEntrega().generar(original, original, CambiosEntrega(), sobrescribir=True)


def test_no_pisa_un_archivo_existente_sin_permiso(original, tmp_path):
    destino = tmp_path / "entrega.xlsx"
    GeneradorEntrega().generar(original, destino, CambiosEntrega())
    with pytest.raises(EntregaError, match="Ya existe"):
        GeneradorEntrega().generar(original, destino, CambiosEntrega())
    GeneradorEntrega().generar(original, destino, CambiosEntrega(), sobrescribir=True)


def test_rechaza_puntos_que_no_existen(original, tmp_path):
    with pytest.raises(EntregaError, match="no existen"):
        GeneradorEntrega().generar(original, tmp_path / "x.xlsx", CambiosEntrega(suspendidos=[Suspension("9999|9999")]))
    assert not (tmp_path / "x.xlsx").exists()


def test_rechaza_campo_no_reprogramable(original, tmp_path):
    malo = CambiosEntrega(reprogramaciones=[Reprogramacion("0001|0001", "P65_Importe", 5)])
    with pytest.raises(EntregaError, match="no reprogramable"):
        GeneradorEntrega().generar(original, tmp_path / "x.xlsx", malo)


def test_sin_cambios_solo_quita_las_columnas(original, tmp_path):
    r = GeneradorEntrega().generar(original, tmp_path / "e.xlsx", CambiosEntrega())
    assert r.filas_quitadas == 0 and r.importe_p65_entrega == r.importe_p65_original


# ---- Utilidades ---------------------------------------------------------------
def test_codigos_con_ceros():
    assert normalizar_codigo(9) == "0009" and normalizar_codigo("9.0") == "0009" and normalizar_codigo(float("nan")) == ""
    assert clave_punto(9, "0821") == "0009|0821"


def test_remapear_formula():
    cols, filas = _Mapa(10, [3]), _Mapa(10, [5])
    assert remapear_formula("=D2+A2", cols, filas) == "=C2+A2"            # D pasa a C
    assert remapear_formula("=SUM(B2:B9)", cols, filas) == "=SUM(B2:B8)"  # el rango se acorta
    assert remapear_formula("=$A$6&B7", cols, filas) == "=$A$5&B6"        # filas que bajan, absolutos intactos
    assert remapear_formula("=C2+1", cols, filas) is None                 # apunta a la columna quitada
    assert remapear_formula("=A5", cols, filas) is None                   # apunta a la fila quitada
    assert remapear_formula("=SUM(A1:J1)", cols, filas) == "=SUM(A1:I1)"


def test_nombre_sugerido_para_la_entrega():
    assert nombre_sugerido_entrega("CRONOGRAMA ETV JA 2026 difusion.xlsx") == "ENTREGA DE FONDOS ETV JA 2026 difusion.xlsx"
    assert nombre_sugerido_entrega("C:/x/P65 CRONOGRAMA ETV MJ 2026 (1).xlsx") == "ENTREGA DE FONDOS ETV MJ 2026 (1).xlsx"
    assert nombre_sugerido_entrega("otro.xlsx") == "ENTREGA DE FONDOS - otro.xlsx"
