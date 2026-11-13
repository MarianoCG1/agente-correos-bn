"""Casos que aparecieron al usar la aplicación con los archivos reales del banco."""

import json
import os
import time
from datetime import date
from pathlib import Path

import pytest

from agente_correos.configuracion import Configuracion
from agente_correos.datos.cronograma_loader import elegir_hoja
from agente_correos.datos.entrega_vigente import mas_reciente
from agente_correos.ui.api import Api
from agente_correos.usuario.perfil import PerfilUsuario, separar_cargo_y_nombre

from test_api import DialogosFalsos, PuertaFalsa   # reutiliza las simulaciones


# ---- Hoja de trabajo --------------------------------------------------------------
def test_prefiere_la_hoja_cronograma_etv_aunque_la_original_vaya_primero():
    assert elegir_hoja(["CRONOGRAMA ETV_ORIGINAL", "CRONOGRAMA ETV", "Hoja1"]) == "CRONOGRAMA ETV"


def test_sin_hoja_exacta_evita_las_copias_de_referencia():
    assert elegir_hoja(["CRONOGRAMA ETV_ORIGINAL", "ETV trabajo"]) == "ETV trabajo"
    assert elegir_hoja(["PJ", "P65", "CRONOGRAMA ETV copia", "PAGOS 2026"]) == "PAGOS 2026"


def test_si_solo_hay_la_original_la_usa():
    assert elegir_hoja(["CRONOGRAMA ETV_ORIGINAL"]) == "CRONOGRAMA ETV_ORIGINAL"
    assert elegir_hoja(["Hoja1", "Hoja2"]) == "Hoja1"


# ---- Entrega vigente -----------------------------------------------------------------
def _crear(carpeta: Path, nombre: str, mtime: float = 0):
    p = carpeta / nombre
    p.write_bytes(b"x")
    if mtime:
        os.utime(p, (mtime, mtime))
    return p


def test_detecta_la_campana_mas_reciente_por_anio_y_orden(tmp_path):
    _crear(tmp_path, "ENTREGA DE FONDOS ETV MA 2026 difusion.xlsx", time.time())      # modificada ahora, pero antigua
    ja = _crear(tmp_path, "ENTREGA DE FONDOS ETV JA 2026 difusion.xlsx", 1_000_000)
    _crear(tmp_path, "ENTREGA DE FONDOS ETV ND 2025 difusion.xlsx", time.time())
    _crear(tmp_path, "~$ENTREGA DE FONDOS ETV SO 2026 difusion.xlsx")
    _crear(tmp_path, "prueba.xlsx")
    assert mas_reciente(tmp_path) == ja


def test_carpeta_inexistente_o_sin_entregas(tmp_path):
    assert mas_reciente(tmp_path / "no_existe") is None
    assert mas_reciente(tmp_path) is None


# ---- Nombre del perfil -------------------------------------------------------------------
def test_separa_el_cargo_que_viene_en_el_nombre_del_directorio():
    assert separar_cargo_y_nombre("PRACTICANTE - ANA BEATRIZ PEREZ QUISPE") == \
        ("Practicante", "Ana Beatriz Perez Quispe")
    assert separar_cargo_y_nombre("Ana B. Pérez Quispe") == ("", "Ana B. Pérez Quispe")
    assert separar_cargo_y_nombre("Ana Maria - Perez") == ("Ana Maria", "Perez")      # no se confunde con un cargo largo
    p = PerfilUsuario.inicial("PRACTICANTE - ANA BEATRIZ PEREZ QUISPE", "PRA_APEREZ@BN.COM.PE")
    assert (p.cargo, p.nombre, p.email) == ("Practicante", "Ana Beatriz Perez Quispe", "pra_aperez@bn.com.pe")


# ---- Api: archivo desactualizado y mensajes generales -------------------------------------
@pytest.fixture
def api_sin_entrega(tmp_path):
    locales = tmp_path / "locales"
    locales.mkdir()
    (locales / "local.json").write_text(json.dumps({"carpeta_compartida": str(tmp_path / "compartida")}))
    a = Api(puerta=PuertaFalsa(), hoy=lambda: date(2026, 10, 13), datos_locales=locales, dialogos=DialogosFalsos(),
            carpetas_agencias=[])
    return a


def test_si_la_entrega_configurada_ya_no_existe_usa_la_mas_reciente_de_su_carpeta(api_sin_entrega, tmp_path, crono_path):
    carpeta = tmp_path / "entregas"
    carpeta.mkdir()
    reciente = carpeta / "ENTREGA DE FONDOS ETV JA 2026 difusion.xlsx"
    reciente.write_bytes(Path(crono_path).read_bytes())
    api = api_sin_entrega
    api._cfg_repo.guardar(Configuracion(cronograma_path=str(carpeta / "ENTREGA DE FONDOS ETV MA 2026 difusion.xlsx")))
    r = api.estado_campana()
    assert r["ok"], r
    assert r["datos"]["archivo"] == reciente.name
    # quedó recordada, con su historial de cambios
    assert api._cfg.cronograma_path == str(reciente)
    assert any(c.campo == "cronograma_path" for c in api._cfg_repo.historial())


def test_los_mensajes_no_piden_un_archivo_concreto(api_sin_entrega, monkeypatch):
    api = api_sin_entrega
    monkeypatch.setattr(api, "_buscar_entrega", lambda: None)
    api._cfg_repo.guardar(Configuracion(cronograma_path="X:/ENTREGA DE FONDOS ETV MA 2026 difusion.xlsx"))
    r = api.estado_campana()
    assert r["ok"] is False
    for texto in ("MA 2026", ".xlsx", "ENTREGA DE FONDOS ETV", "agencias_correos"):
        assert texto not in r["error"]
    assert "Preparar entrega" in r["error"]


def test_importar_agencias_sin_archivo_da_mensaje_general(api_sin_entrega, monkeypatch):
    api = api_sin_entrega
    monkeypatch.setattr(api, "_ruta_agencias_v1", lambda: None)
    r = api.agencias_importar()
    assert r["ok"] is False and "agencias_correos" not in r["error"] and ".xlsx" not in r["error"]


def test_la_api_no_falla_al_ser_inspeccionada_antes_de_arrancar(tmp_path):
    """pywebview recorre los atributos de la Api al crear la ventana: no debe abrir la red ni fallar."""
    a = Api(puerta=PuertaFalsa(), datos_locales=tmp_path, diferir_arranque=True)
    for nombre in dir(a):
        getattr(a, nombre)                      # un AttributeError aquí era el error visto en el banco
    assert a._listo is False


# ---- La lista de agencias de v1 se convierte sola ----------------------------------------
def test_al_primer_arranque_convierte_el_excel_de_v1_a_json(tmp_path, agencias_path):
    locales = tmp_path / "locales"
    locales.mkdir()
    (locales / "local.json").write_text(json.dumps({"carpeta_compartida": str(tmp_path / "compartida")}))
    carpeta_data = tmp_path / "programa" / "data"
    carpeta_data.mkdir(parents=True)
    (carpeta_data / "agencias_correos.xlsx").write_bytes(Path(agencias_path).read_bytes())

    api = Api(puerta=PuertaFalsa(), datos_locales=locales, dialogos=DialogosFalsos(),
              carpetas_agencias=[tmp_path / "programa"])
    d = api.iniciar()["datos"]
    assert d["hay_agencias"] is True and "3 agencias" in d["aviso"]
    assert (tmp_path / "compartida" / "agencias.json").is_file()          # ya quedó como JSON, compartido
    nombres = {a["nombre"] for a in api.agencias_listar()["datos"]["agencias"]}
    assert {"AG. UNO", "AG. TRES"} <= nombres


def test_no_vuelve_a_importar_si_ya_hay_agencias(tmp_path, agencias_path):
    locales = tmp_path / "locales"
    locales.mkdir()
    (locales / "local.json").write_text(json.dumps({"carpeta_compartida": str(tmp_path / "compartida")}))
    carpeta = tmp_path / "programa"
    (carpeta / "data").mkdir(parents=True)
    (carpeta / "data" / "agencias_correos.xlsx").write_bytes(Path(agencias_path).read_bytes())
    primero = Api(puerta=PuertaFalsa(), datos_locales=locales, carpetas_agencias=[carpeta])
    primero.agencia_agregar("AG. NUEVA", ["x@bn.com.pe"])
    segundo = Api(puerta=PuertaFalsa(), datos_locales=locales, carpetas_agencias=[carpeta])
    assert segundo.iniciar()["datos"]["aviso"] == ""                          # no repite ni pisa lo editado
    assert any(a["nombre"] == "AG. NUEVA" for a in segundo.agencias_listar()["datos"]["agencias"])


def test_importar_escribe_una_sola_vez(tmp_path, agencias_path, monkeypatch):
    from agente_correos.datos.repositorio_agencias import RepositorioAgencias
    repo = RepositorioAgencias(tmp_path / "agencias.json", usuario="ana")
    escrituras = []
    original = repo._guardar
    monkeypatch.setattr(repo, "_guardar", lambda: (escrituras.append(1), original()))
    r = repo.importar_xlsx(agencias_path)
    assert len(r.agregadas) == 3 and len(escrituras) == 1                    # no una por agencia (SharePoint ~1 s c/u)


def test_toma_el_json_listo_y_se_puede_eliminar_desde_la_api(tmp_path, agencias_path):
    from agente_correos.datos.repositorio_agencias import RepositorioAgencias
    programa = tmp_path / "programa" / "data"
    programa.mkdir(parents=True)
    RepositorioAgencias(programa / "agencias.json", usuario="preparado").importar_xlsx(agencias_path)
    locales = tmp_path / "locales"
    locales.mkdir()
    (locales / "local.json").write_text(json.dumps({"carpeta_compartida": str(tmp_path / "compartida")}))
    api = Api(puerta=PuertaFalsa(), datos_locales=locales, carpetas_agencias=[tmp_path / "programa"])
    assert api.iniciar()["datos"]["hay_agencias"] is True
    assert api.agencia_eliminar("AG. UNO")["ok"] is True
    nombres = [a["nombre"] for a in api.agencias_listar()["datos"]["agencias"]]
    assert "AG. UNO" not in nombres and "AG. TRES" in nombres
    assert api.agencia_eliminar("AG. UNO")["ok"] is False
