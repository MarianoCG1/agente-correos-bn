from datetime import date

import pandas as pd
import pytest

from agente_correos.datos.cronograma_loader import (CronogramaError, CronogramaLoader, calcular_fecha_objetivo,
                                                    detectar_fila_encabezado, programas_activos)
from agente_correos.datos.directorio_agencias import DirectorioAgencias, DirectorioError, separar_correos


# ---- Cronograma -----------------------------------------------------------
def test_detecta_hoja_encabezado_y_campana(cronograma):
    assert cronograma.hoja == "CRONOGRAMA ETV"
    assert cronograma.fila_encabezado == 1            # la fila 0 es un título
    assert cronograma.campana.nombre == "JULIO – AGOSTO 2026"
    assert cronograma.columnas_faltantes == []


def test_mapea_columnas_repetidas_como_en_v1(cronograma):
    cols = set(cronograma.df.columns)
    assert {"Agencia", "P65_Usuarios", "P65_Importe", "Juntos_Usuarios", "Juntos_Importe",
            "Fecha_Pago", "Fecha_Entrega", "Hora_Pago", "Hora_Entrega", "ETV",
            "Cod_Pueblo", "Cod_Pto_Pago", "Punto_de_Pago"} <= cols


def test_descarta_filas_sin_agencia(cronograma):
    assert len(cronograma.df) == 8
    assert "AG. UNO" in cronograma.agencias()


def test_fecha_objetivo_es_la_mas_temprana(cronograma):
    fechas = cronograma.fechas_objetivo()
    assert date(2026, 10, 19) in fechas and date(2026, 10, 20) not in fechas
    assert cronograma.filas("AG. UNO", date(2026, 10, 19)).shape[0] == 1


def test_filas_ignora_tildes_y_mayusculas(cronograma):
    assert len(cronograma.filas("ag.  uno")) == 2


def test_agencias_en_fecha(cronograma):
    ags = cronograma.agencias_en_fecha(date(2026, 10, 14))
    assert "AG. UNO" in ags and "AG. SIETE" in ags and len(ags) == 7


def test_programas_activos(cronograma):
    juntos, contigo = programas_activos(cronograma.filas("AG. UNO"))
    assert juntos is True and contigo is False
    assert programas_activos(cronograma.filas("AG. DOS")) == (False, False)


def test_aviso_de_coherencia_acepta_el_desfase_de_dos_meses(cronograma):
    # JA (julio–agosto) se paga en septiembre–octubre: las fechas del cronograma son de octubre
    assert cronograma.campana.codigo == "JA"
    assert cronograma.aviso_de_coherencia() is None


def test_aviso_de_coherencia_detecta_archivo_de_otra_campana(cronograma):
    cronograma.campana = type(cronograma.campana)("EF", 2026)       # EF se paga en marzo–abril
    aviso = cronograma.aviso_de_coherencia()
    assert "MARZO – ABRIL" in aviso and "Verifique" in aviso


def test_archivo_inexistente_da_error_claro(tmp_path):
    with pytest.raises(CronogramaError):
        CronogramaLoader().cargar(tmp_path / "no_existe.xlsx")


def test_detectar_encabezado_prefiere_la_fila_con_palabras_clave():
    raw = pd.DataFrame([["Título", None, None], ["Agencia", "Fecha", "Importe"], ["X", "1", "2"]])
    assert detectar_fila_encabezado(raw) == 1


def test_calcular_fecha_objetivo_sin_columnas_de_fecha():
    df = pd.DataFrame({"Agencia": ["A", "B"]})
    assert calcular_fecha_objetivo(df).isna().all() or all(v is None for v in calcular_fecha_objetivo(df))


# ---- Directorio -------------------------------------------------------------
def test_separar_correos_ignora_nan_vacios_y_repetidos():
    assert separar_correos(float("nan")) == ([], [])
    assert separar_correos("A@bn.com.pe; a@bn.com.pe, b@bn.com.pe") == (["a@bn.com.pe", "b@bn.com.pe"], [])
    assert separar_correos("texto suelto") == ([], ["texto", "suelto"])


def test_directorio_encuentra_agencia_por_nombre_normalizado(directorio):
    d = directorio.buscar("AG. DOS")                       # en el archivo figura como 'Ag.  Dos'
    assert d.para == ("jpago_dos@bn.com.pe",) and d.cc == ()


def test_directorio_varios_cc(directorio):
    assert directorio.buscar("AG. UNO").cc == ("admin_uno@bn.com.pe", "otro_uno@bn.com.pe")


def test_directorio_celda_vacia_no_produce_la_palabra_nan(directorio):
    seis = directorio.buscar("AG. SEIS")
    assert seis.para == () and "nan" not in seis.para_texto and "nan" not in seis.cc_texto


def test_directorio_marca_correos_invalidos(directorio):
    assert directorio.buscar("AG. SIETE").invalidos != ()


def test_directorio_fuera_de_dominio(directorio):
    assert directorio.buscar("AG. CINCO").fuera_de_dominio("bn.com.pe") == ["alguien@gmail.com"]
    assert directorio.buscar("AG. UNO").fuera_de_dominio("@bn.com.pe") == []


def test_directorio_agencia_desconocida(directorio):
    assert directorio.buscar("AG. NO EXISTE") is None and not directorio.existe("AG. NO EXISTE")


def test_directorio_sin_columnas_esperadas(tmp_path):
    ruta = tmp_path / "mal.xlsx"
    pd.DataFrame({"a": [1], "b": [2]}).to_excel(ruta, index=False)
    with pytest.raises(DirectorioError):
        DirectorioAgencias.cargar(ruta)
