from datetime import date

from agente_correos.dominio.avisos import normalizar_agencia
from agente_correos.dominio.campana import Campana
from agente_correos.entorno import ruta_desde_url_sharepoint
from agente_correos.reglas.fecha_objetivo import (CalendarioHabil, fecha_larga, fecha_larga_mayusculas,
                                                  texto_relativo)


# ---- Campaña --------------------------------------------------------------
def test_campana_desde_codigo_y_anio_del_archivo():
    c = Campana.desde_archivo("//srv/ENTREGA DE FONDOS ETV MJ 2026 difusion.xlsx")
    assert (c.codigo, c.anio, c.nombre) == ("MJ", 2026, "MAYO – JUNIO 2026")
    assert c.meses == (5, 6)


def test_campana_acepta_guion_bajo_como_separador():
    assert Campana.desde_archivo("CRONOGRAMA_SO_2026_final.xlsx").nombre == "SEPTIEMBRE – OCTUBRE 2026"


def test_campana_no_confunde_codigo_dentro_de_otra_palabra():
    # 'MA' dentro de 'MAYO' o 'JA' dentro de 'JAVIER' no son códigos de campaña
    c = Campana.desde_archivo("MAYO JAVIER 2026.xlsx", hoy=date(2026, 10, 13))
    assert c.codigo == "??" and c.anio == 2026 and not c.identificada


def test_campana_sin_anio_usa_el_de_hoy():
    assert Campana.desde_archivo("cronograma EF.xlsx", hoy=date(2027, 1, 5)).anio == 2027


def test_meses_de_pago_van_dos_meses_despues_de_la_campana():
    # Verificado con cronogramas reales: EF→mar–abr, MA→may–jun, MJ→jul–ago, JA→sep–oct
    assert Campana("EF", 2026).meses_de_pago == (3, 4)
    assert Campana("JA", 2026).meses_de_pago == (9, 10)
    assert Campana("ND", 2026).meses_de_pago == (1, 2)             # nov–dic se paga en enero–febrero
    assert Campana("JA", 2026).meses_de_pago_texto == "SEPTIEMBRE – OCTUBRE"
    assert Campana("??", 2026).meses_de_pago == ()


def test_normalizar_agencia_ignora_tildes_mayusculas_y_espacios():
    assert normalizar_agencia("  Ag.  Huancayo ") == "AG. HUANCAYO"
    assert normalizar_agencia("Piúra") == "PIURA"
    assert normalizar_agencia(None) == ""


# ---- Calendario -------------------------------------------------------------
def test_viernes_avisa_para_el_lunes():
    cal = CalendarioHabil()
    assert cal.objetivo_de_hoy(date(2026, 10, 16)) == date(2026, 10, 19)   # viernes
    assert cal.objetivo_de_hoy(date(2026, 10, 17)) == date(2026, 10, 19)   # sábado
    assert cal.objetivo_de_hoy(date(2026, 10, 13)) == date(2026, 10, 14)   # martes


def test_feriado_se_salta_igual_que_el_fin_de_semana():
    cal = CalendarioHabil([date(2026, 10, 14)])
    assert cal.objetivo_de_hoy(date(2026, 10, 13)) == date(2026, 10, 15)


def test_fecha_de_aviso_es_la_vispera_habil():
    cal = CalendarioHabil()
    assert cal.fecha_de_aviso(date(2026, 10, 19)) == date(2026, 10, 16)    # pago lunes → avisa viernes
    assert cal.fecha_de_aviso(date(2026, 10, 14)) == date(2026, 10, 13)


def test_texto_relativo():
    hoy = date(2026, 10, 13)
    assert texto_relativo(date(2026, 10, 14), hoy) == "el día de mañana"
    assert texto_relativo(date(2026, 10, 13), hoy) == "el día de hoy"
    assert texto_relativo(date(2026, 10, 19), hoy) == "el lunes"


def test_formatos_de_fecha_largos():
    assert fecha_larga(date(2026, 10, 5)) == "05 de octubre de 2026"
    assert fecha_larga_mayusculas(date(2026, 10, 14)) == "14 DE OCTUBRE DE 2026"


def test_enlace_de_sharepoint_a_ruta_de_windows():
    url = "https://servidor/sitio/Documentos%20compartidos/ENTREGA DE FONDOS"
    assert ruta_desde_url_sharepoint(url) ==         "//servidor@SSL/DavWWWRoot/sitio/Documentos compartidos/ENTREGA DE FONDOS"
    assert ruta_desde_url_sharepoint(r"D:\datos\carpeta") == r"D:\datos\carpeta"
    assert ruta_desde_url_sharepoint("//srv@SSL/DavWWWRoot/x") == "//srv@SSL/DavWWWRoot/x"
