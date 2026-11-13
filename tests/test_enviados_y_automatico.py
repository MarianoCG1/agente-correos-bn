"""Revisión de la carpeta Enviados y envío automático supervisado (con Outlook simulado)."""

import json
from datetime import date, datetime, timedelta

import pytest

from agente_correos.configuracion import Configuracion
from agente_correos.contenido.plantillas import asunto_inicio, asunto_recordatorio
from agente_correos.correo.modelos import CorreoEnviado, IdentidadOutlook, MensajeEncontrado, ResultadoPuerta
from agente_correos.correo.respaldo_red import RespaldoRed
from agente_correos.dominio.avisos import ClaveAviso, EstadoAviso, EventoAviso, TipoAviso
from agente_correos.dominio.campana import Campana
from agente_correos.servicios.enviados import DETALLE, VerificadorEnviados, fecha_del_recordatorio
from agente_correos.servicios.envio import EnvioService, SolicitudAviso
from agente_correos.ui.api import Api
from agente_correos.usuario.perfil import PerfilUsuario

CAMPANA = Campana("JA", 2026)
NOMBRE = CAMPANA.nombre
FECHA = date(2026, 10, 14)
HOY = date(2026, 10, 13)
TEXTO_REC = "Estimado(a) buenos días, BN – AG. UNO. Se le recuerda que para el día de mañana 14 de octubre de 2026, se debe programar"


def _clave(agencia, tipo=TipoAviso.RECORDATORIO, fecha=FECHA):
    return ClaveAviso.crear(NOMBRE, agencia, tipo, fecha)


# ---- Lectura de la fecha ------------------------------------------------------------------
@pytest.mark.parametrize("texto,esperado", [
    (TEXTO_REC, date(2026, 10, 14)),
    ("Se le recuerda que para el lunes 05 de   noviembre\nde 2026, se debe", date(2026, 11, 5)),
    ("Se le recuerda que para el día de hoy 1 de setiembre de 2026", date(2026, 9, 1)),
    ("Se le recuerda que para el lunes 31 de febrero de 2026", None),
    ("Otro correo cualquiera", None),
    ("", None),
])
def test_fecha_del_recordatorio(texto, esperado):
    assert fecha_del_recordatorio(texto) == esperado


# ---- Verificador --------------------------------------------------------------------------
class PuertaEnviados:
    def __init__(self, enviados=(), hilos=None):
        self.enviados = list(enviados)
        self.hilos = hilos or {}
        self.creados, self.anulados = [], []
        self.consultas = []
        self.libre = True

    def disponible(self): return self.libre
    def identidad(self): return IdentidadOutlook("Ana Pérez", "ana@bn.com.pe", "Practicante")
    def verificar(self, id_outlook): return {"existe": True}
    def buscar_enviados(self, asunto): return self.hilos.get(asunto, [])

    def enviados_desde(self, fragmento, desde, omitir=None):
        self.consultas.append((fragmento, desde, set(omitir or ())))
        return [c for c in self.enviados if c.id not in (omitir or ())]

    def anular(self, correos):
        self.anulados.extend(correos)
        return len(correos)

    def crear(self, correo, accion, diferir_minutos=0, prueba_para=""):
        self.creados.append((correo, accion, diferir_minutos))
        return ResultadoPuerta(f"ID{len(self.creados)}", "; ".join(correo.para), "; ".join(correo.cc))


def _env(id, asunto, texto="", cuando=datetime(2026, 10, 13, 9, 0)):
    return CorreoEnviado(id, asunto, cuando, "jpago@bn.com.pe", texto)


@pytest.fixture
def verificador(cronograma, registro):
    def _armar(enviados, ahora=datetime(2026, 10, 13, 10, 0)):
        puerta = PuertaEnviados(enviados)
        return VerificadorEnviados(puerta, registro, cronograma, ahora=lambda: ahora), puerta
    return _armar


def test_un_inicio_enviado_a_mano_se_anota(verificador, registro):
    ver, _ = verificador([_env("a", asunto_inicio("AG. UNO", NOMBRE))])
    r = ver.revisar(datetime(2026, 10, 1))
    assert r.nuevos == ["AG. UNO · inicio"] and r.vistos == {"a"}
    ev = registro.estado_actual(_clave("AG. UNO", TipoAviso.INICIO, None))
    assert ev.estado is EstadoAviso.ENVIADO and ev.detalle == DETALLE and ev.id_outlook == "a"
    assert ev.creado_en == datetime(2026, 10, 13, 9, 0)                 # la hora real del envío


def test_un_recordatorio_se_reconoce_por_asunto_y_fecha_del_cuerpo(verificador, registro):
    en_hilo = "RECORDATORIO: " + asunto_inicio("AG. UNO", NOMBRE)         # respuesta en el hilo del inicio
    propio = asunto_recordatorio("AG. TRES", NOMBRE)                      # correo independiente
    ver, _ = verificador([_env("a", en_hilo, TEXTO_REC), _env("b", propio, TEXTO_REC)])
    r = ver.revisar(datetime(2026, 10, 1))
    assert sorted(r.nuevos) == ["AG. TRES · recordatorio del 14/10", "AG. UNO · recordatorio del 14/10"]
    assert registro.ya_avisado(_clave("AG. UNO")) and registro.ya_avisado(_clave("AG. TRES"))


def test_respuestas_pruebas_y_otros_correos_no_cuentan(verificador, registro):
    ver, _ = verificador([
        _env("a", "RE: " + asunto_inicio("AG. UNO", NOMBRE)),
        _env("b", "RV: " + asunto_inicio("AG. UNO", NOMBRE)),
        _env("c", "[PRUEBA] " + asunto_inicio("AG. UNO", NOMBRE)),
        _env("d", "Reunión del lunes"),
        _env("e", asunto_inicio("AG. INEXISTENTE", NOMBRE)),
    ])
    r = ver.revisar(datetime(2026, 10, 1))
    assert r.nuevos == [] and registro.eventos(NOMBRE) == [] and r.vistos == {"a", "b", "c", "d", "e"}


def test_un_recordatorio_sin_fecha_reconocible_no_se_inventa(verificador, registro):
    ver, _ = verificador([_env("a", asunto_recordatorio("AG. UNO", NOMBRE), "texto sin fecha"),
                          _env("b", asunto_recordatorio("AG. UNO", NOMBRE),
                               "Se le recuerda que para el lunes 02 de enero de 2026")])      # fecha sin pagos de la agencia
    r = ver.revisar(datetime(2026, 10, 1))
    assert r.nuevos == [] and r.sin_reconocer == 2 and registro.eventos(NOMBRE) == []


def test_no_repite_lo_que_el_programa_ya_envio_ni_lo_ya_detectado(verificador, registro):
    registro.registrar(EventoAviso(clave=_clave("AG. UNO", TipoAviso.INICIO, None), estado=EstadoAviso.ENVIADO))
    ver, _ = verificador([_env("a", asunto_inicio("AG. UNO", NOMBRE)), _env("b", asunto_inicio("AG. TRES", NOMBRE))])
    assert ver.revisar(datetime(2026, 10, 1)).nuevos == ["AG. TRES · inicio"]
    assert ver.revisar(datetime(2026, 10, 1)).nuevos == []              # segunda vuelta: ya figura
    assert len(registro.eventos(NOMBRE)) == 2


def test_dos_correos_del_mismo_aviso_se_anotan_una_vez(verificador, registro):
    ver, _ = verificador([_env("a", asunto_inicio("AG. UNO", NOMBRE)),
                          _env("b", asunto_inicio("AG. UNO", NOMBRE), cuando=datetime(2026, 10, 12, 9))])
    assert ver.revisar(datetime(2026, 10, 1)).nuevos == ["AG. UNO · inicio"]


def test_un_envio_del_programa_en_curso_se_deja_para_la_proxima_vuelta(verificador, registro):
    registro.registrar(EventoAviso(clave=_clave("AG. UNO", TipoAviso.INICIO, None), estado=EstadoAviso.ENVIANDO,
                                   creado_en=datetime(2026, 10, 13, 9, 58)))
    ver, _ = verificador([_env("a", asunto_inicio("AG. UNO", NOMBRE))])
    r = ver.revisar(datetime(2026, 10, 1))
    assert r.nuevos == [] and "a" not in r.vistos                       # se vuelve a mirar después


def test_una_vez_anotado_el_aviso_la_revision_previa_lo_omite(verificador, cronograma, directorio, config, registro):
    ver, _ = verificador([_env("a", "RECORDATORIO: " + asunto_inicio("AG. UNO", NOMBRE), TEXTO_REC)])
    ver.revisar(datetime(2026, 10, 1))
    from agente_correos.reglas.preflight import PreflightValidator, Veredicto
    r = PreflightValidator(cronograma, directorio, registro, config).evaluar(
        TipoAviso.RECORDATORIO, FECHA, agencias=["AG. UNO"])[0]
    assert r.veredicto is Veredicto.OMITIDA and "Ya se envió" in r.motivo


def test_los_ids_vistos_no_se_vuelven_a_pedir(verificador):
    ver, puerta = verificador([_env("a", "Reunión")])
    r = ver.revisar(datetime(2026, 10, 1))
    ver.revisar(datetime(2026, 10, 1), r.vistos)
    assert puerta.consultas[1][2] == {"a"} and puerta.consultas[0][0] == NOMBRE


# ---- Plan automático ---------------------------------------------------------------------
@pytest.fixture
def servicio(cronograma, directorio, config, tmp_path):
    def _armar(puerta, registro=None):
        from agente_correos.historial.registro import RegistroEjecuciones
        reg = registro or RegistroEjecuciones(tmp_path / "reg2", usuario="ana")
        return EnvioService(config, cronograma, directorio, reg, RespaldoRed(tmp_path / "BACKUP_CORREOS"), puerta,
                            PerfilUsuario(nombre="Ana Pérez", cargo="Practicante"), hoy=lambda: HOY,
                            carpeta_temporal=tmp_path / "tmp"), reg
    return _armar


def _hilo(agencia):
    asunto = asunto_inicio(agencia, NOMBRE)
    return {asunto: [MensajeEncontrado("h-" + agencia, asunto, enviado_en=datetime(2026, 9, 1), es_enviado=True)]}


def test_el_plan_separa_lo_que_sale_solo_de_lo_que_se_revisa_a_mano(servicio):
    svc, _ = servicio(PuertaEnviados(hilos=_hilo("AG. UNO")))
    plan = svc.plan_automatico([FECHA])
    assert [s.agencia for s in plan.listos] == ["AG. UNO"]
    motivos = {d.agencia: d.motivo for d in plan.descartados}
    assert "advertencias" in motivos["AG. DOS"] and "importe" in motivos["AG. DOS"]       # fila sin importe de Pensión 65
    assert "correo de inicio" in motivos["AG. TRES"]                                      # sin hilo ni respaldo
    assert "no figura" in motivos["AG. CUATRO"] and "fuera de" in motivos["AG. CINCO"]
    svc.limpiar()


def test_lo_ya_avisado_no_se_descarta_ni_se_repite(servicio):
    puerta = PuertaEnviados(hilos=_hilo("AG. UNO"))
    svc, _ = servicio(puerta)
    svc.ejecutar([SolicitudAviso("AG. UNO", TipoAviso.RECORDATORIO, FECHA)])
    plan = svc.plan_automatico([FECHA])
    assert plan.listos == [] and plan.ya_avisados == 1
    svc.limpiar()


def test_con_el_respaldo_en_red_tambien_sale_solo(servicio, tmp_path):
    svc, _ = servicio(PuertaEnviados())
    RespaldoRed(tmp_path / "BACKUP_CORREOS").guardar(CAMPANA, "AG. UNO", asunto_inicio("AG. UNO", NOMBRE),
                                                     ["jpago_uno@bn.com.pe"], [], "<p>inicio</p>")
    assert [s.agencia for s in svc.plan_automatico([FECHA]).listos] == ["AG. UNO"]
    svc.limpiar()


# ---- Modo automático en la Api ----------------------------------------------------------
class Reloj:
    def __init__(self, t): self.t = t
    def __call__(self): return self.t
    def avanzar(self, **kw): self.t += timedelta(**kw)


@pytest.fixture
def api(tmp_path, crono_path, agencias_path):
    locales = tmp_path / "locales"
    locales.mkdir()
    (locales / "local.json").write_text(json.dumps({"carpeta_compartida": str(tmp_path / "compartida")}))
    reloj = Reloj(datetime(2026, 10, 13, 7, 0))
    a = Api(puerta=PuertaEnviados(hilos=_hilo("AG. UNO")), hoy=lambda: reloj().date(), datos_locales=locales,
            dialogos=None, carpetas_agencias=[], ahora=reloj)
    a._cfg_repo.guardar(Configuracion(cronograma_path=str(crono_path), agencias_path=str(agencias_path),
                                      respaldo_path=str(tmp_path / "BACKUP_CORREOS")))
    a.agencias_importar()
    a.perfil_guardar({"nombre": "Ana Pérez", "cargo": "Practicante"})
    a.reloj = reloj
    return a


def _auto(api):
    return api.vigilancia_estado()["datos"]["auto"]


def _activar(api, **extra):
    api.auto_ajustes_guardar({"activo": True, "hora": "08:00", "cuenta_s": 30, "verificar_enviados": False, **extra})


def test_ajustes_de_fabrica_y_validacion(api):
    a = api.auto_ajustes_obtener()["datos"]
    assert a["activo"] is False and a["hora"] == "08:00" and a["accion"] == "enviar" and a["verificar_enviados"]
    for malo in ({"hora": "8am"}, {"hora": "25:00"}, {"accion": "mandar"}, {"cuenta_s": "mucho"}):
        r = api.auto_ajustes_guardar(malo)
        assert r["ok"] is False
    assert api.auto_ajustes_guardar({"cuenta_s": 2})["datos"]["cuenta_s"] == 15


def test_apagado_no_hace_nada(api):
    api.reloj.t = datetime(2026, 10, 13, 8, 30)
    api._vigilancia.tick()
    assert _auto(api)["fase"] == "inactivo" and api._puerta.creados == []


def test_espera_la_hora_y_luego_cuenta_regresiva_y_envia(api):
    _activar(api)
    api._vigilancia.tick()
    assert _auto(api)["fase"] == "espera" and "08:00" in _auto(api)["mensaje"]
    api.reloj.t = datetime(2026, 10, 13, 8, 0, 5)
    api._vigilancia.tick()
    a = _auto(api)
    assert a["fase"] == "cuenta" and a["sale_en"] == 30 and [x["agencia"] for x in a["listos"]] == ["AG. UNO"]
    assert {d["agencia"] for d in a["descartados"]} >= {"AG. DOS", "AG. TRES"}
    assert api._puerta.creados == []                                        # todavía nada ha salido
    api.reloj.avanzar(seconds=31)
    api._vigilancia.tick()
    assert _auto(api)["fase"] == "enviando"
    for _ in range(100):
        api._vigilancia.tick()
        if _auto(api)["fase"] == "hecho":
            break
        import time; time.sleep(0.05)
    a = _auto(api)
    assert a["fase"] == "hecho" and a["resumen"]["enviados"] == 1 and a["anulable_hasta"]
    assert [(c.agencia, acc, dif) for c, acc, dif in api._puerta.creados] == [("AG. UNO", "enviar", 2)]
    assert api._puerta.creados[0][0].modo == "respuesta"


def test_cancelar_no_envia_y_no_se_repite_ese_dia(api):
    _activar(api)
    api.reloj.t = datetime(2026, 10, 13, 8, 0, 5)
    api._vigilancia.tick()
    assert api.auto_cancelar()["datos"]["fase"] == "cancelado"
    api.reloj.avanzar(minutes=5)
    api._vigilancia.tick()
    assert _auto(api)["fase"] == "cancelado" and api._puerta.creados == []
    # al día siguiente el resultado de hoy deja de mostrarse y vuelve a esperar su hora
    api.reloj.t = datetime(2026, 10, 14, 7, 0)
    api._vigilancia.tick()
    assert _auto(api)["fase"] == "espera"


def test_si_se_abre_el_programa_muy_tarde_no_envia_solo(api):
    _activar(api)
    api.reloj.t = datetime(2026, 10, 13, 11, 30)                             # pasaron más de 3 horas
    api._vigilancia.tick()
    a = _auto(api)
    assert a["fase"] == "espera" and "ya pasó" in a["mensaje"] and api._puerta.creados == []


def test_enviar_ya_salta_la_espera(api):
    _activar(api)
    api.reloj.t = datetime(2026, 10, 13, 8, 0, 5)
    api._vigilancia.tick()
    assert api.auto_enviar_ya()["datos"]["sale_en"] == 0
    api._vigilancia.tick()
    assert _auto(api)["fase"] == "enviando"


def test_sin_outlook_espera_y_reintenta_sin_dar_el_dia_por_hecho(api):
    _activar(api)
    api._puerta.libre = False
    api.reloj.t = datetime(2026, 10, 13, 8, 0, 5)
    api._vigilancia.tick()
    assert _auto(api)["fase"] == "esperando_outlook" and _auto(api)["fecha_hecha"] is None
    api._puerta.libre = True
    api.reloj.avanzar(seconds=61)
    api._vigilancia.tick()
    assert _auto(api)["fase"] == "cuenta"


def test_sin_acceso_a_la_carpeta_compartida_no_envia(api):
    _activar(api)
    api._compartida_ok = False
    api.reloj.t = datetime(2026, 10, 13, 8, 0, 5)
    api._vigilancia.tick()
    assert _auto(api)["fase"] == "esperando_outlook" and "compartida" in _auto(api)["mensaje"]


def test_probar_ahora_con_borradores_no_envia_nada(api):
    api.auto_ajustes_guardar({"accion": "borrador", "cuenta_s": 15, "verificar_enviados": False})
    r = api.auto_probar()["datos"]                                          # funciona aunque esté apagado y sea de madrugada
    assert r["fase"] == "cuenta" and r["prueba"] is True and r["accion"] == "borrador"
    api.auto_enviar_ya()
    for _ in range(100):
        api._vigilancia.tick()
        if _auto(api)["fase"] == "hecho":
            break
        import time; time.sleep(0.05)
    assert _auto(api)["fase"] == "hecho" and [acc for _, acc, _ in api._puerta.creados] == ["borrador"]
    assert api._vigilancia._auto.fecha_hecha is None                        # una prueba no gasta el envío del día


def test_sin_nada_que_enviar_lo_dice_y_cierra_el_dia(api):
    _activar(api)
    api._puerta.hilos = {}                                                  # nadie tiene hilo ni respaldo
    api.reloj.t = datetime(2026, 10, 13, 8, 0, 5)
    api._vigilancia.tick()
    a = _auto(api)
    assert a["fase"] == "sin_nada" and "revisión manual" in a["mensaje"] and a["fecha_hecha"] == "2026-10-13"


def test_un_dia_sin_fechas_de_pago_por_avisar(api):
    _activar(api)
    api.reloj.t = datetime(2026, 10, 15, 8, 0, 5)                           # el aviso del 19/10 es el viernes 16
    api._vigilancia.tick()
    assert _auto(api)["fase"] == "sin_nada" and "ninguna fecha" in _auto(api)["mensaje"]


def test_la_revision_de_enviados_corre_sola_y_anota(api):
    api._puerta.enviados = [_env("a", asunto_inicio("AG. UNO", NOMBRE))]
    api.reloj.t = datetime(2026, 10, 13, 10, 0)
    api._vigilancia.tick()
    s = api.vigilancia_estado()["datos"]["sync"]
    assert s["nuevos_total"] == 1 and s["error"] == "" and "1 avisos nuevos" in s["resumen"]
    celda = {a["nombre"]: a for a in api.estado_campana()["datos"]["agencias"]}["AG. UNO"]["celdas"]["inicio"]
    assert celda["estado"] == "env"
    # antes de que pasen 3 minutos no vuelve a consultar; después sí, sin releer lo ya visto
    n = len(api._puerta.consultas)
    api.reloj.avanzar(minutes=1); api._vigilancia.tick()
    assert len(api._puerta.consultas) == n
    api.reloj.avanzar(minutes=3); api._vigilancia.tick()
    assert len(api._puerta.consultas) == n + 1 and "a" in api._puerta.consultas[-1][2]


def test_revisar_enviados_a_pedido(api):
    api._puerta.enviados = [_env("a", asunto_inicio("AG. TRES", NOMBRE))]
    r = api.enviados_revisar()
    assert r["ok"] and r["datos"]["nuevos_total"] == 1


def test_una_falla_de_outlook_al_revisar_se_informa_sin_romper(api):
    def boom(*a, **k): raise RuntimeError("Outlook no responde")
    api._puerta.enviados_desde = boom
    r = api.enviados_revisar()
    assert r["ok"] is False and "no responde" in r["error"]
    assert "no responde" in api.vigilancia_estado()["datos"]["sync"]["error"]


def test_un_error_inesperado_al_preparar_no_deja_el_modo_atascado(api):
    _activar(api)
    api.reloj.t = datetime(2026, 10, 13, 8, 0, 5)
    def boom(*a, **k): raise RuntimeError("fallo raro")
    api._servicio = boom
    api._vigilancia.tick()
    a = _auto(api)
    assert a["fase"] == "esperando_outlook" and "fallo raro" in a["mensaje"] and a["fecha_hecha"] is None
