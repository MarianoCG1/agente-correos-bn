import json
from datetime import date, datetime
from pathlib import Path

from agente_correos.correo.ordenar_respaldos import aplicar, planificar, resumen
from agente_correos.correo.respaldo_red import RespaldoRed
from agente_correos.dominio.avisos import ClaveAviso, EstadoAviso, EventoAviso, TipoAviso
from agente_correos.dominio.campana import Campana
from agente_correos.historial.registro import RegistroEjecuciones

MJ, JA = "MAYO – JUNIO 2026", "JULIO – AGOSTO 2026"


def _resp(carpeta: Path, guardado: str):
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "cuerpo_principal.html").write_text("<p>x</p>", encoding="utf-8")
    (carpeta / "metadata.json").write_text(json.dumps({"saved_at": guardado, "agency": carpeta.name}))
    (carpeta / "entrega.xlsx").write_bytes(b"xlsx")


def _arbol(raiz: Path):
    """La misma forma que se vio en SharePoint: tres ubicaciones, una incompleta."""
    for ag in ("CUSCO", "PIURA", "ICA"):
        _resp(raiz / "2026" / MJ / ag, "2026-07-02T14:02:00")                 # v1 apuntando a la entrega
    for ag in ("CUSCO", "PIURA"):
        _resp(raiz / "2026" / "2026" / JA / ag, "2026-09-02T14:42:00")        # v1 apuntando al año
    _resp(raiz / "BACKUP_CORREOS" / "2026" / MJ / "PIURA", "2026-07-27T09:47:00")   # solo una en la de v2
    _resp(raiz / "BACKUP_CORREOS" / "2026" / JA / "CUSCO", "2026-09-07T09:42:00")   # más reciente que la anidada


def test_el_plan_describe_cada_caso_sin_tocar_nada(tmp_path):
    _arbol(tmp_path)
    antes = sorted(str(p) for p in tmp_path.rglob("*"))
    plan = planificar(tmp_path)
    assert sorted(str(p) for p in tmp_path.rglob("*")) == antes                # la simulación no escribe
    por = {(m.campana, m.agencia): m for m in plan}
    assert por[(MJ, "CUSCO")].accion == "copiar" and por[(MJ, "ICA")].accion == "copiar"
    assert por[(MJ, "PIURA")].accion == "ya_ordenado"                          # ya estaba en BACKUP_CORREOS
    assert por[(JA, "PIURA")].accion == "copiar"
    assert por[(JA, "CUSCO")].accion == "ya_ordenado"                          # el de v2 es más reciente
    assert resumen(plan) == {"copiar": 3, "ya_ordenado": 2, "conflicto": 0, "duplicado": 0}


def test_aplicar_copia_lo_que_falta_y_conserva_los_originales(tmp_path):
    _arbol(tmp_path)
    assert aplicar(planificar(tmp_path)) == 3
    destino = tmp_path / "BACKUP_CORREOS" / "2026"
    assert (destino / MJ / "CUSCO" / "metadata.json").is_file() and (destino / MJ / "ICA" / "entrega.xlsx").is_file()
    assert (destino / JA / "PIURA" / "cuerpo_principal.html").is_file()
    assert (tmp_path / "2026" / MJ / "CUSCO" / "metadata.json").is_file()      # el origen sigue ahí
    assert resumen(planificar(tmp_path))["copiar"] == 0                         # volver a correrlo no cambia nada


def test_no_pisa_un_respaldo_existente_aunque_el_origen_sea_mas_reciente(tmp_path):
    _resp(tmp_path / "2026" / MJ / "CUSCO", "2026-08-01T10:00:00")
    _resp(tmp_path / "BACKUP_CORREOS" / "2026" / MJ / "CUSCO", "2026-07-01T10:00:00")
    plan = planificar(tmp_path)
    assert plan[0].accion == "conflicto"
    assert aplicar(plan) == 0
    meta = json.loads((tmp_path / "BACKUP_CORREOS/2026" / MJ / "CUSCO/metadata.json").read_text())
    assert meta["saved_at"].startswith("2026-07-01")
    assert aplicar(plan, reemplazar_conflictos=True) == 1


def test_misma_agencia_en_dos_carpetas_antiguas_copia_solo_la_reciente(tmp_path):
    _resp(tmp_path / "2026" / MJ / "ICA", "2026-07-02T10:00:00")
    _resp(tmp_path / "2026" / "2026" / MJ / "ICA", "2026-07-20T10:00:00")
    plan = planificar(tmp_path)
    assert sorted(m.accion for m in plan) == ["copiar", "duplicado"]
    aplicar(plan)
    meta = json.loads((tmp_path / "BACKUP_CORREOS/2026" / MJ / "ICA/metadata.json").read_text())
    assert meta["saved_at"].startswith("2026-07-20")


def test_respaldo_red_encuentra_lo_ordenado_y_no_confunde_carpetas_del_programa(tmp_path):
    _arbol(tmp_path)
    aplicar(planificar(tmp_path))
    canonica = tmp_path / "BACKUP_CORREOS"
    (canonica / "2026" / JA / "_REGISTRO").mkdir(parents=True)                  # carpeta del programa dentro de la campaña
    (canonica / "_PROGRAMA").mkdir()
    red = RespaldoRed(canonica)                                                 # ya no necesita mirar las anteriores
    assert red.buscar(Campana("JA", 2026), "PIURA") is not None
    assert red.buscar(Campana("MJ", 2026), "ICA") is not None
    assert red.buscar(Campana("JA", 2026), "_REGISTRO") is None


def test_el_registro_vive_dentro_de_la_carpeta_de_la_campana(tmp_path):
    canonica = tmp_path / "BACKUP_CORREOS"
    reg = RegistroEjecuciones(tmp_path / "x", usuario="ana",
                              ruta_campana=lambda c: canonica / c.split(" ")[-1] / c / "_REGISTRO")
    clave = ClaveAviso.crear(JA, "CUSCO", TipoAviso.RECORDATORIO, date(2026, 10, 14))
    reg.registrar(EventoAviso(clave, EstadoAviso.ENVIADO))
    assert (canonica / "2026" / JA / "_REGISTRO" / "ana.json").is_file()
    assert not (tmp_path / "x").exists()                                        # no creó carpeta aparte
    assert reg.ya_avisado(clave)
