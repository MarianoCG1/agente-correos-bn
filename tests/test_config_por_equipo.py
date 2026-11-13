"""Lo propio de cada equipo no se comparte; y el aviso cuando llega la entrega de la campaña siguiente."""

import json
import shutil
from datetime import date

from agente_correos.ui.api import Api

from test_api import DialogosFalsos, PuertaFalsa
from test_primer_uso import api  # noqa: F401  (fixture)

HOY = date(2026, 10, 13)


def _otro_equipo(tmp_path, nombre="otra_pc"):
    """Otra PC: su propia carpeta local y la misma carpeta compartida."""
    locales = tmp_path / nombre
    locales.mkdir()
    (locales / "local.json").write_text(json.dumps({"carpeta_compartida": str(tmp_path / "compartida")}))
    return Api(puerta=PuertaFalsa(), hoy=lambda: HOY, datos_locales=locales, dialogos=DialogosFalsos(),
               carpetas_agencias=[])


def test_las_rutas_del_equipo_no_viajan_a_la_carpeta_compartida(api, tmp_path):
    api.config_guardar({"carpeta_entrega": "C:/Users/ana/Downloads", "minutos_anulacion": 7})
    compartido = json.loads((tmp_path / "compartida" / "config.json").read_text(encoding="utf-8"))["valores"]
    assert compartido["carpeta_entrega"] == "" and compartido["cronograma_path"] == ""
    assert compartido["minutos_anulacion"] == 7                                  # lo compartido sí se comparte
    propio = json.loads((api._locales / "local.json").read_text(encoding="utf-8"))
    assert propio["carpeta_entrega"] == "C:/Users/ana/Downloads"

    otra = _otro_equipo(tmp_path)
    valores = otra.config_obtener()["datos"]["valores"]
    assert valores["carpeta_entrega"] == "" and valores["minutos_anulacion"] == 7


def test_una_ruta_local_que_quedo_en_lo_compartido_se_ignora(tmp_path):
    compartida = tmp_path / "compartida"
    compartida.mkdir()
    (compartida / "config.json").write_text(json.dumps({
        "version": 3, "valores": {"cronograma_path": "C:/Users/otra/Downloads/a.xlsx", "minutos_anulacion": 5},
        "historial": []}), encoding="utf-8")
    valores = _otro_equipo(tmp_path).config_obtener()["datos"]["valores"]
    assert valores["cronograma_path"] == "" and valores["minutos_anulacion"] == 5


def test_los_cambios_del_equipo_quedan_en_el_historial(api):
    api.config_guardar({"carpeta_entrega": "D:/entregas"})
    historial = api.config_obtener()["datos"]["historial"]
    assert any(c["campo"] == "carpeta_entrega" and c["despues"] == "D:/entregas" for c in historial)


def test_cambiar_la_carpeta_compartida_pide_reiniciar(api, tmp_path):
    assert api.config_guardar({"carpeta_compartida": str(tmp_path / "otra")})["datos"]["reiniciar"] is True
    assert api.config_guardar({"minutos_anulacion": 3})["datos"]["reiniciar"] is False


def test_cada_ruta_dice_si_es_de_este_equipo_o_de_todos(api):
    por = {r["campo"]: r["alcance"] for r in api.config_obtener()["datos"]["rutas"]}
    assert por["cronograma_path"] == "equipo" and por["carpeta_entrega"] == "equipo"
    assert por["respaldo_path"] == "compartida"


def test_avisa_cuando_hay_una_entrega_de_una_campana_posterior(api, crono_path, tmp_path, monkeypatch):
    monkeypatch.setattr("agente_correos.ui.api.RAIZ_SUGERIDA", str(tmp_path / "sin_sharepoint"))
    assert api.estado_campana()["datos"]["entrega_nueva"] is None

    nueva = tmp_path / "ENTREGA DE FONDOS ETV SO 2026 difusion.xlsx"
    shutil.copy(crono_path, nueva)
    aviso = api.estado_campana(True)["datos"]["entrega_nueva"]
    assert aviso["archivo"] == nueva.name

    assert api.entrega_cambiar(aviso["ruta"])["ok"] is True
    assert api.iniciar()["datos"]["entrega_archivo"] == nueva.name
    assert api.estado_campana(True)["datos"]["entrega_nueva"] is None             # ya la usa: no vuelve a avisar


def test_no_se_puede_cambiar_a_un_archivo_que_no_existe(api, tmp_path):
    r = api.entrega_cambiar(str(tmp_path / "no_esta.xlsx"))
    assert r["ok"] is False and "ya no está" in r["error"]
