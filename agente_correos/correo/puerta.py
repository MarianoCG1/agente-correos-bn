"""Lo que el programa necesita de Outlook, como interfaz. Así el resto se prueba sin Outlook."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Protocol, Set

from .modelos import CorreoEnviado, CorreoPreparado, IdentidadOutlook, MensajeEncontrado, ResultadoPuerta

ACCIONES = ("borrador", "enviar", "prueba")


class ErrorCorreo(Exception):
    """Outlook no pudo completar la operación; el mensaje se puede mostrar a la persona."""


class PuertaCorreo(Protocol):
    def disponible(self) -> bool: ...

    def identidad(self) -> IdentidadOutlook: ...

    def buscar_enviados(self, asunto: str) -> List[MensajeEncontrado]: ...

    def enviados_desde(self, fragmento: str, desde: datetime,
                       omitir: Optional[Set[str]] = None) -> List[CorreoEnviado]:
        """Solo lectura: lo enviado desde `desde` cuyo asunto contiene `fragmento` (el nombre de la campaña),
        del más reciente al más antiguo. Los ids de `omitir` ya se revisaron y no se vuelven a leer."""
        ...

    def crear(self, correo: CorreoPreparado, accion: str, diferir_minutos: int = 0,
              prueba_para: str = "") -> ResultadoPuerta:
        """Crea el correo en Outlook. `accion`: 'borrador' lo guarda, 'enviar' lo envía (con espera
        opcional para poder anularlo) y 'prueba' lo envía solo a `prueba_para`."""
        ...

    def verificar(self, id_outlook: str) -> dict: ...

    def anular(self, correos: List[tuple]) -> int:
        """Retira de la Bandeja de salida los correos enviados con espera que aún no salieron.
        `correos`: pares (asunto, para). Devuelve cuántos retiró."""
        ...
