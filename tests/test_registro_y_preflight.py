from datetime import date, datetime

from agente_correos.dominio.avisos import ClaveAviso, EstadoAviso, EventoAviso, TipoAviso
from agente_correos.historial.registro import RegistroEjecuciones
from agente_correos.reglas.preflight import PreflightValidator, Veredicto, resumen

CAMPANA = "JULIO – AGOSTO 2026"
HOY = date(2026, 10, 14)


def _evento(estado, agencia="AG. UNO", fecha=HOY, tipo=TipoAviso.RECORDATORIO, usuario="mcg22"):
    return EventoAviso(clave=ClaveAviso.crear(CAMPANA, agencia, tipo, fecha), estado=estado, usuario=usuario)


# ---- Registro ---------------------------------------------------------------
def test_registro_guarda_y_recupera_eventos(registro):
    registro.registrar(_evento(EstadoAviso.BORRADOR))
    eventos = registro.eventos(CAMPANA)
    assert len(eventos) == 1 and eventos[0].clave.agencia == "AG. UNO" and eventos[0].creado_en


def test_el_estado_vigente_es_el_ultimo_evento(tmp_path):
    reloj = iter(datetime(2026, 10, 13, 8, m) for m in range(10))
    reg = RegistroEjecuciones(tmp_path, reloj=lambda: next(reloj))
    reg.registrar(_evento(EstadoAviso.ENVIANDO))
    reg.registrar(_evento(EstadoAviso.ENVIADO))
    assert reg.estado_actual(_evento(EstadoAviso.ENVIADO).clave).estado is EstadoAviso.ENVIADO
    assert len(reg.eventos(CAMPANA)) == 2        # el historial conserva ambos


def test_ya_avisado_distingue_agencias_y_fechas(registro):
    registro.registrar(_evento(EstadoAviso.ENVIADO))
    assert registro.ya_avisado(_evento(EstadoAviso.ENVIADO).clave)
    assert not registro.ya_avisado(_evento(EstadoAviso.ENVIADO, agencia="AG. DOS").clave)
    assert not registro.ya_avisado(_evento(EstadoAviso.ENVIADO, fecha=date(2026, 10, 15)).clave)


def test_la_clave_normaliza_la_agencia(registro):
    registro.registrar(_evento(EstadoAviso.ENVIADO, agencia="Ag.  uno"))
    assert registro.ya_avisado(ClaveAviso.crear(CAMPANA, "AG. UNO", TipoAviso.RECORDATORIO, HOY))


def test_un_error_no_cuenta_como_avisado(registro):
    registro.registrar(_evento(EstadoAviso.ERROR))
    assert not registro.ya_avisado(_evento(EstadoAviso.ERROR).clave)


def test_registro_ignora_archivos_danados(registro, tmp_path):
    registro.registrar(_evento(EstadoAviso.ENVIADO))
    carpeta = next((tmp_path / "registro").iterdir())
    (carpeta / "basura.json").write_text("{no es json", encoding="utf-8")
    assert len(registro.eventos(CAMPANA)) == 1


def test_campana_sin_eventos(registro):
    assert registro.eventos("CAMPAÑA INEXISTENTE") == []


# ---- Preflight --------------------------------------------------------------
def _evaluar(cronograma, directorio, registro, config, **kw):
    pf = PreflightValidator(cronograma, directorio, registro, config)
    return {r.agencia: r for r in pf.evaluar(TipoAviso.RECORDATORIO, HOY, **kw)}


def test_preflight_clasifica_cada_caso(cronograma, directorio, registro, config):
    r = _evaluar(cronograma, directorio, registro, config)
    assert r["AG. UNO"].veredicto is Veredicto.LISTA
    assert r["AG. TRES"].veredicto is Veredicto.LISTA
    assert r["AG. CUATRO"].veredicto is Veredicto.BLOQUEADA and "no figura" in r["AG. CUATRO"].motivo
    assert r["AG. CINCO"].veredicto is Veredicto.BLOQUEADA and "gmail.com" in r["AG. CINCO"].motivo
    assert r["AG. SEIS"].veredicto is Veredicto.BLOQUEADA and "Sin correo" in r["AG. SEIS"].motivo
    assert r["AG. SIETE"].veredicto is Veredicto.BLOQUEADA and "inválido" in r["AG. SIETE"].motivo


def test_preflight_solo_incluye_agencias_con_filas_en_la_fecha(cronograma, directorio, registro, config):
    pf = PreflightValidator(cronograma, directorio, registro, config)
    assert pf.evaluar(TipoAviso.RECORDATORIO, date(2026, 10, 25)) == []
    uno = [r for r in pf.evaluar(TipoAviso.RECORDATORIO, date(2026, 10, 19))]
    assert [r.agencia for r in uno] == ["AG. UNO"]


def test_preflight_omite_lo_ya_enviado(cronograma, directorio, registro, config):
    registro.registrar(_evento(EstadoAviso.ENVIADO, usuario="jrojas"))
    r = _evaluar(cronograma, directorio, registro, config)["AG. UNO"]
    assert r.veredicto is Veredicto.OMITIDA and "jrojas" in r.motivo


def test_preflight_omite_el_borrador_de_otra_persona(cronograma, directorio, registro, config):
    registro.registrar(_evento(EstadoAviso.BORRADOR, usuario="jrojas"))
    r = _evaluar(cronograma, directorio, registro, config)["AG. UNO"]
    assert r.veredicto is Veredicto.OMITIDA and "jrojas" in r.motivo


def test_preflight_deja_regenerar_un_borrador_propio(cronograma, directorio, registro, config):
    registro.registrar(_evento(EstadoAviso.BORRADOR))                 # del mismo usuario que revisa
    r = _evaluar(cronograma, directorio, registro, config)["AG. UNO"]
    assert r.veredicto is Veredicto.LISTA and "borrador suyo" in r.motivo
    assert any("Elimine el borrador anterior" in a for a in r.advertencias)


def test_envio_interrumpido_pide_decision(cronograma, directorio, registro, config):
    registro.registrar(_evento(EstadoAviso.ENVIANDO))
    r = _evaluar(cronograma, directorio, registro, config)["AG. UNO"]
    assert r.veredicto is Veredicto.REVISAR and "Enviados" in r.motivo


def test_preflight_avisa_importe_vacio_sin_bloquear(cronograma, directorio, registro, config):
    r = _evaluar(cronograma, directorio, registro, config)["AG. DOS"]
    assert r.veredicto is Veredicto.LISTA and any("importe" in a for a in r.advertencias)


def test_preflight_inicio_incluye_todas_las_agencias(cronograma, directorio, registro, config):
    pf = PreflightValidator(cronograma, directorio, registro, config)
    res = pf.evaluar(TipoAviso.INICIO)
    assert len(res) == 7 and all(r.fecha_objetivo is None for r in res)


def test_resumen_cuenta_por_veredicto(cronograma, directorio, registro, config):
    conteo = resumen(PreflightValidator(cronograma, directorio, registro, config)
                     .evaluar(TipoAviso.RECORDATORIO, HOY))
    assert conteo == {"lista": 3, "revisar": 0, "omitida": 0, "bloqueada": 4}


def test_recordatorio_sin_fecha_es_error(cronograma, directorio, registro, config):
    import pytest
    with pytest.raises(ValueError):
        PreflightValidator(cronograma, directorio, registro, config).evaluar(TipoAviso.RECORDATORIO)
