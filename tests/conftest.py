"""Datos sintéticos: ningún dato real del banco entra al repositorio."""

import os

# Las pruebas no deben depender de data/institucional.json (valores del despliegue local)
os.environ.setdefault("AGENTE_CORREOS_SIN_INSTITUCIONAL", "1")

from datetime import date, datetime, time

import pytest
from openpyxl import Workbook

from agente_correos.configuracion import Configuracion
from agente_correos.datos.cronograma_loader import CronogramaLoader
from agente_correos.datos.directorio_agencias import DirectorioAgencias
from agente_correos.historial.registro import RegistroEjecuciones

NOMBRE_CRONOGRAMA = "ENTREGA DE FONDOS ETV JA 2026 difusion.xlsx"   # JA se paga en sep–oct

ENCABEZADO = ["N°", "Departamento", "Provincia", "Cod. Pueblo", "Distrito", "Cod. Pto. Pago",
              "Punto de Pago", "N° Usuarios", "Importe", "N° Usuarios", "Importe", "Fecha Propuesta",
              "Hora", "ETV", "Agencia", "FECHA", "Hora"]


def _fila(n, ag, pago, entrega, p65=(100, 50000.0), juntos=(None, None), etv="HERMES"):
    return [n, "CUSCO", "CUSCO", 664, "DISTRITO " + str(n), 85, "PUNTO " + str(n),
            p65[0], p65[1], juntos[0], juntos[1], pago, time(9, 0), etv, ag, entrega, time(8, 30)]


@pytest.fixture
def crono_path(tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.title = "CRONOGRAMA ETV"
    ws.append(["CRONOGRAMA DE ENTREGA DE FONDOS"] + [None] * 16)      # fila de título
    ws.append(ENCABEZADO)
    d = datetime
    ws.append(_fila(1, "AG. UNO", d(2026, 10, 14), d(2026, 10, 14), juntos=(30, 9000.0)))
    ws.append(_fila(2, "AG. UNO", d(2026, 10, 20), d(2026, 10, 19)))               # objetivo = 19/10
    ws.append(_fila(3, "AG. DOS", d(2026, 10, 14), d(2026, 10, 14), p65=(80, 0)))  # sin importe
    ws.append(_fila(4, "AG. TRES", d(2026, 10, 14), d(2026, 10, 14), etv="PROSEGUR"))
    ws.append(_fila(5, "AG. CUATRO", d(2026, 10, 14), d(2026, 10, 14)))            # no está en el directorio
    ws.append(_fila(6, "AG. CINCO", d(2026, 10, 14), d(2026, 10, 14)))             # correo externo
    ws.append(_fila(7, "AG. SEIS", d(2026, 10, 14), d(2026, 10, 14)))              # sin correo
    ws.append(_fila(8, "AG. SIETE", d(2026, 10, 14), d(2026, 10, 14)))             # correo mal escrito
    ws.append(_fila(9, None, None, None))                                           # fila vacía
    ruta = tmp_path / NOMBRE_CRONOGRAMA
    wb.save(ruta)
    return ruta


@pytest.fixture
def agencias_path(tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.append(["AGENCIAS", "JEFE DE PAGO", "ADMINISTRADOR"])
    ws.append(["AG. UNO", "jpago_uno@bn.com.pe", "admin_uno@bn.com.pe; otro_uno@bn.com.pe"])
    ws.append(["Ag.  Dos", "JPAGO_DOS@BN.COM.PE", None])
    ws.append(["AG. TRES", "jpago_tres@bn.com.pe", "admin_tres@bn.com.pe"])
    ws.append(["AG. CINCO", "alguien@gmail.com", "admin_cinco@bn.com.pe"])
    ws.append(["AG. SEIS", None, "admin_seis@bn.com.pe"])
    ws.append(["AG. SIETE", "esto-no-es-correo", None])
    ruta = tmp_path / "agencias_correos.xlsx"
    wb.save(ruta)
    return ruta


@pytest.fixture
def config():
    return Configuracion()


@pytest.fixture
def cronograma(crono_path):
    return CronogramaLoader().cargar(crono_path, hoy=date(2026, 10, 13))


@pytest.fixture
def directorio(agencias_path):
    return DirectorioAgencias.cargar(agencias_path)


@pytest.fixture
def registro(tmp_path):
    return RegistroEjecuciones(tmp_path / "registro", usuario="tester")
