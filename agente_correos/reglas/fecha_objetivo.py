"""Reglas de calendario: qué día se avisa, y cómo se nombra la fecha en el correo."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


class CalendarioHabil:
    """Días hábiles = lunes a viernes que no estén en la lista de feriados."""

    def __init__(self, feriados: Iterable[date] = ()):
        self._feriados = set(feriados)

    def es_habil(self, dia: date) -> bool:
        return dia.weekday() < 5 and dia not in self._feriados

    def siguiente_habil(self, desde: date) -> date:
        """Primer día hábil estrictamente posterior a `desde`."""
        dia = desde + timedelta(days=1)
        while not self.es_habil(dia):
            dia += timedelta(days=1)
        return dia

    def anterior_habil(self, hasta: date) -> date:
        """Último día hábil estrictamente anterior a `hasta`."""
        dia = hasta - timedelta(days=1)
        while not self.es_habil(dia):
            dia -= timedelta(days=1)
        return dia

    # ---- reglas del negocio ---------------------------------------------
    def objetivo_de_hoy(self, hoy: date) -> date:
        """Fecha de pago que se recuerda hoy: el siguiente día hábil (viernes → lunes)."""
        return self.siguiente_habil(hoy)

    def fecha_de_aviso(self, fecha_pago: date) -> date:
        """Día en que corresponde enviar el recordatorio de una fecha de pago: la víspera hábil."""
        return self.anterior_habil(fecha_pago)


def texto_relativo(objetivo: date, hoy: date) -> str:
    """'el día de mañana' / 'el día de hoy' / 'el lunes'."""
    dias = (objetivo - hoy).days
    if dias == 1:
        return "el día de mañana"
    if dias == 0:
        return "el día de hoy"
    return f"el {DIAS[objetivo.weekday()]}"


def fecha_larga(dia: date) -> str:
    """'14 de octubre de 2026' (día con dos cifras, como en v1)."""
    return f"{dia.day:02d} de {MESES[dia.month - 1]} de {dia.year}"


def fecha_larga_mayusculas(dia: date) -> str:
    """'14 DE OCTUBRE DE 2026', para el correo de inicio."""
    return fecha_larga(dia).upper()
