"""Copia fija del área en los correos y regeneración de borradores propios."""

import json
from datetime import date, datetime

from agente_correos.dominio.avisos import ClaveAviso, EstadoAviso, EventoAviso, TipoAviso
from agente_correos.historial.registro import RegistroEjecuciones

from test_api import UNO, _esperar
from test_primer_uso import api  # noqa: F401  (fixture)

JEFE = "jefe@bn.com.pe"


def _vista(api_, agencia="AG. UNO", tipo="inicio", fecha=None):
    return api_.vista_previa(agencia, tipo, fecha)["datos"]


def _otra_persona(api_, estado, usuario="rosa"):
    """Un evento de otra persona en el registro compartido."""
    reg = RegistroEjecuciones(api_._compartida / "registro", usuario, ruta_campana=api_._carpeta_registro)
    campana = api_._cronograma().campana.nombre
    clave = ClaveAviso.crear(campana, "AG. UNO", TipoAviso.RECORDATORIO, date(2026, 10, 14))
    reg.registrar(EventoAviso(clave=clave, estado=estado))


# ---- copia fija ---------------------------------------------------------
def test_el_inicio_lleva_copia_a_la_jefatura_ademas_de_la_del_administrador(api):
    api.config_guardar({"copia_fija": [JEFE, "area1@bn.com.pe", "area2@bn.com.pe"]})
    cc = _vista(api)["cc"]
    assert JEFE in cc and "area1@bn.com.pe" in cc and "area2@bn.com.pe" in cc
    assert "admin_ag._uno@bn.com.pe" in cc or any(c.startswith("admin_") for c in cc)    # la copia de la agencia se conserva


def test_no_se_repite_a_nadie_en_la_copia(api):
    api.config_guardar({"copia_fija": [JEFE, JEFE.upper(), "jpago_ag._uno@bn.com.pe"]})
    v = _vista(api)
    todos = [x.lower() for x in v["para"] + v["cc"]]
    assert len(todos) == len(set(todos))


def test_los_recordatorios_sin_hilo_copian_al_area_pero_no_a_los_excluidos(api):
    api.config_guardar({"copia_fija": [JEFE, "area1@bn.com.pe"], "correos_excluidos": [JEFE]})
    v = _vista(api, tipo="recordatorio", fecha="2026-10-14")
    assert "area1@bn.com.pe" in v["cc"] and JEFE not in v["cc"]


def test_se_rechaza_una_copia_con_formato_o_dominio_invalido(api):
    r = api.config_guardar({"copia_fija": ["no-es-correo"]})
    assert r["ok"] is False and "no es un correo válido" in r["error"]
    r = api.config_guardar({"copia_fija": ["alguien@gmail.com"]})
    assert r["ok"] is False and "@bn.com.pe" in r["error"]


def test_la_copia_se_guarda_en_minusculas_y_sin_repetidos(api):
    api.config_guardar({"copia_fija": ["Area1@BN.com.pe", "area1@bn.com.pe"]})
    assert api.config_obtener()["datos"]["valores"]["copia_fija"] == ["area1@bn.com.pe"]


# ---- borradores ---------------------------------------------------------
def _hacer_borrador(api_, seleccion):
    lote = api_.confirmar_envio([seleccion], "borrador")["datos"]["lote"]
    return _esperar(api_, lote)


def test_un_borrador_propio_descartado_se_puede_generar_de_nuevo(api):
    assert _hacer_borrador(api, UNO)["resultados"][0]["estado"] == "borr"
    fila = {f["agencia"]: f for f in api.preparar_revision("recordatorio", "2026-10-14")["datos"]["filas"]}["AG. UNO"]
    assert fila["veredicto"] == "lista" and "borrador suyo" in fila["motivo"]
    assert any("Elimine el borrador anterior" in a for a in fila["advertencias"])
    assert _hacer_borrador(api, UNO)["resultados"][0]["estado"] == "borr"
    assert len(api._puerta.creados) == 2


def test_un_inicio_en_borrador_tambien_se_puede_volver_a_generar(api):
    inicio = {"agencia": "AG. UNO", "tipo": "inicio"}
    assert _hacer_borrador(api, inicio)["resultados"][0]["estado"] == "borr"
    fila = {f["agencia"]: f for f in api.preparar_revision("inicio", None)["datos"]["filas"]}["AG. UNO"]
    assert fila["veredicto"] == "lista"


def test_un_borrador_de_otra_persona_sigue_omitiendo_el_aviso(api):
    _otra_persona(api, EstadoAviso.BORRADOR)
    fila = {f["agencia"]: f for f in api.preparar_revision("recordatorio", "2026-10-14")["datos"]["filas"]}["AG. UNO"]
    assert fila["veredicto"] == "omitida" and "rosa" in fila["motivo"]


def test_un_envio_ya_hecho_nunca_se_repite(api):
    lote = api.confirmar_envio([UNO], "enviar")["datos"]["lote"]
    _esperar(api, lote)
    fila = {f["agencia"]: f for f in api.preparar_revision("recordatorio", "2026-10-14")["datos"]["filas"]}["AG. UNO"]
    assert fila["veredicto"] == "omitida"


def test_la_copia_fija_trae_a_la_jefatura_y_al_area_de_origen(api):
    cc = _vista(api)["cc"]
    for correo in ("jefe@bn.com.pe", "integrante1@bn.com.pe", "integrante2@bn.com.pe", "integrante3@bn.com.pe"):
        assert correo in cc
    assert "admin_uno@bn.com.pe" in cc and "otro_uno@bn.com.pe" in cc      # la copia propia de la agencia se conserva
    assert len(cc) == len({c.lower() for c in cc}) == 6      # y nadie se repite
