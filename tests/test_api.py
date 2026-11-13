"""La Api de la interfaz, con puerta y diálogos simulados y una carpeta compartida temporal."""

import base64
import json
import time
from datetime import date
from pathlib import Path

import pytest

from agente_correos.configuracion import Configuracion
from agente_correos.correo.modelos import IdentidadOutlook, ResultadoPuerta
from agente_correos.ui.api import Api

HOY = date(2026, 10, 13)


class PuertaFalsa:
    def __init__(self):
        self.creados, self.anulados = [], []

    def disponible(self): return True
    def identidad(self): return IdentidadOutlook("Ana Pérez", "ana@bn.com.pe", "Practicante")
    def buscar_enviados(self, asunto): return []
    def verificar(self, id_outlook): return {"existe": True}

    def anular(self, correos):
        self.anulados.extend(correos)
        return len(correos)

    def crear(self, correo, accion, diferir_minutos=0, prueba_para=""):
        self.creados.append((correo, accion, diferir_minutos, prueba_para))
        return ResultadoPuerta(f"ID{len(self.creados)}", "; ".join(correo.para), "; ".join(correo.cc))


class DialogosFalsos:
    def abrir_archivo(self, carpeta=""): return None
    def elegir_carpeta(self, carpeta=""): return None
    def guardar_como(self, nombre, carpeta="", tipos=()): return ""


@pytest.fixture
def api(tmp_path, crono_path, agencias_path):
    locales = tmp_path / "locales"
    locales.mkdir()
    (locales / "local.json").write_text(json.dumps({"carpeta_compartida": str(tmp_path / "compartida")}))
    a = Api(puerta=PuertaFalsa(), hoy=lambda: HOY, datos_locales=locales, dialogos=DialogosFalsos(),
            carpetas_agencias=[])
    a._cfg_repo.guardar(Configuracion(cronograma_path=str(crono_path), agencias_path=str(agencias_path),
                                      respaldo_path=str(tmp_path / "BACKUP_CORREOS")))
    a.agencias_importar()
    a.perfil_guardar({"nombre": "Ana Pérez", "cargo": "Practicante", "anexo": "12345"})
    return a


def _esperar(api, lote, segundos=10):
    fin = time.time() + segundos
    while time.time() < fin:
        p = api.progreso(lote)["datos"]
        if p["terminado"]:
            return p
        time.sleep(0.05)
    raise AssertionError("El lote no terminó")


UNO = {"agencia": "AG. UNO", "tipo": "recordatorio", "fecha": "2026-10-14"}
DOS = {"agencia": "AG. DOS", "tipo": "recordatorio", "fecha": "2026-10-14"}


def test_respuestas_siempre_traen_ok(api):
    for r in (api.iniciar(), api.estado_campana(), api.config_obtener(), api.agencias_listar(), api.historial()):
        assert set(r) <= {"ok", "datos", "error"} and r["ok"] is True
    malo = api.progreso("noexiste")
    assert malo["ok"] is False and "desconocido" in malo["error"]


def test_iniciar(api):
    d = api.iniciar()["datos"]
    assert d["outlook"] and d["compartida_ok"] and d["hay_entrega"] and d["hay_agencias"] and d["perfil_completo"]
    assert d["hoy"] == "2026-10-13" and d["minutos_anulacion"] == 2


def test_estado_de_la_campana_para_el_tablero(api):
    e = api.estado_campana()["datos"]
    assert e["campana"] == "JULIO – AGOSTO 2026" and e["objetivo"] == "2026-10-14"
    assert e["aviso_objetivo"] == "2026-10-13" and e["coherencia"] is None
    ags = {a["nombre"]: a for a in e["agencias"]}
    assert ags["AG. UNO"]["celdas"]["2026-10-14"]["estado"] == "hoy"
    assert ags["AG. UNO"]["celdas"]["2026-10-19"]["estado"] == "pend"
    assert ags["AG. CUATRO"]["celdas"]["2026-10-14"]["estado"] == "bloq" and ags["AG. CUATRO"]["sin_correo"]
    assert ags["AG. UNO"]["celdas"]["inicio"]["estado"] == "hoy"         # al comienzo de la campaña, el inicio se prepara
    assert ags["AG. TRES"]["etvs"] == ["PROSEGUR"]


def test_el_respaldo_de_v1_cuenta_como_inicio_enviado(api, tmp_path):
    carpeta = tmp_path / "BACKUP_CORREOS" / "2026" / "JULIO – AGOSTO 2026" / "AG._UNO"
    carpeta.mkdir(parents=True)
    (carpeta / "metadata.json").write_text(json.dumps({"saved_at": "2026-09-07T09:42:00"}))
    api._invalidar()
    celda = {a["nombre"]: a for a in api.estado_campana()["datos"]["agencias"]}["AG. UNO"]["celdas"]["inicio"]
    assert celda["estado"] == "env" and "07/09/2026" in celda["motivo"]


def test_revision_previa(api):
    r = api.preparar_revision("recordatorio", "2026-10-14")["datos"]
    por = {f["agencia"]: f for f in r["filas"]}
    assert por["AG. UNO"]["veredicto"] == "lista" and por["AG. UNO"]["hilo"]["estado"] == "ninguno"
    assert por["AG. CUATRO"]["veredicto"] == "bloqueada" and "no figura" in por["AG. CUATRO"]["motivo"]
    assert por["AG. DOS"]["advertencias"]


def test_vista_previa_es_el_correo_real(api):
    v = api.vista_previa("AG. UNO", "recordatorio", "2026-10-14")["datos"]
    assert v["asunto"] == "RECORDATORIO: Entrega de Fondos – BN AG. UNO – JULIO – AGOSTO 2026"
    assert "el día de mañana" in v["html"] and "Practicante - Ana Pérez" in v["html"]
    assert v["para"] == ["jpago_uno@bn.com.pe"] and v["modo"] == "nuevo" and v["adjunto"]["filas"] == 2


def test_envio_en_segundo_plano_y_estado_en_el_tablero(api):
    lote = api.confirmar_envio([UNO, DOS], "enviar")["datos"]["lote"]
    p = _esperar(api, lote)
    assert [r["estado"] for r in p["resultados"]] == ["env", "env"] and p["anulable_hasta"]
    assert [(c[1], c[2]) for c in api._puerta.creados] == [("enviar", 2), ("enviar", 2)]
    celda = {a["nombre"]: a for a in api.estado_campana()["datos"]["agencias"]}["AG. UNO"]["celdas"]["2026-10-14"]
    assert celda["estado"] == "env"
    assert {f["agencia"] for f in api.historial()["datos"]["filas"]} == {"AG. UNO", "AG. DOS"}


def test_anular_un_envio_con_espera(api):
    lote = api.confirmar_envio([UNO], "enviar")["datos"]["lote"]
    _esperar(api, lote)
    r = api.anular_envio(lote)["datos"]
    assert r["anulados"] == 1 and api._puerta.anulados[0][0].startswith("RECORDATORIO:")
    celda = {a["nombre"]: a for a in api.estado_campana()["datos"]["agencias"]}["AG. UNO"]["celdas"]["2026-10-14"]
    assert celda["estado"] == "hoy"                                         # vuelve a estar pendiente
    assert api.anular_envio(lote)["ok"] is False                            # no se anula dos veces


def test_borrador_no_lleva_espera(api):
    lote = api.confirmar_envio([UNO], "borrador")["datos"]["lote"]
    p = _esperar(api, lote)
    assert p["resultados"][0]["estado"] == "borr" and p["anulable_hasta"] is None
    assert api._puerta.creados[0][1:3] == ("borrador", 0)


def test_sin_carpeta_compartida_no_envia(api):
    api._compartida_ok = False
    r = api.confirmar_envio([UNO], "enviar")
    assert r["ok"] is False and "no se puede enviar" in r["error"]


def test_prueba_a_uno_mismo(api):
    r = api.enviarme_prueba("AG. UNO", "recordatorio", "2026-10-14")["datos"]
    assert r["enviado_a"] == "ana@bn.com.pe"
    assert api._puerta.creados[-1][1] == "prueba" and api._puerta.creados[-1][3] == "ana@bn.com.pe"


def test_agencias_editables_y_auditadas(api):
    assert api.agencia_agregar("AG. NUEVA", ["jpago_nueva@bn.com.pe"])["ok"]
    assert api.agencia_agregar("AG. NUEVA", ["x@bn.com.pe"])["ok"] is False
    assert api.agencia_actualizar("AG. NUEVA", ["otro@bn.com.pe"], [])["ok"]
    malo = api.agencia_actualizar("AG. NUEVA", ["fuera@gmail.com"], [])
    assert malo["ok"] is False and "fuera de" in malo["error"]
    cambios = api.agencias_historial("AG. NUEVA")["datos"]["cambios"]
    assert [c["campo"] for c in cambios] == ["para", "alta"]
    api.agencia_estado("AG. NUEVA", False)
    activas = [a["nombre"] for a in api.agencias_listar(False)["datos"]["agencias"]]
    assert "AG. NUEVA" not in activas


def test_configuracion_con_rutas_e_historial(api, tmp_path):
    d = api.config_obtener()["datos"]
    campos = {r["campo"]: r for r in d["rutas"]}
    assert campos["cronograma_path"]["estado"] == "ok" and campos["carpeta_entrega"]["estado"] == "sin_configurar"
    assert api.config_guardar({"carpeta_entrega": str(tmp_path), "minutos_anulacion": 5})["datos"]["cambios"] == 2
    historial = api.config_obtener()["datos"]["historial"]
    assert {c["campo"] for c in historial} >= {"carpeta_entrega", "minutos_anulacion"}
    assert historial[0]["usuario"]


def test_perfil_detectado_de_outlook_y_firma(api):
    api._perfil_path().unlink()                                             # persona nueva
    p = api.perfil_obtener()["datos"]
    assert p["detectado_de"] == "outlook" and p["perfil"]["nombre"] == "Ana Pérez"
    assert p["perfil"]["email"] == "ana@bn.com.pe" and "Telf:" in p["firma_html"]
    assert api.perfil_guardar({"nombre": ""})["ok"] is False


def test_preparar_entrega_desde_el_original_arrastrado(api, tmp_path):
    from openpyxl import load_workbook
    wb = load_workbook(api._cfg.cronograma_path)          # la entrega sintética sirve de "original"
    ws = wb.active
    ws.cell(1, 15).value = "Preparación y ENTREGA DE FONDOS"      # grupo que el generador exige encontrar
    for n, fila in enumerate(range(3, 11), start=1):
        ws.cell(fila, 4).value = f"{n:04d}"                # código de pueblo único por punto
    original = tmp_path / "original.xlsx"
    wb.save(original)

    r = api.entrega_subir_original("CRONOGRAMA ETV JA 2026 difusion.xlsx",
                                   base64.b64encode(original.read_bytes()).decode())["datos"]
    assert r["nombre_sugerido"] == "ENTREGA DE FONDOS ETV JA 2026 difusion.xlsx" and r["filas"] == 8
    assert len(r["puntos"]) == 8 and r["token"]
    destino = tmp_path / "salida" / r["nombre_sugerido"]
    g = api.entrega_generar(r["token"], str(destino), [{"clave": r["puntos"][0]["clave"], "origen": "correo 10/09"}], [])
    assert g["ok"], g
    assert g["datos"]["filas_quitadas"] == 1 and destino.exists()
    cfg = api.config_obtener()["datos"]["valores"]
    assert cfg["cronograma_path"] == str(destino) and cfg["carpeta_entrega"] == str(destino.parent)
    assert api.estado_campana()["datos"]["archivo"] == destino.name


def test_puntos_repetidos_en_el_original_se_rechazan(api, tmp_path):
    original = Path(api._cfg.cronograma_path)              # todos con el mismo código
    r = api.entrega_subir_original("CRONOGRAMA ETV JA 2026 difusion.xlsx",
                                   base64.b64encode(original.read_bytes()).decode())["datos"]
    g = api.entrega_generar(r["token"], str(tmp_path / "x.xlsx"), [], [])
    assert g["ok"] is False and "repetidos" in g["error"]


def test_original_invalido_da_mensaje_claro(api):
    r = api.entrega_subir_original("malo.xlsx", base64.b64encode(b"no es excel").decode())
    assert r["ok"] is False and r["error"]
