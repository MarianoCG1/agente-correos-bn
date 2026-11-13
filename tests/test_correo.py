"""Capa de correo con una puerta simulada: no se abre Outlook."""

import json
from datetime import date, datetime
from pathlib import Path

import pytest
from openpyxl import load_workbook

from agente_correos.correo.buscador_hilo import elegir_hilo, normalizar_asunto, sin_prefijos
from agente_correos.correo.constructor import ConstructorCorreo, insertar_en_cuerpo
from agente_correos.correo.modelos import CorreoPreparado, IdentidadOutlook, MensajeEncontrado, ResultadoPuerta
from agente_correos.correo.puerta import ErrorCorreo
from agente_correos.correo.respaldo_red import RespaldoRed, nombre_carpeta_agencia
from agente_correos.datos.excel_filtrador import ExcelFiltrador, FiltroError
from agente_correos.dominio.avisos import ClaveAviso, EstadoAviso, TipoAviso
from agente_correos.dominio.campana import Campana
from agente_correos.historial.registro import RegistroEjecuciones
from agente_correos.servicios.envio import EnvioService, SolicitudAviso
from agente_correos.usuario.perfil import PerfilUsuario

FECHA = date(2026, 10, 14)
HOY = date(2026, 10, 13)
CAMPANA = Campana("JA", 2026)


# ---- Hilo ---------------------------------------------------------------------
def _m(id, asunto, enviado=True, cuando=datetime(2026, 9, 1, 9)):
    return MensajeEncontrado(id=id, asunto=asunto, es_enviado=enviado, enviado_en=cuando)


def test_quita_prefijos_repetidos():
    assert sin_prefijos("RE: RV: Programación") == "Programación"
    assert normalizar_asunto("  rv:  Programación   de  Fondos ") == "PROGRAMACIÓN DE FONDOS"


def test_hilo_exacto_no_por_subcadena():
    asunto = "Programación de Fondos – BN LIMA – JULIO – AGOSTO 2026"
    otros = [_m("1", "Programación de Fondos – BN LIMA NORTE – JULIO – AGOSTO 2026")]
    assert elegir_hilo(otros, asunto).estado == "ninguno"                    # 'LIMA' no engancha 'LIMA NORTE'
    assert elegir_hilo(otros + [_m("2", asunto)], asunto).elegido.id == "2"


def test_ignora_los_recordatorios_y_prefiere_el_original():
    asunto = "Programación de Fondos – BN CUSCO – JULIO – AGOSTO 2026"
    msgs = [_m("r", "RECORDATORIO: " + asunto), _m("o", asunto), _m("f", "RV: " + asunto, enviado=False)]
    r = elegir_hilo(msgs, asunto)
    assert r.estado == "unico" and r.elegido.id == "o"


def test_dos_originales_es_ambiguo():
    asunto = "Programación de Fondos – BN CUSCO – JULIO – AGOSTO 2026"
    r = elegir_hilo([_m("a", asunto), _m("b", asunto, cuando=datetime(2026, 9, 2))], asunto)
    assert r.estado == "ambiguo" and [m.id for m in r.candidatos] == ["b", "a"]


# ---- Respaldo -----------------------------------------------------------------
def _escribir_respaldo(carpeta: Path, agencia="CUSCO", guardado="2026-09-01T09:00:00", excel=True):
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "cuerpo_principal.html").write_text(f"<p>cuerpo {guardado}</p>", encoding="utf-8")
    (carpeta / "metadata.json").write_text(json.dumps(
        {"campaign": CAMPANA.nombre, "agency": agencia, "subject": "Programación de Fondos – BN CUSCO",
         "to": "a@bn.com.pe; b@bn.com.pe", "cc": "", "sent_by": "rosa", "pc_name": "PC1",
         "saved_at": guardado, "excel_filename": "e.xlsx"}), encoding="utf-8")
    if excel:
        (carpeta / "e.xlsx").write_bytes(b"x")


def test_respaldo_lee_las_tres_ubicaciones_y_elige_la_mas_reciente(tmp_path):
    raiz = tmp_path / "ENTREGA"
    canonica = raiz / "BACKUP_CORREOS"
    nombre = CAMPANA.nombre
    _escribir_respaldo(raiz / "2026" / nombre / "CUSCO", guardado="2026-09-02T14:42:00")          # v1 apuntando a la entrega
    _escribir_respaldo(raiz / "2026" / "2026" / nombre / "CUSCO", guardado="2026-09-03T10:00:00")  # v1 apuntando al año
    _escribir_respaldo(canonica / "2026" / nombre / "CUSCO", guardado="2026-09-07T09:42:00")       # canónica
    r = RespaldoRed(canonica, [raiz]).buscar(CAMPANA, "Cusco")
    assert r.guardado_en == datetime(2026, 9, 7, 9, 42) and r.enviado_por == "rosa"
    assert r.para == ["a@bn.com.pe", "b@bn.com.pe"] and r.excel.name == "e.xlsx"


def test_respaldo_encuentra_lo_que_solo_esta_en_la_ubicacion_anterior(tmp_path):
    raiz = tmp_path / "ENTREGA"
    _escribir_respaldo(raiz / "2026" / CAMPANA.nombre / "AYACUCHO", agencia="AYACUCHO")
    assert RespaldoRed(raiz / "BACKUP_CORREOS", [raiz]).buscar(CAMPANA, "AYACUCHO") is not None
    assert RespaldoRed(raiz / "BACKUP_CORREOS", [raiz]).buscar(CAMPANA, "PUNO") is None


def test_respaldo_guarda_en_el_formato_de_v1(tmp_path):
    xlsx = tmp_path / "entrega.xlsx"
    xlsx.write_bytes(b"x")
    red = RespaldoRed(tmp_path / "BACKUP_CORREOS")
    carpeta = red.guardar(CAMPANA, "San Martín", "Asunto", ["a@bn.com.pe"], ["c@bn.com.pe"], "<p>hola</p>",
                          excel=xlsx, usuario="ana", equipo="PC9")
    assert carpeta == tmp_path / "BACKUP_CORREOS" / "2026" / CAMPANA.nombre / "SAN_MARTÍN"
    meta = json.loads((carpeta / "metadata.json").read_text(encoding="utf-8"))
    assert set(meta) == {"campaign", "agency", "subject", "to", "cc", "sent_by", "pc_name", "saved_at",
                         "excel_filename"}
    assert meta["sent_by"] == "ana" and (carpeta / "entrega.xlsx").exists()
    assert red.buscar(CAMPANA, "San Martín").html == "<p>hola</p>"
    assert nombre_carpeta_agencia("Ag. San  Martín/") == "AG._SAN__MARTÍN"


# ---- Excel de la agencia ---------------------------------------------------------
def test_excel_filtrado_solo_trae_la_agencia_y_los_encabezados(cronograma, tmp_path):
    destino = tmp_path / "uno.xlsx"
    n = ExcelFiltrador(cronograma).generar("AG. UNO", destino)
    ws = load_workbook(destino).active
    assert n == 2 and ws.max_row == 4                       # 2 de encabezado + 2 filas
    assert {ws.cell(r, 15).value for r in (3, 4)} == {"AG. UNO"}


def test_excel_filtrado_agencia_sin_filas(cronograma, tmp_path):
    with pytest.raises(FiltroError):
        ExcelFiltrador(cronograma).generar("AG. NO EXISTE", tmp_path / "x.xlsx")


# ---- Construcción ---------------------------------------------------------------
def test_insertar_en_cuerpo():
    assert insertar_en_cuerpo("<html><body><p>cita</p></body></html>", "<p>nuevo</p>").startswith(
        "<html><body><p>nuevo</p><br><br><p>cita</p>")
    assert insertar_en_cuerpo("", "<p>x</p>") == "<p>x</p><br><br>"


@pytest.fixture
def perfil():
    return PerfilUsuario(nombre="Ana Pérez", cargo="Practicante", anexo="12345", email="ana@bn.com.pe")


def test_recordatorio_en_hilo(cronograma, directorio, config, perfil):
    hilo = _m("H1", "Programación de Fondos – BN AG. UNO – JULIO – AGOSTO 2026")
    c = ConstructorCorreo(config).recordatorio(
        "AG. UNO", cronograma.filas("AG. UNO", FECHA), FECHA, HOY, CAMPANA, directorio.buscar("AG. UNO"),
        perfil, hilo=hilo)
    assert c.modo == "respuesta" and c.id_hilo == "H1"
    assert c.asunto == "RECORDATORIO: Programación de Fondos – BN AG. UNO – JULIO – AGOSTO 2026"
    assert "el día de mañana" in c.html and "Practicante - Ana Pérez" in c.html
    assert c.excluir == ["jefe@bn.com.pe"] and c.dominio == "bn.com.pe"


def test_recordatorio_reconstruido_desde_respaldo(cronograma, directorio, config, perfil, tmp_path):
    _escribir_respaldo(tmp_path / "2026" / CAMPANA.nombre / "AG._UNO", agencia="AG. UNO")
    respaldo = RespaldoRed(tmp_path).buscar(CAMPANA, "AG. UNO")
    c = ConstructorCorreo(config).recordatorio(
        "AG. UNO", cronograma.filas("AG. UNO", FECHA), FECHA, HOY, CAMPANA, directorio.buscar("AG. UNO"),
        perfil, respaldo=respaldo)
    assert c.modo == "reconstruido"
    assert c.asunto == "RECORDATORIO: Entrega de Fondos – BN AG. UNO – JULIO – AGOSTO 2026"
    assert "<b>De:</b> rosa" in c.html and "01/09/2026 09:00" in c.html and "cuerpo 2026-09-01" in c.html
    assert c.html.index("Practicante - Ana") < c.html.index("<b>De:</b>")      # la firma va antes de la cita


def test_recordatorio_sin_hilo_ni_respaldo_avisa(cronograma, directorio, config, perfil):
    c = ConstructorCorreo(config).recordatorio(
        "AG. UNO", cronograma.filas("AG. UNO", FECHA), FECHA, HOY, CAMPANA, directorio.buscar("AG. UNO"), perfil)
    assert c.modo == "nuevo" and c.advertencias and c.para == ["jpago_uno@bn.com.pe"]


def test_firma_de_outlook_o_ninguna(cronograma, directorio, config):
    args = ("AG. UNO", cronograma.filas("AG. UNO"), CAMPANA, directorio.buscar("AG. UNO"))
    c = ConstructorCorreo(config).inicio(*args, PerfilUsuario(nombre="Ana", modo_firma="outlook"))
    assert c.firma_outlook and "Telf:" not in c.html
    c = ConstructorCorreo(config).inicio(*args, PerfilUsuario(nombre="Ana", modo_firma="ninguna"))
    assert not c.firma_outlook and "Telf:" not in c.html


# ---- Servicio ------------------------------------------------------------------------
class PuertaFalsa:
    def __init__(self, hilos=None, falla_en=()):
        self.hilos = hilos or {}
        self.falla_en = set(falla_en)
        self.creados = []
        self.busquedas = []

    def disponible(self): return True
    def identidad(self): return IdentidadOutlook(nombre="Ana Pérez", correo="ana@bn.com.pe")
    def verificar(self, id_outlook): return {"existe": True}

    def buscar_enviados(self, asunto):
        self.busquedas.append(asunto)
        return self.hilos.get(asunto, [])

    def crear(self, correo, accion, diferir_minutos=0, prueba_para=""):
        if correo.agencia in self.falla_en:
            raise ErrorCorreo("Outlook no pudo resolver los destinatarios")
        self.creados.append((correo, accion, diferir_minutos))
        return ResultadoPuerta(f"ID-{len(self.creados)}", "; ".join(correo.para), "; ".join(correo.cc))


@pytest.fixture
def armar(cronograma, directorio, config, tmp_path, perfil):
    def _armar(puerta=None, usuario="ana", registro=None):
        puerta = puerta or PuertaFalsa()
        reg = registro or RegistroEjecuciones(tmp_path / "registro", usuario=usuario)
        svc = EnvioService(config, cronograma, directorio, reg, RespaldoRed(tmp_path / "BACKUP_CORREOS"),
                           puerta, perfil, hoy=lambda: HOY, carpeta_temporal=tmp_path / "tmp")
        return svc, puerta, reg
    return _armar


def _sol(ag, tipo=TipoAviso.RECORDATORIO, fecha=FECHA, hilo=None):
    return SolicitudAviso(ag, tipo, fecha if tipo is TipoAviso.RECORDATORIO else None, hilo)


def test_envia_los_listos_y_registra_cada_uno(armar):
    svc, puerta, reg = armar()
    res = svc.ejecutar([_sol("AG. UNO"), _sol("AG. DOS"), _sol("AG. CUATRO")], accion="enviar", diferir_minutos=2)
    assert [r.estado for r in res] == [EstadoAviso.ENVIADO, EstadoAviso.ENVIADO, EstadoAviso.BLOQUEADO]
    assert "no figura" in res[2].detalle
    assert [(c.agencia, a, d) for c, a, d in puerta.creados] == [("AG. UNO", "enviar", 2), ("AG. DOS", "enviar", 2)]
    assert reg.estado_actual(ClaveAviso.crear(CAMPANA.nombre, "AG. UNO", TipoAviso.RECORDATORIO, FECHA)
                             ).estado is EstadoAviso.ENVIADO
    svc.limpiar()


def test_el_adjunto_sale_de_la_entrega_vigente_con_solo_esa_agencia(armar):
    svc, puerta, _ = armar()
    svc.ejecutar([_sol("AG. UNO")], accion="borrador")
    correo = puerta.creados[0][0]
    assert correo.adjuntos[0].name == "ENTREGA DE FONDOS ETV JA 2026 difusion.xlsx"
    ws = load_workbook(correo.adjuntos[0]).active
    assert ws.max_row == 4                                  # 2 encabezados + las 2 filas de AG. UNO en la campaña
    svc.limpiar()


def test_no_envia_dos_veces_lo_mismo(armar):
    svc, puerta, _ = armar()
    svc.ejecutar([_sol("AG. UNO")])
    res = svc.ejecutar([_sol("AG. UNO")])
    assert res[0].estado is EstadoAviso.OMITIDO and len(puerta.creados) == 1


def test_no_envia_lo_que_otra_persona_ya_envio(armar, tmp_path):
    rosa, _, reg_r = armar(usuario="rosa")
    rosa.ejecutar([_sol("AG. UNO")])
    ana, puerta_ana, _ = armar(usuario="ana")
    res = ana.ejecutar([_sol("AG. UNO"), _sol("AG. DOS")])
    assert res[0].estado is EstadoAviso.OMITIDO and "rosa" in res[0].detalle
    assert res[1].estado is EstadoAviso.ENVIADO and len(puerta_ana.creados) == 1


def test_una_falla_no_detiene_a_las_demas_y_queda_registrada(armar):
    svc, puerta, reg = armar(PuertaFalsa(falla_en={"AG. UNO"}))
    res = svc.ejecutar([_sol("AG. UNO"), _sol("AG. DOS")])
    assert res[0].estado is EstadoAviso.ERROR and "resolver" in res[0].detalle
    assert res[1].estado is EstadoAviso.ENVIADO
    assert reg.ya_avisado(ClaveAviso.crear(CAMPANA.nombre, "AG. UNO", TipoAviso.RECORDATORIO, FECHA)) is False
    # tras el error se puede reintentar
    puerta.falla_en.clear()
    assert svc.ejecutar([_sol("AG. UNO")])[0].estado is EstadoAviso.ENVIADO


def test_hilo_ambiguo_pide_decision_y_devuelve_el_reclamo(armar):
    asunto = "Programación de Fondos – BN AG. UNO – JULIO – AGOSTO 2026"
    puerta = PuertaFalsa({asunto: [_m("a", asunto), _m("b", asunto, cuando=datetime(2026, 9, 2))]})
    svc, _, reg = armar(puerta)
    res = svc.ejecutar([_sol("AG. UNO")])
    assert res[0].estado is EstadoAviso.DECISION and puerta.creados == []
    assert reg.estado_actual(ClaveAviso.crear(CAMPANA.nombre, "AG. UNO", TipoAviso.RECORDATORIO, FECHA)) is None
    # con el hilo elegido sí sale
    res = svc.ejecutar([_sol("AG. UNO", hilo="b")])
    assert res[0].estado is EstadoAviso.ENVIADO and puerta.creados[0][0].id_hilo == "b"


def test_inicio_de_campana_guarda_el_respaldo(armar, tmp_path):
    svc, puerta, _ = armar()
    res = svc.ejecutar([_sol("AG. UNO", TipoAviso.INICIO)], accion="enviar")
    assert res[0].estado is EstadoAviso.ENVIADO
    r = RespaldoRed(tmp_path / "BACKUP_CORREOS").buscar(CAMPANA, "AG. UNO")
    assert r is not None and r.metadata["agency"] == "AG. UNO" and r.excel is not None
    assert r.asunto == "Programación de Fondos – BN AG. UNO – JULIO – AGOSTO 2026"
    svc.limpiar()


def test_el_recordatorio_de_otra_persona_se_reconstruye_con_el_respaldo(armar, tmp_path):
    rosa, _, _ = armar(usuario="rosa")
    rosa.ejecutar([_sol("AG. UNO", TipoAviso.INICIO)])                    # su inicio queda respaldado en la red
    ana, puerta, _ = armar(usuario="ana")                                 # Ana no tiene ese hilo en su Outlook
    res = ana.ejecutar([_sol("AG. UNO")])
    assert res[0].estado is EstadoAviso.ENVIADO and res[0].modo == "reconstruido"
    assert "<b>De:</b> rosa" in puerta.creados[0][0].html


def test_cancelar_devuelve_lo_que_falta(armar):
    svc, puerta, reg = armar()
    llamadas = iter([False, True])
    res = svc.ejecutar([_sol("AG. UNO"), _sol("AG. DOS")], cancelar=lambda: next(llamadas))
    assert [r.estado for r in res] == [EstadoAviso.ENVIADO, EstadoAviso.OMITIDO]
    assert reg.estado_actual(ClaveAviso.crear(CAMPANA.nombre, "AG. DOS", TipoAviso.RECORDATORIO, FECHA)) is None
