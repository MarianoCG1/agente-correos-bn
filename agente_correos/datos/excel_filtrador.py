"""Excel de una sola agencia, con los estilos del archivo de entrega vigente."""

from __future__ import annotations

from copy import copy
from pathlib import Path
from typing import List

from openpyxl import Workbook, load_workbook
from openpyxl.utils import get_column_letter

from .cronograma_loader import COL_FILA, Cronograma
from .generador_entrega import _Mapa, remapear_formula


class FiltroError(Exception):
    """No se pudo armar el Excel de la agencia."""


class ExcelFiltrador:
    """Carga el archivo una vez y genera el Excel de cada agencia a partir de él."""

    def __init__(self, cronograma: Cronograma):
        self._c = cronograma
        self._wb = load_workbook(cronograma.ruta)
        self._wbv = load_workbook(cronograma.ruta, data_only=True)
        self._ws = self._wb[cronograma.hoja]
        self._wsv = self._wbv[cronograma.hoja]

    def generar(self, agencia: str, destino: str | Path) -> int:
        """Escribe el Excel de la agencia en `destino`. Devuelve cuántas filas de datos tiene."""
        filas_datos: List[int] = sorted(int(f) for f in self._c.filas(agencia)[COL_FILA])
        if not filas_datos:
            raise FiltroError(f"La agencia {agencia} no tiene filas en {Path(self._c.ruta).name}.")

        ws, wsv = self._ws, self._wsv
        fila_sub = self._c.fila_encabezado + 1
        conservar = list(range(1, fila_sub + 1)) + filas_datos
        mapa_f = _Mapa(ws.max_row, [r for r in range(1, ws.max_row + 1) if r not in set(conservar)])
        mapa_c = _Mapa(ws.max_column, [])

        wb = Workbook()
        salida = wb.active
        salida.title = self._c.hoja
        for nuevo, viejo in enumerate(conservar, start=1):
            for col in range(1, ws.max_column + 1):
                origen = ws.cell(viejo, col)
                destino_celda = salida.cell(nuevo, col)
                valor = origen.value
                if isinstance(valor, str) and valor.startswith("="):
                    reescrita = remapear_formula(valor, mapa_c, mapa_f)
                    valor = reescrita if reescrita else wsv.cell(viejo, col).value
                destino_celda.value = valor
                if origen.has_style:
                    destino_celda.font = copy(origen.font)
                    destino_celda.fill = copy(origen.fill)
                    destino_celda.border = copy(origen.border)
                    destino_celda.alignment = copy(origen.alignment)
                    destino_celda.number_format = origen.number_format
            alto = ws.row_dimensions[viejo].height
            if alto:
                salida.row_dimensions[nuevo].height = alto

        for rango in ws.merged_cells.ranges:
            if rango.max_row <= fila_sub:
                salida.merge_cells(str(rango))
        for col in range(1, ws.max_column + 1):
            letra = get_column_letter(col)
            ancho = ws.column_dimensions[letra].width
            if ancho:
                salida.column_dimensions[letra].width = ancho

        destino = Path(destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        wb.save(str(destino))
        return len(filas_datos)
