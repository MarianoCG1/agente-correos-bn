"""Única clase que habla con Outlook (COM). Todo lo demás del programa trabaja contra `PuertaCorreo`.

Cada hilo debe inicializar COM; pywebview ejecuta cada llamada de la interfaz en un hilo distinto,
por eso la conexión se guarda por hilo y no se comparte.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta
from typing import Any, List, Optional, Set

from .buscador_hilo import sin_prefijos
from .constructor import insertar_en_cuerpo
from .modelos import CorreoEnviado, CorreoPreparado, IdentidadOutlook, MensajeEncontrado, ResultadoPuerta
from .puerta import ACCIONES, ErrorCorreo

log = logging.getLogger(__name__)

_OL_MAIL = 43
_CARPETA_ENVIADOS = 5
_PR_ATTACH_CONTENT_ID = "http://schemas.microsoft.com/mapi/proptag/0x3712001F"
_PR_ATTACHMENT_HIDDEN = "http://schemas.microsoft.com/mapi/proptag/0x7FFE000B"


def _a_datetime(valor: Any):
    try:
        return datetime(valor.year, valor.month, valor.day, valor.hour, valor.minute, valor.second)
    except Exception:
        return None


def _smtp(recipiente: Any) -> str:
    """Dirección SMTP real aunque Outlook devuelva una dirección interna de Exchange."""
    try:
        entrada = recipiente.AddressEntry
        if entrada is not None and entrada.AddressEntryUserType in (0, 10):
            usuario = entrada.GetExchangeUser()
            if usuario is not None and usuario.PrimarySmtpAddress:
                return usuario.PrimarySmtpAddress.lower()
    except Exception:
        pass
    try:
        return (recipiente.Address or "").lower()
    except Exception:
        return ""


class OutlookGateway:
    def __init__(self) -> None:
        self._local = threading.local()

    # ---- conexión -----------------------------------------------------
    def _app(self):
        app = getattr(self._local, "app", None)
        if app is None:
            try:
                import pythoncom
                import win32com.client
                pythoncom.CoInitialize()
                app = win32com.client.Dispatch("Outlook.Application")
            except Exception as exc:
                raise ErrorCorreo(f"No se pudo conectar con Outlook: {exc}") from exc
            self._local.app = app
        return app

    def _mapi(self):
        return self._app().GetNamespace("MAPI")

    def disponible(self) -> bool:
        try:
            self._app()
            return True
        except ErrorCorreo:
            return False

    # ---- identidad ----------------------------------------------------
    def identidad(self) -> IdentidadOutlook:
        """Datos de quien tiene abierto Outlook, del directorio de Exchange."""
        try:
            actual = self._mapi().CurrentUser
            ident = IdentidadOutlook(nombre=str(actual.Name or ""))
            usuario = actual.AddressEntry.GetExchangeUser()
            if usuario is not None:
                ident.correo = str(usuario.PrimarySmtpAddress or "").lower()
                ident.cargo = str(getattr(usuario, "JobTitle", "") or "")
                ident.telefono = str(getattr(usuario, "BusinessTelephoneNumber", "") or "")
                ident.oficina = str(getattr(usuario, "OfficeLocation", "") or "")
                ident.departamento = str(getattr(usuario, "Department", "") or "")
            return ident
        except ErrorCorreo:
            raise
        except Exception as exc:
            log.warning("No se pudo leer la identidad desde Outlook: %s", exc)
            return IdentidadOutlook()

    # ---- búsqueda -----------------------------------------------------
    def buscar_enviados(self, asunto: str, maximo: int = 40) -> List[MensajeEncontrado]:
        """Correos enviados cuyo asunto contiene el de inicio (sin RE:/RV:). La decisión final es de
        `elegir_hilo`: aquí solo se acota la búsqueda para no recorrer toda la carpeta."""
        fragmento = sin_prefijos(asunto).replace("'", "''")
        filtro = f"@SQL=\"urn:schemas:httpmail:subject\" LIKE '%{fragmento}%'"
        encontrados: List[MensajeEncontrado] = []
        almacenes = self._mapi().Stores
        for i in range(1, almacenes.Count + 1):
            try:
                almacen = almacenes.Item(i)
                enviados = almacen.GetDefaultFolder(_CARPETA_ENVIADOS)
                for n, item in enumerate(enviados.Items.Restrict(filtro)):
                    if n >= maximo:
                        break
                    if getattr(item, "Class", 0) != _OL_MAIL:
                        continue
                    encontrados.append(MensajeEncontrado(
                        id=str(item.EntryID), asunto=str(item.Subject or ""), para=str(item.To or ""),
                        enviado_en=_a_datetime(item.SentOn), es_enviado=True,
                        almacen=str(almacen.DisplayName)))
            except Exception as exc:                      # un buzón sin Enviados o sin permiso no frena el resto
                log.warning("Almacén omitido al buscar en Enviados: %s", exc)
        return encontrados

    def enviados_desde(self, fragmento: str, desde: datetime, omitir: Optional[Set[str]] = None,
                       maximo: int = 3000) -> List[CorreoEnviado]:
        """Solo lectura de la carpeta Enviados: asunto, fecha y destinatarios de los correos de la campaña.
        El cuerpo se lee únicamente en los recordatorios (para saber a qué fecha de pago corresponden)."""
        omitir = omitir or set()
        filtro = "@SQL=\"urn:schemas:httpmail:subject\" LIKE '%" + fragmento.replace("'", "''") + "%'"
        salida: List[CorreoEnviado] = []
        almacenes = self._mapi().Stores
        for i in range(1, almacenes.Count + 1):
            try:
                items = almacenes.Item(i).GetDefaultFolder(_CARPETA_ENVIADOS).Items.Restrict(filtro)
                items.Sort("[SentOn]", True)                       # del más reciente al más antiguo
                for n, item in enumerate(items):
                    if n >= maximo:
                        break
                    if getattr(item, "Class", 0) != _OL_MAIL:
                        continue
                    enviado = _a_datetime(item.SentOn)
                    if enviado is not None and enviado < desde:
                        break
                    id_item = str(item.EntryID)
                    if id_item in omitir:
                        continue
                    asunto = str(item.Subject or "")
                    texto = str(item.Body or "")[:3000] if asunto.strip().upper().startswith("RECORDATORIO") else ""
                    salida.append(CorreoEnviado(id_item, asunto, enviado, str(item.To or ""), texto))
            except Exception as exc:                          # un buzón sin Enviados o sin permiso no frena el resto
                log.warning("Almacén omitido al revisar Enviados: %s", exc)
        return salida

    # ---- creación y envío ---------------------------------------------
    def crear(self, correo: CorreoPreparado, accion: str, diferir_minutos: int = 0,
              prueba_para: str = "") -> ResultadoPuerta:
        if accion not in ACCIONES:
            raise ErrorCorreo(f"Acción desconocida: {accion}")
        if accion == "prueba" and not prueba_para:
            raise ErrorCorreo("Falta el correo al que se envía la prueba.")

        item = self._armar(correo)
        advertencias: List[str] = []

        if accion == "prueba":
            item.Subject = "[PRUEBA] " + str(item.Subject)
            for i in range(item.Recipients.Count, 0, -1):
                item.Recipients.Remove(i)
            item.Recipients.Add(prueba_para)
            item.Recipients.ResolveAll()
        else:
            sin_resolver = self._sin_resolver(item)
            if sin_resolver:
                if accion == "enviar":
                    raise ErrorCorreo("Destinatarios que Outlook no pudo resolver: " + ", ".join(sin_resolver))
                advertencias.append("Destinatarios sin resolver: " + ", ".join(sin_resolver))

        if correo.confirmar_lectura and accion != "prueba":
            item.ReadReceiptRequested = True

        item.Save()
        id_outlook = str(item.EntryID)
        resultado = ResultadoPuerta(id_outlook, str(item.To or ""), str(item.CC or ""), advertencias)

        if accion in ("enviar", "prueba"):
            if diferir_minutos > 0 and accion == "enviar":
                item.DeferredDeliveryTime = datetime.now() + timedelta(minutes=diferir_minutos)
            item.Send()
        return resultado

    def _armar(self, c: CorreoPreparado):
        app = self._app()
        if c.modo == "respuesta":
            if not c.id_hilo:
                raise ErrorCorreo("Falta el hilo al que se responde.")
            original = self._mapi().GetItemFromID(c.id_hilo)
            item = original.ReplyAll()
            self._limpiar_destinatarios(item, c.excluir, c.dominio)
            item.Subject = c.asunto
            item.HTMLBody = insertar_en_cuerpo(str(item.HTMLBody or ""), c.html)
        else:
            item = app.CreateItem(0)
            item.Subject = c.asunto
            item.To = "; ".join(c.para)
            if c.cc:
                item.CC = "; ".join(c.cc)
            item.HTMLBody = insertar_en_cuerpo(str(item.HTMLBody or ""), c.html) if c.firma_outlook else c.html

        for ruta in c.adjuntos:
            item.Attachments.Add(str(ruta))
        if c.logo is not None:
            adjunto = item.Attachments.Add(str(c.logo))
            adjunto.PropertyAccessor.SetProperty(_PR_ATTACH_CONTENT_ID, "logo_firma")
            adjunto.PropertyAccessor.SetProperty(_PR_ATTACHMENT_HIDDEN, True)
        item.Recipients.ResolveAll()
        return item

    @staticmethod
    def _limpiar_destinatarios(item: Any, excluir: List[str], dominio: str) -> None:
        """Como v1: de la respuesta se quitan la jefatura excluida y las direcciones externas."""
        quitar_exactos = {e.strip().lower() for e in excluir}
        sufijo = "@" + dominio.strip().lower().lstrip("@") if dominio else ""
        quitar = []
        for i in range(1, item.Recipients.Count + 1):
            direccion = _smtp(item.Recipients.Item(i))
            if direccion in quitar_exactos or (sufijo and "@" in direccion and not direccion.endswith(sufijo)):
                quitar.append(i)
        for i in reversed(quitar):
            item.Recipients.Remove(i)

    @staticmethod
    def _sin_resolver(item: Any) -> List[str]:
        pendientes = []
        for i in range(1, item.Recipients.Count + 1):
            r = item.Recipients.Item(i)
            if not r.Resolved:
                pendientes.append(str(r.Name))
        return pendientes

    # ---- anulación -----------------------------------------------------
    def anular(self, correos: List[tuple]) -> int:
        """Borra de la Bandeja de salida lo que aún espera su hora de envío (entrega diferida)."""
        buscados = {(sin_prefijos(a).upper(), p.strip().lower()) for a, p in correos}
        salida = self._mapi().GetDefaultFolder(4)         # olFolderOutbox
        ahora = datetime.now()
        borrados = 0
        for i in range(salida.Items.Count, 0, -1):
            try:
                item = salida.Items.Item(i)
                espera = _a_datetime(item.DeferredDeliveryTime)
                if espera is None or espera <= ahora or espera.year < 2000:
                    continue
                if (sin_prefijos(str(item.Subject or "")).upper(), str(item.To or "").strip().lower()) in buscados:
                    item.Delete()
                    borrados += 1
            except Exception as exc:
                log.debug("Elemento de salida omitido: %s", exc)
        return borrados

    # ---- verificación ------------------------------------------------
    def verificar(self, id_outlook: str) -> dict:
        try:
            item = self._mapi().GetItemFromID(id_outlook)
        except Exception:
            return {"existe": False}
        return {
            "existe": True,
            "asunto": str(item.Subject or ""),
            "adjuntos": int(item.Attachments.Count),
            "destinatarios": int(item.Recipients.Count),
            "resueltos": all(item.Recipients.Item(i).Resolved for i in range(1, item.Recipients.Count + 1)),
        }
