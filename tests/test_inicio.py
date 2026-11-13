"""Correo de inicio de campaña: revisión, envío, respaldo y anulación."""

import json
import time
from datetime import date
from pathlib import Path

from agente_correos.correo.respaldo_red import RespaldoRed
from agente_correos.dominio.avisos import TipoAviso
from agente_correos.dominio.campana import Campana

from test_api import _esperar
from test_primer_uso import api  # noqa: F401  (fixture)

INICIO_UNO = {"agencia": "AG. UNO", "tipo": "inicio"}
CAMPANA = "JULIO – AGOSTO 2026"


def _carpeta_respaldo(tmp_path, agencia="AG._UNO"):
    return tmp_path / "BACKUP_CORREOS" / "2026" / CAMPANA / agencia


def _filas(api_):
    return {f["agencia"]: f for f in api_.preparar_revision("inicio", None)["datos"]["filas"]}


def test_la_revision_del_inicio_incluye_a_todas_las_agencias_sin_buscar_hilos(api):
    filas = _filas(api)
    assert filas["AG. UNO"]["veredicto"] == "lista" and filas["AG. UNO"]["hilo"]["estado"] == "no_aplica"
    assert filas["AG. CUATRO"]["veredicto"] == "bloqueada"


def test_un_inicio_con_respaldo_de_v1_u_otra_persona_se_omite(api, tmp_path):
    carpeta = _carpeta_respaldo(tmp_path)
    carpeta.mkdir(parents=True)
    (carpeta / "metadata.json").write_text(json.dumps({"saved_at": "2026-09-07T09:42:00"}))
    api._invalidar()
    fila = _filas(api)["AG. UNO"]
    assert fila["veredicto"] == "omitida" and "respaldo del inicio del 07/09/2026" in fila["motivo"]
    assert _filas(api)["AG. DOS"]["veredicto"] == "lista"


def test_el_servidor_tambien_rechaza_un_inicio_que_ya_tiene_respaldo(api, tmp_path):
    carpeta = _carpeta_respaldo(tmp_path)
    carpeta.mkdir(parents=True)
    (carpeta / "metadata.json").write_text(json.dumps({"saved_at": "2026-09-07T09:42:00"}))
    api._invalidar()
    lote = api.confirmar_envio([INICIO_UNO], "enviar")["datos"]["lote"]
    p = _esperar(api, lote)
    assert p["resultados"][0]["estado"] == "omit" and not api._puerta.creados


def test_enviar_el_inicio_arma_un_correo_nuevo_con_el_excel_y_deja_respaldo(api, tmp_path):
    lote = api.confirmar_envio([INICIO_UNO], "enviar")["datos"]["lote"]
    p = _esperar(api, lote)
    assert p["resultados"][0]["estado"] == "env"
    correo = api._puerta.creados[0][0]
    assert correo.tipo is TipoAviso.INICIO and correo.modo == "nuevo" and correo.adjuntos
    assert not correo.asunto.startswith("RECORDATORIO") and "AG. UNO" in correo.asunto
    assert (_carpeta_respaldo(tmp_path) / "metadata.json").is_file()
    celda = {a["nombre"]: a for a in api.estado_campana(True)["datos"]["agencias"]}["AG. UNO"]["celdas"]["inicio"]
    assert celda["estado"] == "env"
    assert _filas(api)["AG. UNO"]["veredicto"] == "omitida"                       # no se repite


def test_anular_un_inicio_retira_su_respaldo_y_permite_reenviarlo(api, tmp_path):
    lote = api.confirmar_envio([INICIO_UNO], "enviar")["datos"]["lote"]
    _esperar(api, lote)
    assert (_carpeta_respaldo(tmp_path) / "metadata.json").is_file()
    assert api.anular_envio(lote)["datos"]["anulados"] == 1
    assert not (_carpeta_respaldo(tmp_path) / "metadata.json").exists()
    assert _filas(api)["AG. UNO"]["veredicto"] == "lista"
    celda = {a["nombre"]: a for a in api.estado_campana(True)["datos"]["agencias"]}["AG. UNO"]["celdas"]["inicio"]
    assert celda["estado"] == "hoy"


def test_retirar_no_toca_un_respaldo_antiguo(tmp_path):
    campana = Campana.desde_archivo("ENTREGA DE FONDOS ETV JA 2026 difusion.xlsx")
    red = RespaldoRed(tmp_path / "BACKUP_CORREOS")
    carpeta = red.destino(campana, "AG. UNO")
    carpeta.mkdir(parents=True)
    (carpeta / "metadata.json").write_text(json.dumps({"saved_at": "2026-09-07T09:42:00"}))
    assert red.retirar(campana, "AG. UNO") is False and (carpeta / "metadata.json").is_file()


def test_avanzada_la_campana_un_inicio_sin_registro_figura_como_vencido(api):
    api._hoy = lambda: date(2026, 12, 1)
    api._invalidar()
    celda = {a["nombre"]: a for a in api.estado_campana()["datos"]["agencias"]}["AG. UNO"]["celdas"]["inicio"]
    assert celda["estado"] == "venc"


def test_con_la_campana_en_curso_el_inicio_sin_registrar_sigue_pendiente(api):
    api._hoy = lambda: date(2026, 10, 16)               # ya pasó el primer aviso, pero quedan pagos por avisar
    api._invalidar()
    e = api.estado_campana()["datos"]
    assert e["objetivo"] is not None
    celda = {a["nombre"]: a for a in e["agencias"]}["AG. UNO"]["celdas"]["inicio"]
    assert celda["estado"] == "hoy"
