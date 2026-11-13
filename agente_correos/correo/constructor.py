"""Arma el correo completo (asunto, destinatarios, cuerpo, firma, adjunto) sin tocar Outlook.

La vista previa de la pantalla y el envío usan exactamente el mismo `CorreoPreparado`.
"""

from __future__ import annotations

import html as _html
import re
from datetime import date
from pathlib import Path
from typing import List, Optional

import pandas as pd

from ..configuracion import Configuracion
from ..contenido.plantillas import Plantillas, Programas, asunto_inicio, asunto_recordatorio, fecha_de_inicio
from ..contenido.tabla_html import construir_tabla
from ..datos.cronograma_loader import programas_activos
from ..datos.directorio_agencias import Destinatarios
from ..dominio.avisos import TipoAviso
from ..dominio.campana import Campana
from ..usuario.firma import CID_LOGO, construir_firma
from ..usuario.perfil import PerfilUsuario
from .buscador_hilo import sin_prefijos
from .modelos import CorreoPreparado, MensajeEncontrado
from .respaldo_red import Respaldo

_BODY = re.compile(r"(<body[^>]*>)", re.IGNORECASE)


def insertar_en_cuerpo(html_existente: str, nuevo: str) -> str:
    """Pone `nuevo` al comienzo del <body> de un correo ya armado (p. ej. una respuesta de Outlook)."""
    partes = _BODY.split(html_existente or "", maxsplit=1)
    if len(partes) == 3:
        return partes[0] + partes[1] + nuevo + "<br><br>" + partes[2]
    return nuevo + "<br><br>" + (html_existente or "")


def _sin_excluidos(correos: List[str], excluidos: List[str]) -> List[str]:
    quitar = {e.strip().lower() for e in excluidos}
    return [c for c in correos if c.lower() not in quitar]


class ConstructorCorreo:
    def __init__(self, config: Configuracion):
        self._cfg = config
        self._plantillas = Plantillas(config)

    # ------------------------------------------------------------------
    def inicio(self, agencia: str, filas: pd.DataFrame, campana: Campana, dest: Destinatarios,
               perfil: PerfilUsuario, logo: Optional[Path] = None,
               adjunto: Optional[Path] = None) -> CorreoPreparado:
        juntos, contigo = programas_activos(filas)
        tabla = construir_tabla(filas, juntos, contigo, es_recordatorio=False)
        cuerpo = self._plantillas.cuerpo_inicio(agencia, fecha_de_inicio(filas), campana.nombre, tabla,
                                                Programas(juntos, contigo))
        firma, firma_outlook, logo_usado = self._firma(perfil, logo)
        return CorreoPreparado(
            agencia=agencia, tipo=TipoAviso.INICIO,
            asunto=asunto_inicio(agencia, campana.nombre),
            para=list(dest.para), cc=self._con_copia_fija(dest.cc, dest.para),
            html=cuerpo + ("<br><br>" + firma if firma else ""),
            modo="nuevo", adjuntos=[adjunto] if adjunto else [], logo=logo_usado, firma_outlook=firma_outlook,
        )

    def recordatorio(self, agencia: str, filas: pd.DataFrame, objetivo: date, hoy: date, campana: Campana,
                     dest: Destinatarios, perfil: PerfilUsuario, logo: Optional[Path] = None,
                     adjunto: Optional[Path] = None, hilo: Optional[MensajeEncontrado] = None,
                     respaldo: Optional[Respaldo] = None) -> CorreoPreparado:
        juntos, contigo = programas_activos(filas)
        tabla = construir_tabla(filas, juntos, contigo, es_recordatorio=True)
        cuerpo = self._plantillas.cuerpo_recordatorio(agencia, objetivo, hoy, campana.nombre, tabla)
        firma, firma_outlook, logo_usado = self._firma(perfil, logo)
        nuevo = cuerpo + ("<br><br>" + firma if firma else "")
        excluidos = list(self._cfg.correos_excluidos)
        advertencias: List[str] = []

        if hilo is not None:
            return CorreoPreparado(
                agencia=agencia, tipo=TipoAviso.RECORDATORIO, fecha_objetivo=objetivo,
                asunto="RECORDATORIO: " + sin_prefijos(hilo.asunto),
                para=[], cc=[], html=nuevo, modo="respuesta", id_hilo=hilo.id,
                adjuntos=[adjunto] if adjunto else [], logo=logo_usado, firma_outlook=firma_outlook,
                excluir=excluidos, dominio=self._cfg.dominio_interno,
            )

        para = _sin_excluidos(respaldo.para if respaldo and respaldo.para else list(dest.para), excluidos)
        cc = self._con_copia_fija(_sin_excluidos(list(dest.cc), excluidos), para, quitar=excluidos)
        asunto = asunto_recordatorio(agencia, campana.nombre)
        if respaldo is not None and respaldo.html:
            modo = "reconstruido"
            nuevo += self._cita(respaldo, campana, agencia)
        else:
            modo = "nuevo"
            advertencias.append("No hay hilo en este Outlook ni respaldo en red: sale como correo independiente.")
        return CorreoPreparado(
            agencia=agencia, tipo=TipoAviso.RECORDATORIO, fecha_objetivo=objetivo, asunto=asunto,
            para=para, cc=cc, html=nuevo, modo=modo, adjuntos=[adjunto] if adjunto else [],
            logo=logo_usado, firma_outlook=firma_outlook, advertencias=advertencias,
        )

    # ------------------------------------------------------------------
    def _con_copia_fija(self, cc: List[str], para: List[str], quitar: List[str] = ()) -> List[str]:
        """La copia de la agencia más la copia fija del área, sin repetir a nadie ni a quien ya va en Para."""
        vistos = {x.strip().lower() for x in para}
        quitar = {x.strip().lower() for x in quitar}
        salida: List[str] = []
        for correo in list(cc) + list(self._cfg.copia_fija):
            clave = correo.strip().lower()
            if not clave or clave in vistos or clave in quitar:
                continue
            vistos.add(clave)
            salida.append(correo.strip())
        return salida

    @staticmethod
    def _firma(perfil: PerfilUsuario, logo: Optional[Path]):
        if perfil.modo_firma == "ninguna":
            return "", False, None
        if perfil.modo_firma == "outlook":
            return "", True, None
        logo = logo if logo and Path(logo).is_file() else None
        return construir_firma(perfil, logo_src=f"cid:{CID_LOGO}" if logo else None), False, logo

    @staticmethod
    def _cita(respaldo: Respaldo, campana: Campana, agencia: str) -> str:
        """Cabecera de mensaje citado, igual que v1, seguida del cuerpo original archivado."""
        e = _html.escape
        cuando = respaldo.guardado_en.strftime("%d/%m/%Y %H:%M") if respaldo.guardado_en else "(fecha desconocida)"
        asunto = respaldo.asunto or asunto_inicio(agencia, campana.nombre)
        return (
            '<br><br><hr align="center" size="2" width="100%" tabindex="-1">'
            '<div style="font-family:Calibri,sans-serif;font-size:10pt;color:#555;direction:ltr;">'
            f"<b>De:</b> {e(respaldo.enviado_por)}<br><b>Enviado:</b> {cuando}<br>"
            f"<b>Para:</b> {e('; '.join(respaldo.para))}<br><b>Asunto:</b> {e(asunto)}<br></div><br>"
            f"{respaldo.html}"
        )
