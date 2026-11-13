"""Lo que se comparte entre personas: registro con reclamo, agencias editables y configuración auditada."""

from datetime import date, datetime, timedelta

import pytest

from agente_correos.configuracion import Configuracion
from agente_correos.datos.repositorio_agencias import (AgenciaInvalida, ConflictoEdicion, RepositorioAgencias)
from agente_correos.dominio.avisos import ClaveAviso, EstadoAviso, EventoAviso, TipoAviso
from agente_correos.historial.registro import RegistroEjecuciones
from agente_correos.reglas.preflight import PreflightValidator, Veredicto
from agente_correos.repositorio_configuracion import (ConflictoConfiguracion, RepositorioConfiguracion,
                                                      estado_de_rutas)

CAMPANA = "JULIO – AGOSTO 2026"
FECHA = date(2026, 10, 14)


def _clave(agencia="AG. UNO", fecha=FECHA):
    return ClaveAviso.crear(CAMPANA, agencia, TipoAviso.RECORDATORIO, fecha)


def _reloj(inicio=datetime(2026, 10, 13, 8, 0, 0)):
    ticks = iter(inicio + timedelta(seconds=i) for i in range(10_000))
    return lambda: next(ticks)


# ---- Registro: un archivo por persona -------------------------------------------
def test_cada_persona_escribe_su_propio_archivo(tmp_path):
    ana = RegistroEjecuciones(tmp_path, usuario="ana", reloj=_reloj())
    rosa = RegistroEjecuciones(tmp_path, usuario="rosa", reloj=_reloj(datetime(2026, 10, 13, 9)))
    ana.registrar(EventoAviso(_clave("AG. UNO"), EstadoAviso.ENVIADO))
    rosa.registrar(EventoAviso(_clave("AG. DOS"), EstadoAviso.ENVIADO))

    archivos = sorted(p.name for p in (tmp_path / CAMPANA).glob("*.json"))
    assert archivos == ["ana.json", "rosa.json"]
    assert {e.clave.agencia for e in ana.eventos(CAMPANA)} == {"AG. UNO", "AG. DOS"}     # ve lo de la otra
    assert [e.usuario for e in rosa.eventos(CAMPANA)] == ["ana", "rosa"]


def test_registrar_lote_escribe_una_sola_vez(tmp_path, monkeypatch):
    reg = RegistroEjecuciones(tmp_path, usuario="ana", reloj=_reloj())
    escrituras = []
    original = reg._escribir_propios
    monkeypatch.setattr(reg, "_escribir_propios", lambda c, ev: (escrituras.append(len(ev)), original(c, ev)))
    reg.registrar_lote(EventoAviso(_clave(f"AG. {i}"), EstadoAviso.BORRADOR) for i in range(5))
    assert escrituras == [5]


def test_un_envio_confirmado_prevalece_sobre_lo_que_llegue_despues(tmp_path):
    ana = RegistroEjecuciones(tmp_path, usuario="ana", reloj=_reloj())
    rosa = RegistroEjecuciones(tmp_path, usuario="rosa", reloj=_reloj(datetime(2026, 10, 13, 9)))
    ana.registrar(EventoAviso(_clave(), EstadoAviso.ENVIADO))
    rosa.registrar(EventoAviso(_clave(), EstadoAviso.ENVIADO))               # envío duplicado, posterior
    vigente = ana.estado_actual(_clave())
    assert vigente.usuario == "ana"                                           # cuenta el primero


# ---- Registro: reclamar antes de enviar -----------------------------------------
def test_reclamar_un_aviso_libre(tmp_path):
    ana = RegistroEjecuciones(tmp_path, usuario="ana", reloj=_reloj())
    r = ana.reclamar([_clave("AG. UNO"), _clave("AG. DOS")])
    assert len(r.obtenidas) == 2 and r.perdidas == {}
    assert ana.estado_actual(_clave("AG. UNO")).estado is EstadoAviso.ENVIANDO


def test_no_se_puede_reclamar_lo_que_otra_persona_ya_envio(tmp_path):
    rosa = RegistroEjecuciones(tmp_path, usuario="rosa", reloj=_reloj())
    rosa.registrar(EventoAviso(_clave(), EstadoAviso.ENVIADO))
    ana = RegistroEjecuciones(tmp_path, usuario="ana", reloj=_reloj(datetime(2026, 10, 13, 9)))
    r = ana.reclamar([_clave()])
    assert r.obtenidas == [] and r.perdidas[_clave()].usuario == "rosa"


def test_gana_quien_reclamo_primero_aunque_ambas_escriban_a_la_vez(tmp_path, monkeypatch):
    """Rosa reclama (08:00:00) justo después de que Ana revisó y antes de que Ana releyera."""
    ana = RegistroEjecuciones(tmp_path, usuario="ana", reloj=_reloj(datetime(2026, 10, 13, 8, 0, 5)))
    rosa = RegistroEjecuciones(tmp_path, usuario="rosa", reloj=_reloj(datetime(2026, 10, 13, 8, 0, 0)))

    escribir = ana._escribir_propios
    def con_carrera(campana, eventos):
        escribir(campana, eventos)
        if not getattr(con_carrera, "hecho", False):
            con_carrera.hecho = True
            rosa.registrar(EventoAviso(_clave(), EstadoAviso.ENVIANDO, detalle="reclamado"))
    monkeypatch.setattr(ana, "_escribir_propios", con_carrera)

    r = ana.reclamar([_clave()])
    assert r.obtenidas == [] and r.perdidas[_clave()].usuario == "rosa"
    # Ana retiró su reclamo: no queda ningún "enviando" suyo que tape el de Rosa
    assert [e.usuario for e in ana.eventos(CAMPANA) if e.estado is EstadoAviso.ENVIANDO] == ["rosa"]


def test_empate_exacto_se_resuelve_por_nombre(tmp_path, monkeypatch):
    mismo = datetime(2026, 10, 13, 8, 0, 0)
    ana = RegistroEjecuciones(tmp_path, usuario="ana", reloj=lambda: mismo)
    rosa = RegistroEjecuciones(tmp_path, usuario="rosa", reloj=lambda: mismo)
    escribir = rosa._escribir_propios
    def con_carrera(campana, eventos):
        escribir(campana, eventos)
        if not getattr(con_carrera, "hecho", False):
            con_carrera.hecho = True
            ana.registrar(EventoAviso(_clave(), EstadoAviso.ENVIANDO, detalle="reclamado"))
    monkeypatch.setattr(rosa, "_escribir_propios", con_carrera)
    r = rosa.reclamar([_clave()])
    assert r.obtenidas == [] and r.perdidas[_clave()].usuario == "ana"


def test_preflight_omite_lo_reclamado_por_otra_persona(cronograma, directorio, tmp_path, config):
    clave = ClaveAviso.crear(cronograma.campana.nombre, "AG. UNO", TipoAviso.RECORDATORIO, FECHA)
    RegistroEjecuciones(tmp_path / "r", usuario="rosa", reloj=_reloj()).registrar(
        EventoAviso(clave, EstadoAviso.ENVIADO))
    ana = RegistroEjecuciones(tmp_path / "r", usuario="ana", reloj=_reloj())
    res = {r.agencia: r for r in PreflightValidator(cronograma, directorio, ana, config)
           .evaluar(TipoAviso.RECORDATORIO, FECHA)}
    assert res["AG. UNO"].veredicto is Veredicto.OMITIDA and "rosa" in res["AG. UNO"].motivo


# ---- Agencias editables ------------------------------------------------------------
@pytest.fixture
def agencias(tmp_path):
    return RepositorioAgencias(tmp_path / "agencias.json", usuario="ana", reloj=_reloj())


def test_agregar_agencia_nueva_con_historial(agencias):
    agencias.agregar("AG. NUEVA", ["Jpago_Nueva@bn.com.pe"], ["admin_nueva@bn.com.pe"])
    reg = agencias.obtener("ag. nueva")
    assert reg.para == ["jpago_nueva@bn.com.pe"] and reg.activa
    cambio = agencias.historial("AG. NUEVA")[0]
    assert (cambio.usuario, cambio.campo, cambio.despues) == ("ana", "alta", "jpago_nueva@bn.com.pe")


def test_valida_correos_y_dominio(agencias):
    with pytest.raises(AgenciaInvalida, match="al menos un correo"):
        agencias.agregar("AG. X", [])
    with pytest.raises(AgenciaInvalida, match="formato inválido"):
        agencias.agregar("AG. X", ["no-es-correo"])
    with pytest.raises(AgenciaInvalida, match="fuera de @bn.com.pe"):
        agencias.agregar("AG. X", ["alguien@gmail.com"])
    assert agencias.obtener("AG. X") is None


def test_no_permite_duplicar_agencia(agencias):
    agencias.agregar("AG. UNO", ["a@bn.com.pe"])
    with pytest.raises(AgenciaInvalida, match="ya existe"):
        agencias.agregar("ag.  uno", ["b@bn.com.pe"])


def test_actualizar_guarda_antes_y_despues(agencias):
    agencias.agregar("AG. UNO", ["a@bn.com.pe"])
    agencias.actualizar("AG. UNO", para=["nuevo@bn.com.pe"], cc=["cc@bn.com.pe"])
    cambios = [(c.campo, c.antes, c.despues) for c in agencias.historial("AG. UNO")][1:]
    assert cambios == [("para", "a@bn.com.pe", "nuevo@bn.com.pe"), ("cc", "", "cc@bn.com.pe")]
    agencias.actualizar("AG. UNO", para=["nuevo@bn.com.pe"])           # sin cambio real: no anota nada
    assert len(agencias.historial("AG. UNO")) == 3


def test_desactivar_no_borra_y_sale_del_directorio(agencias):
    agencias.agregar("AG. UNO", ["a@bn.com.pe"])
    agencias.agregar("AG. DOS", ["b@bn.com.pe"])
    agencias.cambiar_estado("AG. UNO", False)
    assert [a.nombre for a in agencias.agencias()] == ["AG. DOS"]
    assert len(agencias.agencias(incluir_inactivas=True)) == 2
    assert agencias.a_directorio().existe("AG. UNO") is False
    agencias.cambiar_estado("AG. UNO", True)
    assert agencias.a_directorio().buscar("AG. UNO").para == ("a@bn.com.pe",)


def test_dos_personas_editando_a_la_vez(tmp_path):
    ruta = tmp_path / "agencias.json"
    ana = RepositorioAgencias(ruta, usuario="ana", reloj=_reloj())
    ana.agregar("AG. UNO", ["a@bn.com.pe"])
    rosa = RepositorioAgencias(ruta, usuario="rosa", reloj=_reloj())          # abre con la versión 1
    ana.actualizar("AG. UNO", cc=["x@bn.com.pe"])                              # versión 2
    with pytest.raises(ConflictoEdicion):
        rosa.actualizar("AG. UNO", cc=["y@bn.com.pe"])
    rosa.cargar()
    rosa.actualizar("AG. UNO", cc=["y@bn.com.pe"])                             # tras recargar, sí
    assert rosa.obtener("AG. UNO").cc == ["y@bn.com.pe"]


def test_importa_el_excel_de_v1_y_rechaza_lo_invalido(agencias, agencias_path):
    r = agencias.importar_xlsx(agencias_path)
    assert len(r.agregadas) == 3
    assert set(r.rechazadas) == {"AG. CINCO", "AG. SEIS", "AG. SIETE"}
    again = agencias.importar_xlsx(agencias_path)                              # segunda vez: nada cambia
    assert again.agregadas == [] and len(again.sin_cambio) == 3


def test_exportar_y_volver_a_importar(agencias, tmp_path):
    agencias.agregar("AG. UNO", ["a@bn.com.pe", "b@bn.com.pe"], ["c@bn.com.pe"], nota="nueva")
    xlsx = agencias.exportar_xlsx(tmp_path / "salida.xlsx")
    otro = RepositorioAgencias(tmp_path / "otro.json", usuario="ana", reloj=_reloj())
    otro.importar_xlsx(xlsx)
    assert otro.obtener("AG. UNO").para == ["a@bn.com.pe", "b@bn.com.pe"]


def test_preflight_usa_la_lista_editable(cronograma, agencias, registro, config):
    agencias.agregar("AG. UNO", ["jpago_uno@bn.com.pe"])
    res = {r.agencia: r for r in PreflightValidator(cronograma, agencias.a_directorio(), registro, config)
           .evaluar(TipoAviso.RECORDATORIO, FECHA)}
    assert res["AG. UNO"].veredicto is Veredicto.LISTA
    assert res["AG. DOS"].veredicto is Veredicto.BLOQUEADA and "no figura" in res["AG. DOS"].motivo


# ---- Configuración auditada ----------------------------------------------------------
def test_guardar_configuracion_registra_quien_y_que_cambio(tmp_path):
    repo = RepositorioConfiguracion(tmp_path / "config.json", usuario="ana", reloj=_reloj())
    nueva = Configuracion(carpeta_entrega="D:/entregas", dominio_interno="bn.com.pe")
    cambios = repo.guardar(nueva)
    assert [(c.campo, c.antes, c.despues, c.usuario) for c in cambios] == [("carpeta_entrega", "", "D:/entregas", "ana")]

    otra = Configuracion(carpeta_entrega="E:/entregas")
    repo.guardar(otra)
    h = repo.historial("carpeta_entrega")
    assert [(c.antes, c.despues) for c in h] == [("", "D:/entregas"), ("D:/entregas", "E:/entregas")]
    assert RepositorioConfiguracion(tmp_path / "config.json").configuracion.carpeta_entrega == "E:/entregas"


def test_guardar_sin_cambios_no_escribe(tmp_path):
    repo = RepositorioConfiguracion(tmp_path / "config.json", usuario="ana", reloj=_reloj())
    assert repo.guardar(Configuracion()) == []
    assert not (tmp_path / "config.json").exists()


def test_conflicto_si_otra_persona_guardo_antes(tmp_path):
    ruta = tmp_path / "config.json"
    ana = RepositorioConfiguracion(ruta, usuario="ana", reloj=_reloj())
    rosa = RepositorioConfiguracion(ruta, usuario="rosa", reloj=_reloj())
    ana.guardar(Configuracion(carpeta_entrega="A"))
    with pytest.raises(ConflictoConfiguracion):
        rosa.guardar(Configuracion(carpeta_entrega="B"))


def test_lee_la_configuracion_plana_de_antes(tmp_path):
    (tmp_path / "config.json").write_text('{"dominio_interno": "ejemplo.pe", "otro": 1}', encoding="utf-8")
    assert RepositorioConfiguracion(tmp_path / "config.json").configuracion.dominio_interno == "ejemplo.pe"


def test_estado_de_rutas(tmp_path):
    carpeta = tmp_path / "entregas"
    carpeta.mkdir()
    archivo = tmp_path / "entrega.xlsx"
    archivo.write_text("x")
    cfg = Configuracion(cronograma_path=str(archivo), carpeta_entrega=str(carpeta),
                        respaldo_path=str(tmp_path / "no_existe"), carpeta_original=str(archivo))
    estado = {e.campo: e for e in estado_de_rutas(cfg)}
    assert estado["cronograma_path"].correcta and estado["carpeta_entrega"].correcta
    assert estado["respaldo_path"].estado == "no_existe"
    assert estado["carpeta_original"].estado == "tipo_incorrecto"          # era un archivo, se esperaba carpeta
    assert estado["agencias_path"].estado == "sin_configurar"


def test_anulado_devuelve_el_aviso_a_estar_libre(tmp_path):
    ana = RegistroEjecuciones(tmp_path, usuario="ana", reloj=_reloj())
    ana.registrar(EventoAviso(_clave(), EstadoAviso.ENVIADO))
    assert ana.ya_avisado(_clave())
    ana.registrar(EventoAviso(_clave(), EstadoAviso.ANULADO))
    assert not ana.ya_avisado(_clave()) and ana.estado_actual(_clave()) is None
    ana.registrar(EventoAviso(_clave(), EstadoAviso.ENVIADO))                    # se puede volver a enviar
    assert ana.ya_avisado(_clave())


def test_solo_quien_envio_puede_anular(tmp_path):
    ana = RegistroEjecuciones(tmp_path, usuario="ana", reloj=_reloj())
    rosa = RegistroEjecuciones(tmp_path, usuario="rosa", reloj=_reloj(datetime(2026, 10, 13, 9)))
    ana.registrar(EventoAviso(_clave(), EstadoAviso.ENVIADO))
    rosa.registrar(EventoAviso(_clave(), EstadoAviso.ANULADO))                   # no es suyo: no tiene efecto
    assert ana.ya_avisado(_clave())


def test_eliminar_agencia_deja_rastro_en_el_historial(agencias):
    agencias.agregar("AG. UNO", ["a@bn.com.pe", "b@bn.com.pe"])
    agencias.agregar("AG. DOS", ["c@bn.com.pe"])
    agencias.eliminar("ag. uno")
    assert [a.nombre for a in agencias.agencias(incluir_inactivas=True)] == ["AG. DOS"]
    baja = agencias.historial("AG. UNO")[-1]
    assert (baja.campo, baja.antes, baja.usuario) == ("baja", "a@bn.com.pe; b@bn.com.pe", "ana")
    with pytest.raises(AgenciaInvalida):
        agencias.eliminar("AG. UNO")                         # ya no existe
    agencias.agregar("AG. UNO", ["nueva@bn.com.pe"])         # se puede volver a crear


def test_importar_json_suma_sin_pisar(tmp_path, agencias_path):
    origen = RepositorioAgencias(tmp_path / "origen.json", usuario="ana", reloj=_reloj())
    origen.importar_xlsx(agencias_path)
    origen.cambiar_estado("AG. TRES", False)
    destino = RepositorioAgencias(tmp_path / "destino.json", usuario="rosa", reloj=_reloj())
    destino.agregar("AG. UNO", ["propio@bn.com.pe"])                       # lo ya editado no se pisa
    r = destino.importar(tmp_path / "origen.json")
    assert sorted(r.sin_cambio) == ["AG. UNO"] and len(r.agregadas) == 2
    assert destino.obtener("AG. UNO").para == ["propio@bn.com.pe"]
    assert destino.obtener("AG. TRES").activa is False                     # conserva el estado de origen
