"""Asuntos y cuerpos de los correos. Los textos son los de v1; lo que cambia ahora es configurable."""

from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import date
from typing import Optional

import pandas as pd

from ..configuracion import Configuracion
from ..reglas.fecha_objetivo import fecha_larga, fecha_larga_mayusculas, texto_relativo


@dataclass(frozen=True)
class Programas:
    juntos: bool = False
    contigo: bool = False


def asunto_inicio(agencia: str, campana: str) -> str:
    return f"Programación de Fondos – BN {agencia} – {campana}"


def asunto_recordatorio(agencia: str, campana: str) -> str:
    return f"RECORDATORIO: Entrega de Fondos – BN {agencia} – {campana}"


def fecha_de_inicio(filas: pd.DataFrame) -> Optional[date]:
    """Primera fecha de la agencia: entrega de fondos si existe esa columna, si no fecha de pago."""
    columna = "Fecha_Entrega" if "Fecha_Entrega" in filas.columns else "Fecha_Pago"
    if columna not in filas.columns:
        return None
    fechas = pd.to_datetime(filas[columna], errors="coerce", dayfirst=True, format="mixed").dropna()
    return fechas.min().date() if not fechas.empty else None


class Plantillas:
    def __init__(self, config: Configuracion):
        self._cfg = config

    def cuerpo_inicio(self, agencia: str, fecha_inicio: Optional[date], campana: str,
                      tabla: str, programas: Programas) -> str:
        nombres = ["PENSIÓN 65"]
        if programas.juntos:
            nombres.append("JUNTOS")
        if programas.contigo:
            nombres.append("CONTIGO")
        negritas = [f"<b>{n}</b>" for n in nombres]
        if len(negritas) > 1:
            menciona = "los Programas Sociales " + ", ".join(negritas[:-1]) + " y " + negritas[-1]
        else:
            menciona = "el Programa Social " + negritas[0]

        inicia = fecha_larga_mayusculas(fecha_inicio) if fecha_inicio else "PRÓXIMAMENTE"
        encargo = html.escape(f"{self._cfg.por_encargo_nombre} - {self._cfg.por_encargo_cargo}")
        obs = html.escape(self._cfg.obs_prosegur_inicio)
        return (
            '<div style="font-family:Calibri,sans-serif;font-size:11pt;color:#222;">'
            f"<p>Estimados buenos días,<br><b>BN &ndash; {html.escape(agencia)}</b></p>"
            f"<p>Por encargo del Sr. <b>{encargo}</b>, y por medio de la presente, se solicita programar "
            f'la entrega de fondos, que inicia el <b><span style="background:yellow">{inicia}</span></b>, '
            f"con el fin de realizar los pagos a los usuarios de {menciona}, les recordamos entregar los "
            f"fondos a las ETV correspondientes a la campaña de pagos {html.escape(campana)}.</p>"
            '<p><b><span style="font-size:12pt;color:#C00000">Se adjunta archivo en formato Excel con la '
            "programación detallada de la presente campaña.</span></b></p>"
            f'<p><i><b><span style="font-size:11pt;background:aqua">Obs.: {obs}</span></b></i></p>'
            "<p>Agradecemos de antemano su atención y coordinación para el cumplimiento oportuno de "
            "estas obligaciones.</p>"
            f"<br>{tabla}<br></div>"
        )

    def cuerpo_recordatorio(self, agencia: str, objetivo: date, hoy: date, campana: str, tabla: str) -> str:
        obs = html.escape(self._cfg.obs_prosegur_recordatorio)
        return (
            '<div style="font-family:Calibri;font-size:11pt;color:black;">'
            f"<p>Estimado(a) buenos días,<br><b>BN – {html.escape(agencia)}</b></p>"
            f"<p>Se le recuerda que para {texto_relativo(objetivo, hoy)} "
            f'<b><span style="background:yellow;mso-highlight:yellow">{fecha_larga(objetivo)}</span></b>, '
            "se debe programar la entrega de fondos a la ETV indicada.</p>"
            '<p><b><span style="font-size:12.0pt;color:#C00000">Se adjunta archivo en formato Excel con la '
            "programación detallada de dicha campaña.</span></b></p>"
            '<p><b><i><span style="font-size:12.0pt;background:aqua;mso-highlight:aqua">'
            f"Obs: {obs}</span></i></b></p>"
            f"<p>De antemano se agradece por el cumplimiento del calendario asignado para esta campaña "
            f"({html.escape(campana)}).</p>"
            f"<br>{tabla}<br></div>"
        )
