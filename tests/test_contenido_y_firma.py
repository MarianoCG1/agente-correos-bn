from datetime import date

import pandas as pd

from agente_correos.contenido import formato
from agente_correos.contenido.plantillas import (Plantillas, Programas, asunto_inicio, asunto_recordatorio,
                                                 fecha_de_inicio)
from agente_correos.contenido.tabla_html import construir_tabla
from agente_correos.datos.cronograma_loader import programas_activos
from agente_correos.usuario.firma import buscar_logo_en_firmas_outlook, construir_firma, logo_como_data_uri
from agente_correos.usuario.perfil import PerfilUsuario, normalizar_nombre


# ---- formato ----------------------------------------------------------------
def test_formatos_de_celda():
    assert formato.codigo(664) == "0664" and formato.codigo("85.0") == "0085" and formato.codigo("0664") == "0664"
    assert formato.codigo(float("nan")) == ""
    assert formato.importe(67920) == "67,920.00" and formato.importe(0) == "" and formato.importe("x") == ""
    assert formato.entero(170.0) == "170" and formato.entero(None) == ""
    assert formato.fecha_corta(pd.Timestamp(2026, 10, 14)) == "14/10/26" and formato.fecha_corta(float("nan")) == ""
    assert formato.hora(pd.Timestamp(2026, 1, 1, 9, 0)) == "09:00 AM" and formato.hora(float("nan")) == ""


# ---- tabla ------------------------------------------------------------------
def test_tabla_tiene_cabeceras_y_celdas_rojas_para_datos_faltantes(cronograma):
    filas = cronograma.filas("AG. DOS", date(2026, 10, 14))
    html = construir_tabla(filas, False, False, es_recordatorio=True)
    assert html.startswith("<table") and html.endswith("</table>")
    assert "Pensión 65" in html and "Juntos" not in html
    assert "background:red;" in html                       # importe 0 → celda roja


def test_tabla_incluye_juntos_solo_si_hay_usuarios(cronograma):
    filas = cronograma.filas("AG. UNO", date(2026, 10, 14))
    juntos, contigo = programas_activos(filas)
    html = construir_tabla(filas, juntos, contigo)
    assert "Juntos" in html and "Contigo" not in html
    assert "0664" in html and "50,000.00" in html           # código con ceros e importe formateado


def test_tabla_resalta_importe_y_fecha_de_entrega(cronograma):
    html = construir_tabla(cronograma.filas("AG. TRES"), False, False)
    assert html.count("background:#FFFF00;font-weight:bold;") >= 3


# ---- plantillas -------------------------------------------------------------
def test_asuntos_son_los_de_v1():
    assert asunto_inicio("AG. UNO", "MAYO – JUNIO 2026") == "Programación de Fondos – BN AG. UNO – MAYO – JUNIO 2026"
    assert asunto_recordatorio("AG. UNO", "MAYO – JUNIO 2026") == \
        "RECORDATORIO: Entrega de Fondos – BN AG. UNO – MAYO – JUNIO 2026"


def test_cuerpo_recordatorio(config):
    html = Plantillas(config).cuerpo_recordatorio("AG. UNO", date(2026, 10, 14), date(2026, 10, 13),
                                                  "SEPTIEMBRE – OCTUBRE 2026", "<table></table>")
    assert "el día de mañana" in html and "14 de octubre de 2026" in html
    assert "SEPTIEMBRE – OCTUBRE 2026" in html and "<table></table>" in html


def test_cuerpo_inicio_menciona_programas_activos(config):
    p = Plantillas(config)
    solo = p.cuerpo_inicio("AG. UNO", date(2026, 10, 14), "C", "", Programas())
    todos = p.cuerpo_inicio("AG. UNO", date(2026, 10, 14), "C", "", Programas(True, True))
    assert "el Programa Social <b>PENSIÓN 65</b>" in solo
    assert "<b>PENSIÓN 65</b>, <b>JUNTOS</b> y <b>CONTIGO</b>" in todos
    assert "14 DE OCTUBRE DE 2026" in solo and "Nombre y Apellidos" in solo


def test_cuerpo_inicio_usa_la_jefatura_configurada(config):
    config.por_encargo_nombre, config.por_encargo_cargo = "Ana Pérez", "Jefa de Sección"
    html = Plantillas(config).cuerpo_inicio("AG. UNO", None, "C", "", Programas())
    assert "Ana Pérez - Jefa de Sección" in html and "PRÓXIMAMENTE" in html


def test_fecha_de_inicio_es_la_mas_temprana(cronograma):
    assert fecha_de_inicio(cronograma.filas("AG. UNO")) == date(2026, 10, 14)


# ---- perfil y firma ---------------------------------------------------------
def test_normalizar_nombre():
    assert normalizar_nombre("PEREZ, Ana B.") == "Ana B. Perez"
    assert normalizar_nombre("  ANA   PEREZ ") == "Ana Perez"
    assert normalizar_nombre("Ana B. Pérez Quispe") == "Ana B. Pérez Quispe"


def test_firma_con_cargo_replica_el_formato_del_banco():
    perfil = PerfilUsuario(nombre="Ana B. Pérez Quispe", cargo="Practicante", anexo="12345",
                           email="pra_aperez@bn.com.pe")
    html = construir_firma(perfil, logo_src="cid:logo_firma")
    assert "<b>Practicante - Ana B. Pérez Quispe</b>" in html
    assert "Telf: 519-2000 Anexo <b>12345</b>" in html
    assert "Oficina Principal del BN – San Borja" in html
    assert 'src="cid:logo_firma"' in html and "border-left:1px solid" in html
    assert 'href="mailto:pra_aperez@bn.com.pe"' in html
    assert "confidenciales" not in html


def test_firma_sin_cargo_con_aviso_confidencial_y_sin_correo():
    perfil = PerfilUsuario(nombre="Ana B. Pérez Quispe", anexo="97811", mostrar_email=False,
                           direccion="Av. Javier Prado Este 2499 - San Borja", aviso_confidencial=True)
    html = construir_firma(perfil)
    assert "<b>Ana B. Pérez Quispe</b>" in html and "Practicante" not in html
    assert "Av. Javier Prado Este 2499" in html and "confidenciales" in html
    assert "E-mail" not in html and "<img" not in html


def test_firma_escapa_html_del_usuario():
    html = construir_firma(PerfilUsuario(nombre="<script>x</script>"))
    assert "<script>" not in html


def test_perfil_se_guarda_y_se_carga(tmp_path):
    ruta = tmp_path / "perfil.json"
    PerfilUsuario(nombre="Ana", anexo="123", modo_firma="outlook").guardar(ruta)
    cargado = PerfilUsuario.cargar(ruta)
    assert (cargado.nombre, cargado.anexo, cargado.modo_firma) == ("Ana", "123", "outlook")
    assert PerfilUsuario.cargar(tmp_path / "no_existe.json").completo is False


def test_busca_el_logo_mas_grande_en_las_firmas_de_outlook(tmp_path):
    carpeta = tmp_path / "Mi firma_files"
    carpeta.mkdir()
    (carpeta / "pequeno.png").write_bytes(b"x" * 10)
    (carpeta / "logo.png").write_bytes(b"x" * 500)
    assert buscar_logo_en_firmas_outlook(tmp_path).name == "logo.png"
    assert buscar_logo_en_firmas_outlook(tmp_path / "vacia") is None
    assert logo_como_data_uri(carpeta / "logo.png").startswith("data:image/png;base64,")


def test_config_ignora_claves_desconocidas_y_guarda(tmp_path, config):
    ruta = tmp_path / "config.json"
    ruta.write_text('{"dominio_interno": "ejemplo.pe", "clave_vieja": 1, "feriados": ["2026-10-08", "mal"]}',
                    encoding="utf-8")
    from agente_correos.configuracion import Configuracion
    cargada = Configuracion.cargar(ruta)
    assert cargada.dominio_interno == "ejemplo.pe" and cargada.dominio_con_arroba() == "@ejemplo.pe"
    assert cargada.feriados_como_fechas() == [date(2026, 10, 8)]
    cargada.guardar(tmp_path / "otra.json")
    assert Configuracion.cargar(tmp_path / "otra.json").dominio_interno == "ejemplo.pe"
