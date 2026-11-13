"""Genera el manual de usuario en Word (identidad BN: Arial, blanco dominante, rojo #C8102E con intención).

    python docs/manual/construir_manual.py

Las capturas salen de docs/manual/capturas (las genera capturar.mjs con datos ficticios).
"""

import re
from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

AQUI = Path(__file__).resolve().parent
CAPT = AQUI / "capturas"
SALIDA = AQUI.parent / "Manual_de_usuario_Agente_Correos_BN.docx"

ROJO, ROJO_OSC, ROJO_SUAVE = "C8102E", "9A0C23", "F6D6DA"
TINTA, TEXTO, GRIS, LINEA, PANEL = "1A1A1A", "333333", "6E6E6E", "D9D9D9", "F4F4F4"
AT_FONDO, AT_TEXTO = "FFF1D6", "B26A00"
OK_FONDO, OK_TEXTO = "E6F2E7", "2E7D32"
ANCHO_UTIL = 16.4          # cm (A4 con márgenes de 2,3 cm)

doc = Document()


def rgb(hexa):
    return RGBColor.from_string(hexa)


def fuente(runs_o_estilo, nombre="Arial", tam=None, negrita=None, color=None, cursiva=None):
    f = runs_o_estilo.font
    f.name = nombre
    el = runs_o_estilo.element if hasattr(runs_o_estilo, "element") else runs_o_estilo._element
    rpr = el.get_or_add_rPr() if hasattr(el, "get_or_add_rPr") else el.rPr
    rf = rpr.find(qn("w:rFonts"))
    if rf is None:
        rf = OxmlElement("w:rFonts")
        rpr.append(rf)
    for atributo in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rf.set(qn(atributo), nombre)
    for atributo in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
        if rf.get(qn(atributo)) is not None:
            del rf.attrib[qn(atributo)]
    if tam is not None:
        f.size = Pt(tam)
    if negrita is not None:
        f.bold = negrita
    if cursiva is not None:
        f.italic = cursiva
    if color:
        f.color.rgb = rgb(color)


# ---------------------------------------------------------------- página y estilos
sec = doc.sections[0]
sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
sec.left_margin = sec.right_margin = Cm(2.3)
sec.top_margin, sec.bottom_margin = Cm(2.5), Cm(2.2)
sec.header_distance, sec.footer_distance = Cm(1.1), Cm(1.0)
sec.different_first_page_header_footer = True

normal = doc.styles["Normal"]
fuente(normal, tam=11, color=TEXTO)
normal.paragraph_format.space_after = Pt(6)
normal.paragraph_format.line_spacing = 1.15

for nombre, tam, antes, despues, color in (("Heading 1", 18, 22, 8, TINTA), ("Heading 2", 13.5, 16, 5, TINTA),
                                           ("Heading 3", 11.5, 12, 3, TINTA)):
    est = doc.styles[nombre]
    fuente(est, tam=tam, negrita=True, color=color)
    est.paragraph_format.space_before = Pt(antes)
    est.paragraph_format.space_after = Pt(despues)
    est.paragraph_format.keep_with_next = True

for nombre in ("List Bullet", "List Number", "Caption"):
    fuente(doc.styles[nombre], tam=11 if nombre != "Caption" else 9.5, color=TEXTO if nombre != "Caption" else GRIS)


# ---------------------------------------------------------------- utilidades
def sombrear(celda, color):
    tcpr = celda._tc.get_or_add_tcPr()
    for viejo in tcpr.findall(qn("w:shd")):
        tcpr.remove(viejo)
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), color)
    tcpr.append(shd)


def bordes(celda, **lados):
    """lados: top/left/bottom/right = (grosor_en_octavos_de_punto, color) o None para sin borde."""
    tcpr = celda._tc.get_or_add_tcPr()
    b = tcpr.find(qn("w:tcBorders"))
    if b is None:
        b = OxmlElement("w:tcBorders")
        tcpr.append(b)
    for lado in ("top", "left", "bottom", "right"):
        el = OxmlElement(f"w:{lado}")
        v = lados.get(lado)
        if v is None:
            el.set(qn("w:val"), "nil")
        else:
            el.set(qn("w:val"), "single")
            el.set(qn("w:sz"), str(v[0]))
            el.set(qn("w:color"), v[1])
            el.set(qn("w:space"), "0")
        b.append(el)


def margenes_celda(celda, arriba=60, abajo=60, izq=110, der=110):
    tcpr = celda._tc.get_or_add_tcPr()
    m = OxmlElement("w:tcMar")
    for lado, v in (("top", arriba), ("left", izq), ("bottom", abajo), ("right", der)):
        e = OxmlElement(f"w:{lado}")
        e.set(qn("w:w"), str(v))
        e.set(qn("w:type"), "dxa")
        m.append(e)
    tcpr.append(m)


def ancho_celda(celda, cm):
    celda.width = Cm(cm)


def fijar_tabla(tabla, anchos):
    tabla.alignment = WD_TABLE_ALIGNMENT.LEFT
    tabla.autofit = False
    tblpr = tabla._tbl.tblPr
    lay = OxmlElement("w:tblLayout")
    lay.set(qn("w:type"), "fixed")
    tblpr.append(lay)
    for fila in tabla.rows:
        for celda, cm in zip(fila.cells, anchos):
            ancho_celda(celda, cm)
    grid = tabla._tbl.tblGrid
    for col, cm in zip(grid.findall(qn("w:gridCol")), anchos):
        col.set(qn("w:w"), str(int(cm * 567)))


def sin_cortar(fila):
    trpr = fila._tr.get_or_add_trPr()
    trpr.append(OxmlElement("w:cantSplit"))


def repetir_encabezado(fila):
    trpr = fila._tr.get_or_add_trPr()
    e = OxmlElement("w:tblHeader")
    e.set(qn("w:val"), "true")
    trpr.append(e)


PATRON = re.compile(r"(\*\*.+?\*\*)")


def texto_en(parrafo, texto, tam=None, color=None, negrita=False, cursiva=False):
    """Escribe texto con **negritas** en línea."""
    for trozo in PATRON.split(texto):
        if not trozo:
            continue
        es_neg = trozo.startswith("**") and trozo.endswith("**")
        run = parrafo.add_run(trozo[2:-2] if es_neg else trozo)
        fuente(run, tam=tam, color=color, negrita=(negrita or es_neg), cursiva=cursiva)
    return parrafo


def p(texto, tam=None, color=None, alinea=None, despues=None, antes=None, cursiva=False, mantener=False):
    par = doc.add_paragraph()
    texto_en(par, texto, tam=tam, color=color, cursiva=cursiva)
    if alinea:
        par.alignment = alinea
    if despues is not None:
        par.paragraph_format.space_after = Pt(despues)
    if antes is not None:
        par.paragraph_format.space_before = Pt(antes)
    if mantener:
        par.paragraph_format.keep_with_next = True
    return par


def h1(t, nueva_pagina=True):
    par = doc.add_heading(t, level=1)
    if nueva_pagina:
        par.paragraph_format.page_break_before = True
    return par


def h2(t):
    return doc.add_heading(t, level=2)


def h3(t):
    return doc.add_heading(t, level=3)


def vinetas(items):
    for it in items:
        par = doc.add_paragraph(style="List Bullet")
        texto_en(par, it)
        par.paragraph_format.space_after = Pt(3)


def paso(n, texto):
    par = doc.add_paragraph()
    par.paragraph_format.left_indent = Cm(0.9)
    par.paragraph_format.first_line_indent = Cm(-0.9)
    par.paragraph_format.tab_stops.add_tab_stop(Cm(0.9))
    par.paragraph_format.space_after = Pt(5)
    r = par.add_run(f"{n}.")
    fuente(r, negrita=True, color=ROJO)
    par.add_run("\t")
    texto_en(par, texto)
    return par


def aviso(titulo, texto, tipo="nota"):
    """Recuadro de una celda. nota = panel gris; atencion = ámbar; importante = rojo suave."""
    fondo, borde, col_titulo = {"nota": (PANEL, GRIS, TINTA), "atencion": (AT_FONDO, AT_TEXTO, AT_TEXTO),
                                "importante": (ROJO_SUAVE, ROJO, ROJO_OSC), "ok": (OK_FONDO, OK_TEXTO, OK_TEXTO)}[tipo]
    t = doc.add_table(rows=1, cols=1)
    fijar_tabla(t, [ANCHO_UTIL])
    c = t.rows[0].cells[0]
    sombrear(c, fondo)
    bordes(c, left=(24, borde))
    margenes_celda(c, 90, 90, 160, 140)
    par = c.paragraphs[0]
    par.paragraph_format.space_after = Pt(2)
    r = par.add_run(titulo)
    fuente(r, tam=10.5, negrita=True, color=col_titulo)
    for linea in texto if isinstance(texto, list) else [texto]:
        q = c.add_paragraph()
        q.paragraph_format.space_after = Pt(2)
        texto_en(q, linea, tam=10.5)
    sin_cortar(t.rows[0])
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def tabla(encabezados, filas, anchos, tam=10):
    t = doc.add_table(rows=1, cols=len(encabezados))
    fijar_tabla(t, anchos)
    for i, e in enumerate(encabezados):
        c = t.rows[0].cells[i]
        sombrear(c, ROJO_OSC)
        bordes(c, bottom=(4, ROJO_OSC))
        margenes_celda(c)
        c.paragraphs[0].paragraph_format.space_after = Pt(0)
        fuente(c.paragraphs[0].add_run(e), tam=tam, negrita=True, color="FFFFFF")
    repetir_encabezado(t.rows[0])
    for n, fila in enumerate(filas):
        cel = t.add_row().cells
        for i, valor in enumerate(fila):
            c = cel[i]
            sombrear(c, PANEL if n % 2 else "FFFFFF")
            bordes(c, bottom=(4, LINEA))
            margenes_celda(c)
            partes = valor if isinstance(valor, list) else [valor]
            for j, parte in enumerate(partes):
                par = c.paragraphs[0] if j == 0 else c.add_paragraph()
                par.paragraph_format.space_after = Pt(2)
                texto_en(par, parte, tam=tam)
        sin_cortar(t.rows[-1])
    fijar_tabla(t, anchos)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return t


FIG = [0]


def figura(archivo, pie, leyenda=None, ancho=ANCHO_UTIL):
    ruta = CAPT / archivo
    if not ruta.is_file():
        raise FileNotFoundError(ruta)
    par = doc.add_paragraph()
    par.alignment = WD_ALIGN_PARAGRAPH.CENTER
    par.paragraph_format.keep_with_next = True
    par.paragraph_format.space_after = Pt(2)
    par.add_run().add_picture(str(ruta), width=Cm(ancho))
    FIG[0] += 1
    cap = doc.add_paragraph(style="Caption")
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap.paragraph_format.space_after = Pt(8)
    if leyenda:
        cap.paragraph_format.keep_with_next = True
    fuente(cap.add_run(f"Figura {FIG[0]}. {pie}"), tam=9.5, color=GRIS)
    if leyenda:
        leyenda_numerada(leyenda)


def leyenda_numerada(items):
    t = doc.add_table(rows=0, cols=2)
    for n, texto in items:
        cel = t.add_row().cells
        sombrear(cel[0], ROJO)
        bordes(cel[0], bottom=(8, "FFFFFF"))
        margenes_celda(cel[0], 30, 30, 40, 40)
        cel[0].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        cel[0].paragraphs[0].paragraph_format.space_after = Pt(0)
        fuente(cel[0].paragraphs[0].add_run(str(n)), tam=10, negrita=True, color="FFFFFF")
        bordes(cel[1], bottom=(4, LINEA))
        margenes_celda(cel[1], 40, 40, 140, 60)
        cel[1].paragraphs[0].paragraph_format.space_after = Pt(0)
        texto_en(cel[1].paragraphs[0], texto, tam=10.5)
        sin_cortar(t.rows[-1])
    for fila in t.rows[:-1]:                    # la leyenda se queda junto a la captura
        for celda in fila.cells:
            for par in celda.paragraphs:
                par.paragraph_format.keep_with_next = True
    fijar_tabla(t, [0.8, ANCHO_UTIL - 0.8])
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def campo(parrafo, instruccion, texto_previo="", tam=None, color=None):
    """Campo de Word (PAGE, NUMPAGES, TOC...). Todos sus fragmentos llevan la misma tipografía."""
    def dar_formato(r):
        if tam or color:
            fuente(r, tam=tam, color=color)
        return r

    def fld(tipo):
        r = dar_formato(parrafo.add_run())
        e = OxmlElement("w:fldChar")
        e.set(qn("w:fldCharType"), tipo)
        r._r.append(e)
        return r
    fld("begin")
    r = dar_formato(parrafo.add_run())
    it = OxmlElement("w:instrText")
    it.set(qn("xml:space"), "preserve")
    it.text = f" {instruccion} "
    r._r.append(it)
    fld("separate")
    previo = dar_formato(parrafo.add_run(texto_previo))
    fld("end")
    return previo


# ---------------------------------------------------------------- encabezado y pie
def encabezado_pie(seccion):
    ep = seccion.header
    ep.is_linked_to_previous = False
    par = ep.paragraphs[0]
    par.paragraph_format.tab_stops.add_tab_stop(Cm(ANCHO_UTIL), WD_TAB_ALIGNMENT.RIGHT)
    fuente(par.add_run("Banco de la Nación"), tam=9, color=GRIS)
    fuente(par.add_run("\t\tAgente de Correos BN · Manual de usuario"), tam=9, color=GRIS)
    pb = par._p.get_or_add_pPr()
    borde = OxmlElement("w:pBdr")
    b = OxmlElement("w:bottom")
    b.set(qn("w:val"), "single")
    b.set(qn("w:sz"), "4")
    b.set(qn("w:space"), "4")
    b.set(qn("w:color"), LINEA)
    borde.append(b)
    pb.append(borde)

    pie = seccion.footer
    pie.is_linked_to_previous = False
    q = pie.paragraphs[0]
    q.paragraph_format.tab_stops.add_tab_stop(Cm(ANCHO_UTIL), WD_TAB_ALIGNMENT.RIGHT)
    fuente(q.add_run("Banco de la Nación · Gerencia de Operaciones · Subgerencia Caja y Valores\t\tPágina "), tam=9, color=GRIS)
    campo(q, "PAGE", "1", tam=9, color=GRIS)
    fuente(q.add_run(" de "), tam=9, color=GRIS)
    campo(q, "NUMPAGES", "1", tam=9, color=GRIS)


encabezado_pie(sec)

# ================================================================= PORTADA
par = doc.add_paragraph()
par.paragraph_format.space_before = Pt(10)
par.add_run().add_picture(str(AQUI / "logo_bn_oficial.png"), width=Cm(4.6))
for _ in range(5):
    doc.add_paragraph()
par = doc.add_paragraph()
fuente(par.add_run("MANUAL DE USUARIO"), tam=11, negrita=True, color=GRIS)
par.paragraph_format.space_after = Pt(2)
par = doc.add_paragraph()
fuente(par.add_run("Agente de Correos BN"), tam=36, negrita=True, color=ROJO)
par.paragraph_format.space_after = Pt(6)
par = doc.add_paragraph()
fuente(par.add_run("Cómo preparar y enviar a las agencias los avisos de entrega de fondos de las ETV"), tam=15, color=TINTA)
par.paragraph_format.space_after = Pt(18)
par = doc.add_paragraph()
fuente(par.add_run("Versión 2.0 · Octubre de 2026"), tam=12, color=GRIS)
for _ in range(9):
    doc.add_paragraph()
par = doc.add_paragraph()
fuente(par.add_run("Sección Caja y Valores en Custodia"), tam=11, negrita=True, color=TINTA)
par.paragraph_format.space_after = Pt(0)
for linea in ("Subgerencia Caja y Valores · Gerencia de Operaciones", "Banco de la Nación"):
    par = doc.add_paragraph()
    fuente(par.add_run(linea), tam=11, color=GRIS)
    par.paragraph_format.space_after = Pt(0)
par = doc.add_paragraph()
par.paragraph_format.space_before = Pt(10)
fuente(par.add_run("Desarrollado por Ana B. Pérez Quispe · Telf. 519-2000, Anexo 12345"), tam=10, color=GRIS)

# ================================================================= CONTENIDO
par = doc.add_paragraph()
par.paragraph_format.page_break_before = True
fuente(par.add_run("Contenido"), tam=18, negrita=True, color=TINTA)
par = doc.add_paragraph()
campo(par, 'TOC \\o "1-1" \\h \\z \\u', "Para ver el contenido, haga clic derecho aquí y elija «Actualizar campo».")

# ================================================================= 1
h1("1. Qué es el Agente de Correos BN")
p("El **Agente de Correos BN** es un programa de escritorio que prepara y envía a las agencias del Banco de la Nación los avisos "
  "de entrega de fondos de las empresas de transporte de valores (ETV): el **correo de inicio** de cada campaña y los "
  "**recordatorios** de cada fecha de pago.")
p("En una sola pantalla muestra qué avisos están pendientes hoy, cuáles ya salieron y cuáles faltan, de modo que nadie tenga que "
  "recordar de memoria qué agencia ya recibió su correo.")
h2("Lo que hace por usted")
vinetas([
    "Arma cada correo con la tabla de la agencia, el Excel filtrado con solo sus filas y su firma.",
    "Responde en el hilo del correo de inicio, de modo que la agencia ve todo junto.",
    "Avisa cuando algo no puede salir: agencia sin correo, correo inválido, dos hilos posibles.",
    "Registra quién envió qué y cuándo. Si otra persona ya envió un aviso, el programa **no lo repite**.",
    "Permite anular un envío durante unos minutos y pedir confirmación de lectura.",
    "Genera el archivo de **entrega** a partir del cronograma original, sin modificar el original.",
])
aviso("Ningún correo sale sin que usted lo confirme",
      "Antes de enviar, el programa muestra la lista de agencias y el correo exacto que recibirán. El envío ocurre solo cuando usted "
      "pulsa el botón de confirmación, y durante unos minutos todavía puede anularlo.", "importante")
h2("Lo que no hace")
vinetas([
    "No envía solo ni a una hora programada.",
    "No modifica el cronograma original: los cambios se hacen siempre en una copia (la entrega).",
    "No reemplaza el criterio de quien opera: decisiones como qué hilo elegir o qué puntos se suspendieron las toma usted.",
])

# ================================================================= 2
h1("2. Antes de empezar")
h2("Qué necesita")
tabla(["Requisito", "Detalle"], [
    ["**Windows con Outlook de escritorio**", "Outlook debe estar **abierto** con su propio buzón mientras usa el programa."],
    ["**Acceso a SharePoint**", "A la carpeta de Caja y Valores: ENTREGA DE FONDOS y su subcarpeta BACKUP_CORREOS."],
    ["**El instalador**", "El archivo **AgenteCorreosBN_2.0.0-beta_Setup.exe** (el número puede cambiar con cada versión). Se lo entrega quien mantiene el programa."],
], [4.6, ANCHO_UTIL - 4.6])
h2("Cómo instalarlo")
paso(1, "Copie el instalador a su equipo (por ejemplo, al Escritorio) y haga doble clic. **No necesita permisos de administrador.**")
paso(2, "Pulse **Siguiente**. Deje la carpeta de instalación que propone el programa (está dentro de su usuario de Windows).")
paso(3, "Marque **Crear acceso directo en el Escritorio** y pulse **Instalar**.")
paso(4, "Al terminar, deje marcada la casilla **Abrir Agente de Correos BN ahora** y pulse **Finalizar**.")
aviso("Si Windows o el antivirus bloquean el instalador",
      "Es posible que Windows muestre una advertencia por tratarse de un programa interno sin firma digital. No continúe por su cuenta: "
      "comuníquese con quien mantiene el programa.", "atencion")
h2("Cómo se abre")
p("Haga doble clic en el acceso directo **Agente de Correos BN**. La ventana se abre siempre maximizada. "
  "Si abre el programa por primera vez en un equipo, siga la sección 3.")
h2("Actualizar o desinstalar")
vinetas([
    "**Actualizar:** ejecute el instalador de la versión nueva; se instala encima de la anterior y conserva sus datos.",
    "**Desinstalar:** Configuración de Windows › Aplicaciones › Agente de Correos BN. Su perfil y su registro de actividad no se borran.",
])

# ================================================================= 3
h1("3. Primeros pasos en un equipo nuevo")
p("Cuando al programa le falta algo para mostrar la campaña, en lugar del tablero aparece la pantalla **Antes de empezar**. "
  "Indica qué encontró en el equipo y ofrece un botón para resolver cada punto. Cuando todo está en orden, desaparece sola y se muestra el tablero.")
figura("01_primeros_pasos.png", "Pantalla «Antes de empezar» (ejemplo con datos ficticios).", [
    (1, "**Carpeta compartida.** Es la carpeta de SharePoint donde el programa guarda el registro de avisos, la lista de agencias y los perfiles. "
        "Si no se pudo abrir, revise su conexión y use **Revisar rutas**. Mientras tanto solo podrá crear borradores."),
    (2, "**Agencias y correos.** Normalmente ya vienen cargadas con la instalación. Si no, use **Importar lista…** o **Agregar a mano** (sección 9.1)."),
    (3, "**Campaña (entrega vigente).** El programa la busca solo en las carpetas conocidas. Si no la encuentra, use **Elegir una entrega…** para señalarla "
        "o **Preparar desde el original** si todavía no existe (sección 7)."),
    (4, "**Outlook.** Debe decir «Conectado». Si dice que no respondió, vea la sección 11."),
    (5, "**Mi firma.** Complete su nombre y cargo para que los correos salgan con su firma (sección 9.2)."),
])
aviso("Su nombre se detecta solo",
      "El programa toma su nombre de Windows y de Outlook. Al abrir **Mi perfil y firma** solo tiene que revisarlo y guardar.", "nota")

# ================================================================= 4
h1("4. El tablero de control")
p("El tablero es la pantalla principal. Cada fila es una agencia y cada columna, una fecha de pago. En cada cruce hay un símbolo que indica "
  "en qué estado está el aviso. Su función es responder dos preguntas: **¿qué tengo pendiente hoy?** y **¿se me pasó algún recordatorio?**")
figura("02_tablero.png", "Tablero de control de la campaña (ejemplo con datos ficticios).", [
    (1, "**Menú lateral.** Control, Preparar entrega, Historial y Configuración. El número rojo indica los avisos pendientes de hoy. Abajo se ve su nombre y si Outlook está conectado."),
    (2, "**Panel de hoy.** Resume qué toca hoy y trae los botones para empezar a preparar los avisos (ver abajo)."),
    (3, "**Avance de la campaña.** Porcentaje de avisos enviados, agencias, avisos totales, enviados y borradores."),
    (4, "**Pestañas.** *Todas*, *Pendientes de hoy* (lo que falta preparar hoy) y *Con problema* (agencias bloqueadas o que requieren una decisión)."),
    (5, "**Filtro por ETV.** Muestra solo las agencias de HERMES o de PROSEGUR."),
    (6, "**Fechas.** El tablero muestra el inicio y **cinco fechas a la vez**; se recorren con la barra y las flechas (ver 4.2)."),
    (7, "**Tabla.** Cada símbolo es el estado de un aviso. Pulse un símbolo o el nombre de una agencia para ver su detalle."),
    (8, "**Leyenda.** Qué significa cada símbolo."),
    (9, "**Actualizar.** Vuelve a leer el archivo y el registro (por ejemplo, si otra persona acaba de enviar)."),
    (10, "**Correos de inicio.** Aparece cuando hay agencias con el correo de inicio por preparar (sección 6)."),
    (11, "**Preparar avisos del día.** Abre la revisión previa de los recordatorios de hoy (sección 5)."),
])
h2("4.1 Qué significa cada símbolo")
figura("23_leyenda.png", "Leyenda de estados que aparece al pie del tablero.", ancho=ANCHO_UTIL)
tabla(["Estado", "Qué significa y qué hacer"], [
    ["**Enviado**", "El aviso ya salió. Al pulsar el símbolo se ve quién lo envió y cuándo. No requiere acción."],
    ["**Borrador generado**", "Hay un borrador en el Outlook de quien lo preparó. Falta enviarlo desde Outlook."],
    ["**Pendiente de hoy**", "Hoy toca preparar este aviso. Use el botón del panel de hoy."],
    ["**Requiere decisión**", "Hay algo que decidir, por ejemplo dos hilos posibles, o un envío anterior quedó a medias. Revise el motivo en el detalle."],
    ["**Bloqueado**", "El aviso no puede prepararse: la agencia no tiene correo, o el correo es inválido o ajeno al banco. Corríjalo en Configuración › Agencias y correos."],
    ["**Omitido**", "No se prepara porque ya se envió o ya tiene borrador (por usted o por otra persona)."],
    ["**Vencido: sin registro**", "La fecha ya pasó y el programa no tiene registro del aviso. Puede haberse enviado antes de usar el programa; si no fue así, **falta un recordatorio**."],
    ["**Pendiente futuro**", "Todavía no toca. Se preparará en su fecha de aviso."],
    ["**Vacío**", "Esa agencia no tiene pago en esa fecha."],
], [4.2, ANCHO_UTIL - 4.2])
h2("4.2 Recorrer las fechas")
p("Una campaña tiene unas 36 fechas de pago. Para que se vea con claridad lo que importa, el tablero muestra la columna **Inicio** y "
  "**cinco fechas a la vez**. Al abrir, muestra un día pasado, hoy y los siguientes.")
figura("24_navegacion_fechas.png", "Controles para recorrer las fechas.")
vinetas([
    "**Barra:** arrástrela para recorrer toda la campaña.",
    "**Flechas ‹ ›:** retroceden o avanzan de cinco en cinco fechas.",
    "**Ir a hoy:** vuelve a la fecha de hoy.",
    "**Sin registrar (n fechas):** lleva a la fecha pasada más antigua que tiene avisos sin registro. Úselo para **comprobar si se omitió algún recordatorio**.",
])
h2("4.3 El panel de hoy")
figura("25_panel_hoy.png", "Panel de hoy con los botones de trabajo.")
p("El programa calcula solo qué pago se avisa cada día: normalmente el del día hábil siguiente (los viernes y sábados, el del lunes). "
  "Los feriados se configuran en Configuración › Jefatura y envío. El panel muestra cuántas agencias están **listas**, cuántas **requieren decisión**, "
  "cuántas están **bloqueadas**, con **borrador** o ya **enviadas**.")
h2("4.4 Detalle de una agencia")
p("Pulse el nombre de una agencia o cualquier símbolo para abrir su detalle a la derecha. Muestra la **línea de tiempo** de sus avisos "
  "(inicio y cada recordatorio con su estado y fecha de aviso) y sus **destinatarios** (Para y CC). Cierre el panel con la X o con la tecla Esc.")
figura("03_detalle.png", "Detalle de una agencia.", [
    (1, "Panel de detalle: línea de tiempo de la agencia, motivo del estado seleccionado y destinatarios. El botón **Ver correo** muestra cómo quedaría el aviso."),
])

# ================================================================= 5
h1("5. Enviar los avisos del día (recordatorios)")
p("Esta es la tarea diaria. Sigue siempre tres pasos, que se ven arriba a la derecha de la pantalla: **Revisar**, **Enviar** y **Verificar**.")
h2("Paso 1: abrir la revisión previa")
paso(1, "En el tablero, pulse **Preparar avisos del [día]**. Si el botón está apagado, no hay nada pendiente para hoy.")
paso(2, "El programa revisa cada agencia y busca en su Outlook el hilo del correo de inicio. Puede tardar unos segundos.")
figura("04_revision.png", "Revisión previa de los recordatorios (ejemplo con datos ficticios).", [
    (1, "**Pasos.** Está en el paso 1, Revisar."),
    (2, "**Lista de agencias.** Marque o desmarque con la casilla. Cada fila muestra el destinatario, el hilo al que responderá y su estado."),
    (3, "**Vista previa.** Es el correo exacto que recibirá la agencia: asunto, destinatarios, Excel adjunto y firma. Pulse otra agencia para verlo."),
    (4, "**Enviarme una prueba.** Le envía a usted mismo ese correo, con «[PRUEBA]» en el asunto, para que lo vea en su bandeja."),
    (5, "**Dejar como borradores.** Crea los correos en la carpeta Borradores de su Outlook, sin enviarlos."),
    (6, "**Enviar N correos.** Pasa a la confirmación. Todavía no envía nada."),
])
h3("Estados de la revisión previa")
tabla(["Estado", "Qué significa"], [
    ["**Lista para enviar**", "Todo en orden. Viene marcada."],
    ["**Se omitirá**", "Ya se envió o ya tiene borrador. El motivo indica quién y cuándo. No se puede marcar."],
    ["**Elija el hilo**", "Hay dos o más hilos posibles del correo de inicio. Hay que elegir uno (ver abajo)."],
    ["**Bloqueada**", "Sin correo, con correo inválido o fuera del dominio del banco. Corrija el dato en Agencias y correos."],
], [4.2, ANCHO_UTIL - 4.2])
h2("Paso 2: elegir el hilo cuando hace falta")
p("El recordatorio se envía **como respuesta al correo de inicio** de esa agencia. Si en su Outlook hay un solo hilo, el programa lo usa. "
  "Si hay dos, la fila indica «Elija el hilo…».")
figura("05_revision_hilos.png", "Una agencia con dos hilos posibles: hay que elegir uno antes de poder enviarla.")
vinetas([
    "Abra la lista **Elija el hilo…** y seleccione el correcto. Cada opción muestra la fecha del envío y el buzón donde está. Al elegir, la agencia se marca sola.",
    "**«Sin hilo: respaldo o correo nuevo»** significa que no hay hilo en su Outlook. El programa reconstruye el hilo desde el respaldo guardado en la red o, si no lo hay, envía un correo nuevo.",
])
aviso("Si dos personas trabajan a la vez",
      "Si su monitora u otra persona ya envió un aviso, o dejó un borrador, la agencia aparece como **Se omitirá** con su nombre. "
      "El programa reserva cada aviso antes de enviarlo, así que no es posible que salga dos veces.", "ok")
h2("Paso 3: probar antes de enviar (opcional)")
p("Seleccione una agencia y pulse **Enviarme una prueba**. Recibirá en su bandeja el mismo correo, con «[PRUEBA]» al inicio del asunto, "
  "pero solo para usted. Compruebe la firma, la tabla y el Excel adjunto.")
h2("Paso 4: confirmar el envío")
p("Pulse **Enviar N correos**. Aparece una ventana de confirmación con la lista de agencias que se enviarán.")
figura("06_confirmar.png", "Ventana de confirmación del envío.", [
    (1, "**Pedir confirmación de lectura.** Si la deja marcada, Outlook pedirá a cada agencia que confirme que abrió el correo (ver abajo)."),
    (2, "**Tiempo para anular.** Los correos esperan unos minutos en la Bandeja de salida antes de salir. Durante ese tiempo puede anularlos."),
])
aviso("Mantenga Outlook abierto después de enviar",
      "Los correos salen cuando termina el tiempo de espera. Si cierra Outlook antes, no saldrán hasta que lo vuelva a abrir.", "atencion")
h3("La confirmación de lectura")
p("Si deja marcada la casilla, Outlook pide a cada agencia que confirme la lectura. Usted recibirá en su bandeja un mensaje que empieza con **«Leído:»** "
  "cuando la agencia abra el correo. Tenga presente que:")
vinetas([
    "Si el mensaje **llega**, la agencia abrió el correo.",
    "Si **no llega**, no significa que no lo haya leído: la agencia puede haber rechazado enviar el acuse.",
    "El valor que aparece marcado por defecto se cambia en Configuración › Jefatura y envío.",
])
h2("Paso 5: verificar el resultado y anular si hace falta")
figura("07_resultado.png", "Resultado del envío, con la cuenta regresiva para anular.", [
    (1, "**Anular envío.** Mientras corre la cuenta regresiva puede retirar de la Bandeja de salida los correos que aún no salieron. Pasado ese tiempo, los correos ya salieron y no se pueden anular."),
    (2, "**Resumen.** Correos enviados, omitidos o bloqueados, y con problema."),
    (3, "**Detalle por agencia.** Indica si respondió al hilo original o reconstruyó el hilo desde el respaldo. Una advertencia (por ejemplo, que no se pudo guardar el respaldo en la red) no impide el envío, pero conviene avisar a soporte."),
])
p("Pulse **Volver al control de campaña**: los símbolos de las agencias enviadas cambian a **Enviado**. El detalle queda también en el **Historial**.")
h2("Si descartó un borrador")
p("Si generó borradores y no los envió (por ejemplo, los eliminó en Outlook para rehacerlos), **puede volver a generarlos**: en el tablero pulse **Inicios en borrador (n)** o **Preparar avisos del [día]** y la agencia aparece como «Lista para enviar», "
  "con la nota «Ya tiene un borrador suyo». Elimine el borrador anterior en Outlook para no tenerlo duplicado. "
  "Un borrador de **otra persona** sigue apareciendo como «Se omitirá», para evitar que el mismo aviso salga dos veces.")
h2("Alternativa: dejar como borradores")
p("Si prefiere revisar cada correo en Outlook antes de enviarlo, pulse **Dejar como borradores**. El programa crea los correos en la carpeta Borradores "
  "de su Outlook, con la firma y el Excel adjunto, y el tablero los muestra como **Borrador generado**. Usted los envía desde Outlook.")

# ================================================================= 6
h1("6. Enviar los correos de inicio de campaña")
p("El correo de inicio es el primero que recibe cada agencia en una campaña. Lleva la programación completa en una tabla y el Excel con las filas de esa agencia. "
  "Los recordatorios posteriores responden a este correo.")
p("Cuando hay agencias con el correo de inicio por preparar, el panel de hoy muestra el botón **Correos de inicio (n)** y la etiqueta **por iniciar**.")
figura("21_tablero_inicio.png", "El tablero cuando hay correos de inicio por preparar.", [
    (1, "**Correos de inicio (n).** Abre la revisión previa de los correos de inicio. «n» es la cantidad de agencias pendientes."),
    (2, "**Preparar avisos del día.** Los recordatorios de hoy, que se trabajan aparte."),
])
paso(1, "Pulse **Correos de inicio (n)**. Se abre la misma revisión previa que usa para los recordatorios.")
paso(2, "Revise la lista. Una agencia con **respaldo del inicio** (enviado con la versión anterior o por otra persona) aparece como **Se omitirá**: no se repite.")
paso(3, "Seleccione una agencia para ver el correo: en la vista previa verá quién va en **Para** y en **CC** (la agencia, más la jefatura y el área que haya cargado en Configuración › Jefatura y envío). Puede probarlo con **Enviarme una prueba**.")
paso(4, "Pulse **Enviar N correos**, confirme y verifique el resultado, igual que en la sección 5.")
aviso("Cómo se ordena la tabla del correo",
      ["Al frente van **ETV, Base, N° Pagadores, Agencia, Fecha y Hora** de la entrega; después, el resto del contenido como siempre.",
       "Las filas salen **por fecha y hora de entrega** (y, a igual fecha, por ETV), de modo que quien recibe el correo ve de inmediato a qué ETV debe pedir los fondos cada día. "
       "El Excel adjunto no se reordena: es la programación original de la agencia."], "nota")
figura("22_inicio_revision.png", "Revisión previa de los correos de inicio.", [
    (1, "Lista de agencias. Las que ya tienen respaldo del inicio se omiten; las bloqueadas necesitan un correo válido."),
    (2, "Vista previa: correo **nuevo** con la tabla de la campaña y el Excel de la agencia adjunto."),
    (3, "Botón de envío."),
])
aviso("Cada correo de inicio deja un respaldo",
      "El programa guarda una copia del correo y del Excel en la carpeta BACKUP_CORREOS de SharePoint. Gracias a ella, otra persona puede continuar "
      "con los recordatorios en el mismo hilo. Si anula un correo de inicio a tiempo, su respaldo se retira para que pueda volver a prepararlo.", "nota")
aviso("Texto del correo",
      "El correo de inicio dice «Por encargo del Sr. [nombre y cargo de la jefatura]». Ese nombre se cambia en Configuración › Jefatura y envío.", "nota")

# ================================================================= 7
h1("7. Preparar la entrega a partir del cronograma original")
p("Cada campaña empieza con el **cronograma original**, que no se modifica nunca. De él sale la **entrega**: una copia sin los puntos suspendidos, con las "
  "fechas reprogramadas y sin tres columnas de trabajo. Con esa copia se arman los correos. Esta pantalla hace ese trabajo por usted.")
h2("Paso 1: cargar el cronograma original")
p("Abra **Preparar entrega** en el menú lateral y **arrastre el archivo** del cronograma original a la zona indicada, o pulse **Elegir archivo…**.")
figura("08_entrega_arrastrar.png", "Zona para arrastrar el cronograma original.", [
    (1, "Suelte aquí el Excel (.xlsx) del cronograma original. El archivo original no se modifica."),
])
h2("Paso 2: marcar los puntos suspendidos y reprogramar fechas")
figura("09_entrega_suspendidos.png", "Revisión de puntos suspendidos y fechas reprogramadas.", [
    (1, "**Datos del archivo.** Campaña, cantidad de puntos y de agencias. Si el nombre del archivo y las fechas no coinciden, el programa lo advierte."),
    (2, "**Puntos.** Marque con la casilla los puntos suspendidos: se quitarán de la entrega. Los que tienen la etiqueta **Marcado en rojo** son los que el original ya trae marcados; es una sugerencia, la decisión es suya. "
        "Use **Reprogramar** para cambiar una fecha."),
    (3, "**Origen del cambio.** Anote de dónde viene la instrucción (por ejemplo, «correo de Operaciones del 10/09»). Queda en la bitácora junto a cada cambio."),
    (4, "**Generar y guardar como…** Crea la entrega y le pide dónde guardarla."),
])
aviso("Las suspensiones las indica una persona",
      "El original no dice con certeza qué puntos se suspendieron: llegan por correo. Compare siempre la lista marcada con ese correo antes de generar.", "atencion")
figura("10_entrega_reprogramar.png", "Reprogramar la fecha de un punto.", ancho=9.5)
p("Elija qué fecha cambia (fecha de pago o de entrega) y la nueva fecha. Cada reprogramación aparece en el panel derecho y se puede quitar.")
h2("Paso 3: generar y guardar")
p("Pulse **Generar y guardar como…**. El programa propone el nombre `ENTREGA DE FONDOS ETV [código] [año] difusion.xlsx` y la carpeta donde guardó la última entrega. "
  "Elija una carpeta de SharePoint para que la vea el resto del equipo.")
figura("11_entrega_lista.png", "Entrega generada.")
vinetas([
    "La entrega queda como la **vigente** en su equipo y el programa recuerda la carpeta para la próxima campaña.",
    "Junto al archivo se guarda una **bitácora** con el origen de cada cambio.",
    "Pulse **Ir al control de campaña** para ver la campaña con la entrega nueva.",
])

# ================================================================= 8
h1("8. Historial")
p("El historial registra cada aviso que se preparó o envió con el programa: cuándo, quién, a qué agencia, de qué tipo y con qué resultado.")
figura("12_historial.png", "Historial de avisos.", [
    (1, "**Agencia.** Filtra por una agencia."),
    (2, "**Resultado.** Filtra por enviado, borrador, omitido o anulado, bloqueado o con problema."),
    (3, "**Buscar.** Busca por agencia, usuario o detalle."),
    (4, "**Registros.** Cada fila indica fecha y hora, usuario, agencia, tipo de aviso, estado y detalle."),
])
p("Úselo para responder preguntas como «¿quién envió el recordatorio de Cusco del jueves?» o «¿se envió el inicio de esta agencia?».")

# ================================================================= 9
h1("9. Configuración")
p("La pantalla **Configuración** tiene seis pestañas. Cada cambio queda registrado con quién y cuándo.")
tabla(["Pestaña", "Para qué sirve", "¿Quién lo ve?"], [
    ["**Agencias y correos**", "Ver, agregar, editar, desactivar o eliminar los correos de cada agencia.", "Todas las personas"],
    ["**Mi perfil y firma**", "Su nombre, cargo, anexo y firma de los correos.", "Solo usted"],
    ["**Jefatura y envío**", "Jefatura del correo de inicio, excluidos, minutos para anular, confirmación de lectura, dominio y feriados.", "Todas las personas"],
    ["**Rutas**", "Dónde busca y guarda el programa.", "Cada ruta indica si es de este equipo o compartida"],
    ["**Cambios**", "Historial de los cambios de configuración.", "—"],
    ["**Soporte**", "Versión del programa y exportar el diagnóstico.", "—"],
], [3.9, 8.2, ANCHO_UTIL - 12.1])
h2("9.1 Agencias y correos")
figura("13_config_agencias.png", "Lista de agencias y sus correos.", [
    (1, "Pestañas de la Configuración. La cifra indica cuántas agencias hay."),
    (2, "**Agregar agencia.** Para una agencia nueva en la campaña. También hay **Importar desde Excel** e **Historial de cambios**."),
    (3, "Lista de agencias con sus correos *Para* y *CC* y las acciones **Editar**, **Desactivar** y **Eliminar**."),
])
figura("19_agencia_editar.png", "Editar los correos de una agencia.", ancho=9.5)
vinetas([
    "**Editar:** cambie los correos *Para* y *CC*, uno por línea o separados por «;». El programa valida el formato y que pertenezcan al dominio del banco.",
    "**Desactivar:** pausa la agencia sin perder sus datos. Puede activarla de nuevo.",
    "**Eliminar:** la quita de la lista, con confirmación. El historial conserva quién la eliminó y con qué correos estaba.",
    "**Historial de cambios:** muestra quién cambió qué correo, cuándo y qué tenía antes.",
])
aviso("Una agencia sin correo queda bloqueada",
      "Si una agencia no tiene correo, o el correo es inválido, el tablero la muestra con candado y no se puede enviar. Corrija el dato aquí.", "atencion")
h2("9.2 Mi perfil y firma")
p("Cada persona tiene su propio perfil. El programa arma la firma con el formato del banco: logotipo «60 años», una línea vertical y su bloque de datos.")
figura("14_config_perfil.png", "Perfil y firma de la persona que usa el programa.", [
    (1, "**Datos personales.** Nombre, cargo (opcional), dependencia, teléfono, anexo, dirección y correo. Marque si desea mostrar el correo y el aviso de confidencialidad."),
    (2, "**Qué firma usar.** *La firma del programa* (recomendada) o *Sin firma*."),
    (3, "**Vista previa.** Así saldrá su firma en los correos."),
    (4, "**Guardar perfil.** Debe pulsarlo para que los cambios se apliquen."),
])
aviso("El logotipo se toma de su firma de Outlook",
      ["El programa reutiliza el logotipo «60 años» de una firma que usted ya tenga guardada en Outlook; no se distribuye aparte.",
       "Si la pantalla dice que no encontró el logo, guarde una vez en Outlook una firma que lo incluya (Archivo › Opciones › Correo › Firmas) y vuelva a abrir el perfil."], "nota")
h2("9.3 Jefatura y envío")
figura("15_config_general.png", "Datos que se comparten con todas las personas.", [
    (1, "**Jefatura del correo de inicio.** Nombre y cargo que aparecen en «Por encargo del Sr. …». No es la firma de quien envía."),
    (2, "**Excluidos de los recordatorios.** Correos que reciben el correo de inicio pero no los recordatorios (por ejemplo, la jefatura)."),
    (3, "**Con copia en los correos.** La jefatura y los integrantes del área que reciben copia (CC) del correo de inicio y de los recordatorios que no van como respuesta al hilo. "
        "Se suman a la copia de cada agencia (el administrador) y no se repiten. Los «excluidos» no reciben copia de los recordatorios."),
    (4, "**Minutos para anular un envío.** Tiempo de espera antes de que salgan los correos. Con 0, salen de inmediato."),
    (5, "**Pedir confirmación de lectura.** Valor inicial de la casilla al enviar; se puede cambiar en cada envío."),
    (6, "**Feriados.** Uno por línea, en formato AAAA-MM-DD. Los fines de semana ya se consideran no hábiles."),
])
p("Pulse **Guardar cambios** (arriba a la derecha) para aplicarlos. Estos datos los ven **todas las personas**: lo que cambie aquí cambia para todas.")
aviso("Cómo quedan los destinatarios",
      ["**Para** y **CC de la agencia:** salen de la lista de la pestaña Agencias y correos (jefe de pago y administrador).",
       "**Vienen cargados** la jefatura y tres integrantes del área, tomados de un correo de inicio anterior. Revíselos y ajústelos si cambió el equipo. Para agregar varios a la vez, pegue la línea de CC copiada desde Outlook.",
       "**Con copia en los correos:** se suma al CC de cada agencia en el correo de inicio. En los recordatorios que responden al hilo, la copia ya viene del correo de inicio, salvo los excluidos."],
      "nota")
h2("9.4 Rutas: qué debe tener cada equipo")
p("Las rutas indican dónde busca y guarda el programa. Cada una muestra debajo de su nombre si es **«Solo este equipo»** (no afecta a nadie más) o "
  "**«Compartida con todos»**.")
figura("16_config_rutas.png", "Rutas del programa.", [
    (1, "**Entrega vigente.** El archivo que alimenta los correos."),
    (2, "**Carpeta del cronograma original.** Dónde llegan los originales (opcional)."),
    (3, "**Carpeta donde se guarda la entrega generada.**"),
    (4, "**Respaldo de correos (BACKUP_CORREOS).** Compartida con todos."),
    (5, "**Carpeta compartida del programa.** Registro, agencias y perfiles."),
    (6, "**Excel de origen de la lista de agencias.** Solo se usa para importar la lista antigua."),
])
tabla(["Ruta", "Alcance", "Qué poner"], [
    ["**Entrega vigente**", "Este equipo", ["**Déjela vacía**: el programa detecta solo la entrega más reciente. Si la cambia, que sea un archivo de SharePoint, no de Descargas."]],
    ["**Carpeta del cronograma original**", "Este equipo", "Opcional. La carpeta de SharePoint donde llegan los cronogramas originales."],
    ["**Carpeta donde se guarda la entrega**", "Este equipo", "La carpeta **ENTREGA DE FONDOS** de SharePoint, para que el resto del equipo vea la entrega. Evite carpetas locales."],
    ["**Respaldo de correos (BACKUP_CORREOS)**", "Compartida", "La carpeta BACKUP_CORREOS de SharePoint. Si la deja vacía, usa la de siempre."],
    ["**Carpeta compartida del programa**", "Este equipo", "**Déjela vacía.** Usa BACKUP_CORREOS\\_PROGRAMA. Si la cambia, el cambio se aplica al volver a abrir el programa."],
    ["**Excel de origen de la lista de agencias**", "Este equipo", "Déjelo vacío. Solo sirve para importar la lista antigua."],
], [4.6, 2.4, ANCHO_UTIL - 7.0])
aviso("Qué debe hacer en cada equipo nuevo",
      ["1. Instalar el programa (sección 2).",
       "2. Abrirlo y completar **Mi perfil y firma** (sección 9.2).",
       "3. Comprobar en **Rutas** que la carpeta compartida es la de SharePoint y está **Accesible**.",
       "Nada más: las agencias, la jefatura y los feriados ya están compartidos."], "importante")
h2("9.5 Cambios y 9.6 Soporte")
figura("17_config_cambios.png", "Cambios de configuración registrados.")
p("La pestaña **Cambios** lista cada modificación de configuración con quién la hizo, cuándo y qué valor tenía antes.")
figura("18_config_soporte.png", "Soporte y diagnóstico.", [
    (1, "**Exportar diagnóstico…** Genera un archivo .zip con el registro de actividad y un resumen del equipo. **No incluye correos de agencias ni el contenido de los avisos.** Envíelo a quien mantiene el programa si algo falla."),
])

# ================================================================= 10
h1("10. Cuando llega una campaña nueva")
p("Al comenzar una campaña, el orden de trabajo es el siguiente:")
paso(1, "**Preparar la entrega** (sección 7): cargue el cronograma original, marque los puntos suspendidos y las fechas reprogramadas, y guarde la entrega en SharePoint.")
paso(2, "**Enviar los correos de inicio** (sección 6): pulse **Correos de inicio (n)**, revise y envíe.")
paso(3, "**Cada día, enviar los recordatorios** (sección 5): pulse **Preparar avisos del [día]**.")
paso(4, "**Comprobar que no falte nada:** use **Sin registrar (n fechas)** para detectar recordatorios que se pasaron.")
h2("Aviso de entrega más reciente")
p("Si en las carpetas conocidas aparece la entrega de una campaña posterior a la que está usando, el tablero lo avisa y ofrece usarla con un botón. "
  "Cambiar de entrega solo afecta a su equipo.")
figura("20_entrega_nueva.png", "Aviso de que hay una entrega más reciente.", [
    (1, "**Usar esa entrega.** Cambia a la entrega de la campaña nueva. No hay que buscar el archivo."),
])

# ================================================================= 11
h1("11. Problemas frecuentes")
tabla(["Qué ve", "Por qué ocurre", "Qué hacer"], [
    ["«No se pudo abrir la carpeta compartida de SharePoint…»", "No hay conexión con SharePoint o la carpeta no responde.",
     "Revise su conexión (red del banco o VPN), abra la carpeta de SharePoint en el Explorador y pulse **Actualizar**. Mientras tanto solo podrá crear borradores, para no duplicar avisos."],
    ["«La carpeta de entregas no respondió a tiempo…»", "SharePoint tardó más de lo normal.", "Espere un momento y pulse **Actualizar**."],
    ["«Outlook no respondió…»", "Outlook tiene una ventana abierta esperando una respuesta (aviso de seguridad, inicio de sesión) o está cerrado.",
     "Revise Outlook, cierre cualquier ventana pendiente y pulse **Actualizar**. Si no se resuelve, cierre Outlook y ábralo de nuevo."],
    ["«No se encontró la entrega vigente…»", "No hay una entrega en las carpetas conocidas.", "Pulse **Elegir una entrega…** o prepárela desde el original (sección 7)."],
    ["Agencia con candado, «Bloqueada»", "La agencia no tiene correo, o es inválido o ajeno al banco.", "Corrija el correo en Configuración › Agencias y correos."],
    ["«Elija el hilo»", "Hay dos hilos posibles del correo de inicio.", "Elíjalo en la lista de la fila (sección 5)."],
    ["«Destinatarios que Outlook no pudo resolver…»", "Un correo de la lista no existe en el directorio.", "Corrija el correo de la agencia."],
    ["«Otra persona cambió la configuración…»", "Alguien guardó cambios mientras usted tenía la pantalla abierta.", "Cambie de pestaña o vuelva a abrir Configuración y repita su cambio."],
    ["Advertencia «No se pudo guardar el respaldo en la red»", "El correo salió, pero la copia de respaldo no se guardó.", "Avise a soporte: otra persona podría no encontrar el hilo para los recordatorios."],
    ["La ventana dice «Conectando…» mucho tiempo", "El programa espera la respuesta de SharePoint u Outlook.", "Espere hasta 30 segundos. Si sigue igual, ciérrelo, ábralo de nuevo y exporte el diagnóstico."],
    ["Ventana «El programa no pudo iniciar»", "Falló algo al arrancar.", "Envíe el archivo de registro que indica la ventana (carpeta %APPDATA%\\AgenteCorreosBN)."],
], [4.6, 5.0, ANCHO_UTIL - 9.6], tam=9.5)

# ================================================================= 12
h1("12. Preguntas frecuentes")
for q, a in [
    ("¿Se modifica el cronograma original?", "No. El original es de solo lectura. Todos los cambios se hacen en la entrega, que es una copia."),
    ("¿Y si mi monitora también envía los correos?", "No hay problema. El programa registra cada aviso en una carpeta compartida y lo reserva antes de enviarlo: si ella ya lo envió o dejó un borrador, a usted le aparece como «Se omitirá»."),
    ("¿Qué significa «Vencido: sin registro»?", "Que la fecha ya pasó y el programa no tiene registro. Puede haberse enviado antes de usar el programa, desde Outlook. Si no fue así, falta un recordatorio."),
    ("¿Quién recibe copia de los correos?", "Para: el jefe de pago de la agencia. CC: el administrador de la agencia y las personas que figuren en Configuración › Jefatura y envío › «Con copia en los correos» (la jefatura y el resto del área). Se puede ver en la vista previa antes de enviar."),
    ("Descarté un borrador y no me deja generarlo otra vez.", "Los borradores propios se pueden volver a generar. Si el botón del tablero no aparece, use «Inicios en borrador (n)» o «Preparar avisos del [día]». Los borradores de otra persona se omiten a propósito."),
    ("¿Puedo anular un correo después de enviarlo?", "Solo durante los minutos de espera que se indican al enviar, desde el botón **Anular envío** de la pantalla de resultado. Pasado ese tiempo el correo ya salió."),
    ("¿Dónde se guardan mis datos?", "Su perfil y firma, la lista de agencias y el registro de avisos, en la carpeta compartida de SharePoint. Las rutas propias de su equipo y el archivo de diagnóstico (registro técnico), en la carpeta del programa de su usuario de Windows."),
    ("¿Qué es el respaldo?", "La copia de cada correo de inicio y de su Excel, guardada en BACKUP_CORREOS. Permite que cualquier persona continúe los recordatorios en el mismo hilo."),
    ("¿Qué pasa si no tengo firma en Outlook?", "No hay problema: el programa usa su perfil. Solo el logotipo se toma de una firma de Outlook; sin ella la firma sale sin logotipo."),
    ("¿Cómo pido ayuda?", "Exporte el diagnóstico (Configuración › Soporte) y envíelo con una breve descripción de lo que ocurrió."),
]:
    par = doc.add_paragraph()
    par.paragraph_format.keep_with_next = True
    par.paragraph_format.space_after = Pt(1)
    par.paragraph_format.space_before = Pt(6)
    fuente(par.add_run(q), negrita=True, color=TINTA)
    p(a)

h2("Glosario")
tabla(["Término", "Significado"], [
    ["**Campaña**", "Período de pagos, por ejemplo «Julio – Agosto 2026». El nombre indica el período cubierto; los pagos caen dos meses después."],
    ["**Cronograma original**", "El archivo con que empieza la campaña. No se modifica."],
    ["**Entrega**", "Copia del cronograma sin los puntos suspendidos y con las fechas reprogramadas. De ella salen los correos."],
    ["**Correo de inicio**", "El primer correo de cada campaña a cada agencia, con la programación completa."],
    ["**Recordatorio**", "Correo de seguimiento por cada fecha de pago, en el hilo del correo de inicio."],
    ["**Hilo**", "La conversación de correo de una agencia, que empieza con el correo de inicio."],
    ["**Respaldo**", "Copia del correo de inicio y su Excel en BACKUP_CORREOS."],
    ["**ETV**", "Empresa de transporte de valores (HERMES, PROSEGUR)."],
], [4.2, ANCHO_UTIL - 4.2])

par = doc.add_paragraph()
par.paragraph_format.space_before = Pt(18)
fuente(par.add_run("Contacto"), negrita=True, color=TINTA)
p("Ana B. Pérez Quispe · Sección Caja y Valores en Custodia · Subgerencia Caja y Valores · Gerencia de Operaciones · Banco de la Nación. "
  "Telf. 519-2000, Anexo 12345.")

doc.core_properties.title = "Agente de Correos BN · Manual de usuario"
doc.core_properties.author = "Sección Caja y Valores en Custodia"
doc.core_properties.subject = "Manual de usuario, versión 2.0"
doc.save(SALIDA)
print("Guardado:", SALIDA)
