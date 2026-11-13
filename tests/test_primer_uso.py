"""Primer uso, diagnóstico y confirmación de lectura."""

import json
import zipfile
from datetime import date

import pytest

from agente_correos import __version__
from agente_correos.configuracion import Configuracion
from agente_correos.correo.modelos import CorreoPreparado
from agente_correos.correo.outlook_gateway import OutlookGateway
from agente_correos.dominio.avisos import TipoAviso
from agente_correos.ui.api import Api

from test_api import DialogosFalsos, PuertaFalsa, UNO, _esperar

HOY = date(2026, 10, 13)


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


@pytest.fixture
def api_vacia(tmp_path):
    """Equipo recién instalado: sin entrega, sin agencias y sin perfil."""
    locales = tmp_path / "locales"
    locales.mkdir()
    (locales / "local.json").write_text(json.dumps({"carpeta_compartida": str(tmp_path / "compartida")}))
    a = Api(puerta=PuertaFalsa(), hoy=lambda: HOY, datos_locales=locales, dialogos=DialogosFalsos(),
            carpetas_agencias=[])
    a._cfg_repo.guardar(Configuracion(respaldo_path=str(tmp_path / "BACKUP_CORREOS"),
                                      carpeta_entrega=str(tmp_path / "sin_entregas")))
    return a


# ---- primer uso ---------------------------------------------------------
def test_equipo_recien_instalado_dice_que_falta(api_vacia, monkeypatch):
    monkeypatch.setattr(Api, "_buscar_entrega", lambda self: None)
    d = api_vacia.iniciar()["datos"]
    assert d["hay_entrega"] is False and d["entrega_archivo"] == ""
    assert d["hay_agencias"] is False and d["agencias_n"] == 0
    assert d["perfil_completo"] is False and d["compartida_ok"] is True
    assert d["version"] == __version__ and d["equipo"]
    e = api_vacia.estado_campana()
    assert e["ok"] is False and "entrega" in e["error"].lower()          # la interfaz muestra el panel de primeros pasos


def test_iniciar_informa_lo_que_ya_hay(api, crono_path):
    d = api.iniciar()["datos"]
    assert d["agencias_n"] >= 3 and d["entrega_archivo"] == crono_path.name


def test_elegir_una_entrega_existente_la_deja_vigente(api_vacia, crono_path, monkeypatch):
    monkeypatch.setattr(Api, "_buscar_entrega", lambda self: None)
    api_vacia._dialogos.abrir_archivo = lambda carpeta="": str(crono_path)
    r = api_vacia.entrega_usar_existente()["datos"]
    assert r["cancelado"] is False and r["archivo"] == crono_path.name and r["campana"]
    assert api_vacia.iniciar()["datos"]["hay_entrega"] is True
    cambios = {c["campo"] for c in api_vacia.config_obtener()["datos"]["historial"]}
    assert "cronograma_path" in cambios                                  # el cambio queda auditado


def test_cancelar_la_eleccion_no_cambia_nada(api_vacia, monkeypatch):
    monkeypatch.setattr(Api, "_buscar_entrega", lambda self: None)
    assert api_vacia.entrega_usar_existente()["datos"] == {"cancelado": True}
    assert api_vacia.iniciar()["datos"]["hay_entrega"] is False


def test_un_archivo_que_no_es_una_entrega_se_rechaza_con_mensaje(api_vacia, tmp_path, monkeypatch):
    monkeypatch.setattr(Api, "_buscar_entrega", lambda self: None)
    malo = tmp_path / "otro.xlsx"
    malo.write_bytes(b"no es un excel")
    api_vacia._dialogos.abrir_archivo = lambda carpeta="": str(malo)
    r = api_vacia.entrega_usar_existente()
    assert r["ok"] is False and r["error"]
    assert api_vacia.iniciar()["datos"]["hay_entrega"] is False


# ---- diagnóstico --------------------------------------------------------
def test_diagnostico_incluye_log_y_resumen_sin_correos(api, tmp_path):
    (api._locales / "agente_correos.log").write_text("INFO prueba\n", encoding="utf-8")
    destino = tmp_path / "diag.zip"
    api._dialogos.guardar_como = lambda nombre, carpeta="", tipos=(): str(destino)
    r = api.diagnostico_exportar()["datos"]
    assert r == {"cancelado": False, "ruta": str(destino)}
    with zipfile.ZipFile(destino) as z:
        assert {"resumen.txt", "agente_correos.log"} <= set(z.namelist())
        resumen = z.read("resumen.txt").decode("utf-8")
    assert __version__ in resumen and "Outlook disponible: True" in resumen and "Agencias cargadas:" in resumen
    assert "@bn.com.pe" not in resumen                                   # sin correos de agencias


def test_diagnostico_cancelado(api):
    assert api.diagnostico_exportar()["datos"] == {"cancelado": True}


# ---- confirmación de lectura -------------------------------------------
def test_la_revision_ofrece_el_valor_configurado(api):
    assert api.preparar_revision("recordatorio", "2026-10-14")["datos"]["confirmacion_lectura"] is True


def test_el_envio_pide_confirmacion_de_lectura_segun_la_casilla(api):
    lote = api.confirmar_envio([UNO], "enviar", True)["datos"]["lote"]
    _esperar(api, lote)
    lote = api.confirmar_envio([{**UNO, "agencia": "AG. DOS"}], "enviar", False)["datos"]["lote"]
    _esperar(api, lote)
    pedidos = [c[0].confirmar_lectura for c in api._puerta.creados]
    assert pedidos == [True, False]


def test_sin_indicacion_manda_lo_configurado(api):
    api.config_guardar({"confirmacion_lectura": False})
    lote = api.confirmar_envio([UNO], "enviar")["datos"]["lote"]
    _esperar(api, lote)
    assert api._puerta.creados[0][0].confirmar_lectura is False


# ---- OutlookGateway con un Outlook de mentira --------------------------
class _Recipientes:
    def __init__(self): self._r = []
    @property
    def Count(self): return len(self._r)
    def Item(self, i): return self._r[i - 1]
    def Add(self, n):
        class R: Resolved = True; Name = n
        self._r.append(R()); return self._r[-1]
    def Remove(self, i): del self._r[i - 1]
    def ResolveAll(self): return True


class _Adjuntos:
    def Add(self, ruta):
        class A:
            class PropertyAccessor:
                @staticmethod
                def SetProperty(*a): pass
        return A()


class _Item:
    def __init__(self):
        self.Subject, self.To, self.CC, self.HTMLBody = "", "", "", "<html><body></body></html>"
        self.Recipients, self.Attachments = _Recipientes(), _Adjuntos()
        self.EntryID, self.ReadReceiptRequested, self.enviado = "E1", False, False
        self.DeferredDeliveryTime = None

    def Save(self): pass
    def Send(self): self.enviado = True


class _App:
    def __init__(self): self.item = _Item()
    def CreateItem(self, _): return self.item


def _gateway():
    gw = OutlookGateway()
    gw._local.app = _App()
    return gw, gw._local.app


def _correo(lectura):
    return CorreoPreparado("AG. UNO", TipoAviso.RECORDATORIO, "RECORDATORIO: x", ["a@bn.com.pe"], [], "<p>hola</p>",
                           "nuevo", confirmar_lectura=lectura)


@pytest.mark.parametrize("accion,lectura,esperado", [
    ("enviar", True, True), ("enviar", False, False), ("borrador", True, True), ("prueba", True, False)])
def test_outlook_recibe_la_solicitud_de_confirmacion(accion, lectura, esperado):
    gw, app = _gateway()
    gw.crear(_correo(lectura), accion, prueba_para="yo@bn.com.pe" if accion == "prueba" else "")
    assert app.item.ReadReceiptRequested is esperado
    assert app.item.enviado is (accion != "borrador")


# ---- carpeta compartida y red lenta ---------------------------------------
def test_sin_ruta_elegida_la_compartida_es_la_de_backup_y_no_la_carpeta_actual(tmp_path, monkeypatch):
    from pathlib import Path
    backup = tmp_path / "BACKUP_CORREOS"
    otra = tmp_path / "desde_donde_se_ejecuta"
    otra.mkdir()
    monkeypatch.chdir(otra)
    monkeypatch.setattr(Api, "_base_respaldo_inicial", staticmethod(lambda: backup))
    monkeypatch.setattr(Api, "_buscar_entrega", lambda self: None)
    locales = tmp_path / "locales"
    locales.mkdir()                                                       # sin local.json
    a = Api(puerta=PuertaFalsa(), hoy=lambda: HOY, datos_locales=locales, dialogos=DialogosFalsos(),
            carpetas_agencias=[])
    d = a.iniciar()["datos"]
    assert Path(d["compartida"]) == backup / "_PROGRAMA" and d["compartida_ok"]
    assert list(otra.iterdir()) == []                                     # nada se escribe donde se ejecuta


def test_si_sharepoint_no_responde_la_ventana_no_se_queda_colgada(api_vacia, monkeypatch):
    import time
    monkeypatch.setattr("agente_correos.ui.api.ESPERA_RED", 0.2)
    monkeypatch.setattr(Api, "_buscar_entrega", lambda self: time.sleep(5))
    t0 = time.time()
    d = api_vacia.iniciar()["datos"]
    e = api_vacia.estado_campana()
    assert time.time() - t0 < 3
    assert d["red_lenta"] is True and d["hay_entrega"] is False
    assert e["ok"] is False and "no respondió" in e["error"]


def test_si_outlook_no_responde_el_arranque_continua(api, monkeypatch):
    import time
    monkeypatch.setattr("agente_correos.ui.api.ESPERA_OUTLOOK", 0.2)
    monkeypatch.setattr(api._puerta, "disponible", lambda: time.sleep(5))
    t0 = time.time()
    d = api.iniciar()["datos"]
    assert time.time() - t0 < 3
    assert d["outlook"] is False and d["outlook_lento"] is True and d["hay_agencias"]
