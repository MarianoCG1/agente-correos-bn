"""Genera el archivo de entrega a partir del cronograma original.

Regla de oro: el original solo se lee. Todo cambio se hace en la copia, y cada copia deja una
bitácora con lo que se quitó o se movió y por qué (origen: el correo que lo pidió, etc.).
"""

from __future__ import annotations

import bisect
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple, Union

import pandas as pd
from openpyxl import load_workbook
from openpyxl.formatting.formatting import ConditionalFormattingList
from openpyxl.utils import get_column_letter, column_index_from_string

from .. import __version__
from .cronograma_loader import COL_FILA, COL_PUNTO, Cronograma, CronogramaError, CronogramaLoader

# Sub-columnas del grupo "Preparación y ENTREGA" que no van en la entrega (comparadas sin tildes)
COLUMNAS_A_QUITAR = ("categoria", "cod", "dias de anticipacion")
_GRUPO_PREPARACION = "preparacion"

# Un punto suspendido suele marcarse en rojo de la columna 4 a la 13 (verificado en JA 2026)
_COLUMNAS_MARCA = range(4, 14)
_UMBRAL_ROJOS = 6
_ROJO = "FFFF0000"

CAMPOS_REPROGRAMABLES = ("Fecha_Pago", "Hora_Pago", "Fecha_Entrega", "Hora_Entrega")


class EntregaError(Exception):
    """No se pudo generar la entrega; el mensaje explica por qué."""


def nombre_sugerido_entrega(nombre_original: str) -> str:
    """'CRONOGRAMA ETV JA 2026 difusion.xlsx' → 'ENTREGA DE FONDOS ETV JA 2026 difusion.xlsx'.

    Si el nombre no tiene el prefijo esperado, antepone 'ENTREGA DE FONDOS - ' para no confundirlo
    con el original.
    """
    base = Path(nombre_original).name
    nuevo, n = re.subn(r"^\s*(P65\s+)?CRONOGRAMA\s+ETV", "ENTREGA DE FONDOS ETV", base, flags=re.IGNORECASE)
    return nuevo if n else f"ENTREGA DE FONDOS - {base}"


# ----------------------------------------------------------------------
# Cambios y resumen
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class Suspension:
    clave: str                  # ClavePunto: 'cod. pueblo|cod. punto de pago'
    origen: str = ""            # p. ej. 'correo de Operaciones del 10/09'


@dataclass(frozen=True)
class Reprogramacion:
    clave: str
    campo: str                  # uno de CAMPOS_REPROGRAMABLES
    valor: Union[date, datetime, time]
    origen: str = ""


@dataclass
class CambiosEntrega:
    suspendidos: List[Suspension] = field(default_factory=list)
    reprogramaciones: List[Reprogramacion] = field(default_factory=list)

    def a_dict(self) -> dict:
        return {
            "suspendidos": [{"clave": s.clave, "origen": s.origen} for s in self.suspendidos],
            "reprogramaciones": [
                {"clave": r.clave, "campo": r.campo, "valor": _valor_a_texto(r.valor), "origen": r.origen}
                for r in self.reprogramaciones],
        }

    @classmethod
    def desde_dict(cls, d: dict) -> "CambiosEntrega":
        return cls(
            suspendidos=[Suspension(x["clave"], x.get("origen", "")) for x in d.get("suspendidos", [])],
            reprogramaciones=[Reprogramacion(x["clave"], x["campo"], _texto_a_valor(x["valor"]),
                                             x.get("origen", "")) for x in d.get("reprogramaciones", [])],
        )

    @classmethod
    def desde_bitacora(cls, ruta: Path) -> "CambiosEntrega":
        return cls.desde_dict(json.loads(Path(ruta).read_text(encoding="utf-8"))["cambios"])


@dataclass
class ResumenEntrega:
    destino: str
    filas_original: int
    filas_entrega: int
    importe_p65_original: float
    importe_p65_entrega: float
    usuarios_p65_original: int
    usuarios_p65_entrega: int
    columnas_quitadas: List[str]
    formulas_convertidas_a_valor: int
    bitacora: str = ""

    @property
    def filas_quitadas(self) -> int:
        return self.filas_original - self.filas_entrega


def _valor_a_texto(v) -> str:
    if isinstance(v, datetime):
        return "datetime:" + v.isoformat()
    if isinstance(v, date):
        return "date:" + v.isoformat()
    if isinstance(v, time):
        return "time:" + v.isoformat()
    return str(v)


def _texto_a_valor(t: str):
    tipo, _, resto = str(t).partition(":")
    if tipo == "datetime":
        return datetime.fromisoformat(resto)
    if tipo == "date":
        return date.fromisoformat(resto)
    if tipo == "time":
        return time.fromisoformat(resto)
    return t


# ----------------------------------------------------------------------
# Utilidades de texto y de referencias de Excel
# ----------------------------------------------------------------------
def _etiqueta(valor: object) -> str:
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto).strip().lower()


class _Mapa:
    """Correspondencia entre posiciones antiguas y nuevas al quitar filas o columnas."""

    def __init__(self, total: int, quitadas: Iterable[int]):
        quitadas = set(quitadas)
        self.vivas: List[int] = [i for i in range(1, total + 1) if i not in quitadas]
        self.total = total
        self._nuevo = {viejo: pos + 1 for pos, viejo in enumerate(self.vivas)}

    def exacto(self, viejo: int) -> Optional[int]:
        if viejo > self.total:
            return viejo - (self.total - len(self.vivas))        # fuera de la hoja: se desplaza igual
        return self._nuevo.get(viejo)

    def inicio(self, viejo: int) -> Optional[int]:
        """Primera posición viva a partir de `viejo` (para el borde inicial de un rango)."""
        if viejo > self.total:
            return self.exacto(viejo)
        i = bisect.bisect_left(self.vivas, viejo)
        return i + 1 if i < len(self.vivas) else None

    def fin(self, viejo: int) -> Optional[int]:
        """Última posición viva hasta `viejo` (para el borde final de un rango)."""
        if viejo > self.total:
            return self.exacto(viejo)
        i = bisect.bisect_right(self.vivas, viejo)
        return i if i > 0 else None


_REF = re.compile(
    r"(?<![A-Za-z0-9_.!'])(\$?)([A-Z]{1,3})(\$?)(\d+)(?::(\$?)([A-Z]{1,3})(\$?)(\d+))?(?![A-Za-z0-9_(])")


def remapear_formula(formula: str, cols: _Mapa, filas: _Mapa) -> Optional[str]:
    """Reescribe las referencias de una fórmula tras quitar filas y columnas.

    Devuelve None si alguna referencia apunta a algo que ya no existe (en ese caso quien llama
    conserva el valor calculado en lugar de dejar un #REF!).
    """
    invalida = False

    def reemplazo(m: re.Match) -> str:
        nonlocal invalida
        da, c1, dr, f1, da2, c2, dr2, f2 = m.groups()
        col1, fila1 = column_index_from_string(c1), int(f1)
        if c2 is None:                                    # referencia simple
            nc, nf = cols.exacto(col1), filas.exacto(fila1)
            if nc is None or nf is None:
                invalida = True
                return m.group(0)
            return f"{da}{get_column_letter(nc)}{dr}{nf}"
        col2, fila2 = column_index_from_string(c2), int(f2)   # rango
        nc1, nc2 = cols.inicio(col1), cols.fin(col2)
        nf1, nf2 = filas.inicio(fila1), filas.fin(fila2)
        if None in (nc1, nc2, nf1, nf2) or nc1 > nc2 or nf1 > nf2:
            invalida = True
            return m.group(0)
        return (f"{da}{get_column_letter(nc1)}{dr}{nf1}:"
                f"{da2}{get_column_letter(nc2)}{dr2}{nf2}")

    nueva = _REF.sub(reemplazo, formula)
    return None if invalida else nueva


# ----------------------------------------------------------------------
# Detección en el original
# ----------------------------------------------------------------------
def _columnas_a_quitar(ws, fila_grupo: int, fila_sub: int) -> List[int]:
    """Columnas del grupo 'Preparación y ENTREGA' cuyo rótulo está en COLUMNAS_A_QUITAR."""
    ancho = ws.max_column
    inicio = next((c for c in range(1, ancho + 1)
                   if _etiqueta(ws.cell(fila_grupo, c).value).startswith(_GRUPO_PREPARACION)), None)
    if inicio is None:
        raise EntregaError("No se encontró el grupo 'Preparación y ENTREGA DE FONDOS' en el original.")
    fin = next((c for c in range(inicio + 1, ancho + 1) if ws.cell(fila_grupo, c).value not in (None, "")),
               ancho + 1)
    quitar = []
    for c in range(inicio, fin):
        rotulo = _etiqueta(ws.cell(fila_sub, c).value)
        if any(rotulo == q or (q.startswith("dias de") and rotulo.startswith("dias de anti"))
               for q in COLUMNAS_A_QUITAR):
            quitar.append(c)
    return quitar


def sugerir_suspendidos(original: str | Path, cronograma: Optional[Cronograma] = None) -> List[str]:
    """Puntos que en el original llevan la marca roja habitual de suspendido (solo una sugerencia)."""
    cronograma = cronograma or CronogramaLoader().cargar(original)
    ws = load_workbook(str(original), read_only=False).active
    sugeridos = []
    for _, fila in cronograma.df.iterrows():
        r = int(fila[COL_FILA])
        rojas = 0
        for c in _COLUMNAS_MARCA:
            relleno = ws.cell(r, c).fill
            if relleno and relleno.fill_type and relleno.fgColor and relleno.fgColor.rgb == _ROJO:
                rojas += 1
        if rojas >= _UMBRAL_ROJOS and COL_PUNTO in cronograma.df.columns:
            sugeridos.append(fila[COL_PUNTO])
    return sugeridos


# ----------------------------------------------------------------------
# Generador
# ----------------------------------------------------------------------
class GeneradorEntrega:
    def __init__(self, loader: Optional[CronogramaLoader] = None):
        self._loader = loader or CronogramaLoader()

    def generar(self, original: str | Path, destino: str | Path, cambios: CambiosEntrega,
                usuario: str = "", sobrescribir: bool = False) -> ResumenEntrega:
        original, destino = Path(original), Path(destino)
        self._validar_rutas(original, destino, sobrescribir)

        crono = self._loader.cargar(original)
        if COL_PUNTO not in crono.df.columns:
            raise EntregaError("El original no tiene las columnas de código de pueblo y punto de pago.")
        por_clave = self._indexar(crono)

        filas_quitar = self._filas_a_quitar(cambios, por_clave)
        reprog = self._reprogramaciones(cambios, por_clave, crono)

        wb = load_workbook(str(original))
        wbv = load_workbook(str(original), data_only=True)
        ws = wb[crono.hoja]
        wsv = wbv[crono.hoja]

        fila_sub = crono.fila_encabezado + 1            # fila (base 1) con los rótulos de columna
        fila_grupo = fila_sub - 1
        if fila_grupo < 1:
            raise EntregaError("El original no tiene la fila de grupos sobre los encabezados.")
        cols_quitar = _columnas_a_quitar(ws, fila_grupo, fila_sub)
        rotulos_quitados = [str(ws.cell(fila_sub, c).value) for c in cols_quitar]

        max_fila, max_col = ws.max_row, ws.max_column
        mapa_f, mapa_c = _Mapa(max_fila, filas_quitar), _Mapa(max_col, cols_quitar)

        # 1) Formulas: se calculan con las posiciones antiguas, antes de mover nada.
        formulas, a_valor = {}, 0
        for fila in ws.iter_rows():
            for celda in fila:
                v = celda.value
                if not (isinstance(v, str) and v.startswith("=")):
                    continue
                if celda.row in filas_quitar or celda.column in cols_quitar:
                    continue
                nueva = remapear_formula(v, mapa_c, mapa_f)
                destino_celda = (mapa_f.exacto(celda.row), mapa_c.exacto(celda.column))
                if nueva is None:
                    nueva = wsv.cell(celda.row, celda.column).value        # valor calculado, sin #REF!
                    a_valor += 1
                formulas[destino_celda] = nueva

        # 2) Estructura que openpyxl no ajusta sola.
        alturas = {r: ws.row_dimensions[r].height for r in mapa_f.vivas}
        anchos, ocultas = self._dimensiones_columnas(ws, max_col)
        combinadas = [str(r) for r in ws.merged_cells.ranges]
        for rango in combinadas:
            ws.unmerge_cells(rango)
        reglas = [(str(cf.sqref), list(reglas)) for cf, reglas in ws.conditional_formatting._cf_rules.items()]
        filtro = ws.auto_filter.ref

        # Los rótulos de grupo que caen en una columna que se quita pasan a la siguiente
        for r in range(1, fila_sub + 1):
            for c in cols_quitar:
                texto = ws.cell(r, c).value
                if texto in (None, ""):
                    continue
                siguiente = next((x for x in range(c + 1, max_col + 1) if x not in cols_quitar), None)
                if siguiente and ws.cell(r, siguiente).value in (None, ""):
                    ws.cell(r, siguiente).value = texto
                    ws.cell(r, siguiente)._style = ws.cell(r, c)._style

        # 3) Reprogramaciones (sobre posiciones antiguas, antes de mover).
        for rp in reprog:
            fila_old, col_old = rp[0], rp[1]
            ws.cell(fila_old, col_old).value = rp[2]

        # 4) Quitar columnas y filas, de atrás hacia adelante.
        for c in sorted(cols_quitar, reverse=True):
            ws.delete_cols(c)
        for r in sorted(filas_quitar, reverse=True):
            ws.delete_rows(r)

        # 5) Reponer fórmulas y estructura con las posiciones nuevas.
        for (r, c), valor in formulas.items():
            ws.cell(r, c).value = valor
        for r_old, alto in alturas.items():
            ws.row_dimensions[mapa_f.exacto(r_old)].height = alto
        self._reponer_columnas(ws, anchos, ocultas, mapa_c)
        self._reponer_combinadas(ws, combinadas, mapa_c, mapa_f)
        self._reponer_formato_condicional(ws, reglas, mapa_c, mapa_f)
        if filtro:
            ws.auto_filter.ref = self._rango(filtro, mapa_c, mapa_f) or filtro

        destino.parent.mkdir(parents=True, exist_ok=True)
        if destino.exists() and not sobrescribir:
            raise EntregaError(f"Ya existe el archivo de destino: {destino.name}")
        wb.save(str(destino))

        resumen = self._verificar(crono, destino, filas_quitar, rotulos_quitados, a_valor)
        resumen.bitacora = str(self._escribir_bitacora(original, destino, cambios, resumen, usuario))
        return resumen

    # ------------------------------------------------------------------
    @staticmethod
    def _validar_rutas(original: Path, destino: Path, sobrescribir: bool) -> None:
        if not original.is_file():
            raise EntregaError(f"No existe el cronograma original: {original}")
        try:
            igual = destino.resolve() == original.resolve() or (
                destino.exists() and destino.samefile(original))
        except OSError:
            igual = False
        if igual:
            raise EntregaError("El destino no puede ser el archivo original: el original no se modifica.")
        if destino.exists() and not sobrescribir:
            raise EntregaError(f"Ya existe el archivo de destino: {destino.name}")

    @staticmethod
    def _indexar(crono: Cronograma) -> Dict[str, int]:
        claves = crono.df[COL_PUNTO]
        repetidas = sorted({k for k in claves[claves.duplicated()] if k != "|"})
        if repetidas:
            raise EntregaError("Hay puntos de pago repetidos en el original (código pueblo|punto): "
                               + ", ".join(repetidas[:5]))
        return {k: int(f) for k, f in zip(claves, crono.df[COL_FILA])}

    @staticmethod
    def _filas_a_quitar(cambios: CambiosEntrega, por_clave: Dict[str, int]) -> List[int]:
        desconocidas = [s.clave for s in cambios.suspendidos if s.clave not in por_clave]
        if desconocidas:
            raise EntregaError("Puntos suspendidos que no existen en el original: " + ", ".join(desconocidas))
        return sorted({por_clave[s.clave] for s in cambios.suspendidos})

    @staticmethod
    def _reprogramaciones(cambios: CambiosEntrega, por_clave: Dict[str, int],
                          crono: Cronograma) -> List[Tuple[int, int, object]]:
        salida = []
        suspendidos = {s.clave for s in cambios.suspendidos}
        for rp in cambios.reprogramaciones:
            if rp.clave not in por_clave:
                raise EntregaError(f"Reprogramación sobre un punto que no existe: {rp.clave}")
            if rp.campo not in CAMPOS_REPROGRAMABLES:
                raise EntregaError(f"Campo no reprogramable: {rp.campo}")
            col = crono.columna_excel(rp.campo)
            if col is None:
                raise EntregaError(f"El original no tiene la columna {rp.campo}.")
            if rp.clave in suspendidos:
                continue                                # un punto suspendido ya no existe en la entrega
            salida.append((por_clave[rp.clave], col, rp.valor))
        return salida

    @staticmethod
    def _dimensiones_columnas(ws, max_col: int) -> Tuple[Dict[int, float], Dict[int, bool]]:
        anchos, ocultas = {}, {}
        for dim in ws.column_dimensions.values():
            if dim.min is None or dim.max is None:
                continue
            for c in range(dim.min, min(dim.max, max_col) + 1):
                if dim.width is not None:
                    anchos[c] = dim.width
                ocultas[c] = bool(dim.hidden)
        return anchos, ocultas

    @staticmethod
    def _reponer_columnas(ws, anchos: Dict[int, float], ocultas: Dict[int, bool], mapa_c: _Mapa) -> None:
        for clave in list(ws.column_dimensions.keys()):
            del ws.column_dimensions[clave]
        for viejo, ancho in anchos.items():
            nuevo = mapa_c.exacto(viejo)
            if nuevo is None:
                continue
            dim = ws.column_dimensions[get_column_letter(nuevo)]
            dim.width = ancho
            dim.hidden = ocultas.get(viejo, False)

    @staticmethod
    def _rango(texto: str, mapa_c: _Mapa, mapa_f: _Mapa) -> Optional[str]:
        nuevo = remapear_formula(texto, mapa_c, mapa_f)
        return nuevo

    @staticmethod
    def _reponer_combinadas(ws, rangos: List[str], mapa_c: _Mapa, mapa_f: _Mapa) -> None:
        for rango in rangos:
            nuevo = remapear_formula(rango, mapa_c, mapa_f)
            if nuevo and ":" in nuevo and nuevo.split(":")[0] != nuevo.split(":")[1]:
                ws.merge_cells(nuevo)

    @staticmethod
    def _reponer_formato_condicional(ws, reglas, mapa_c: _Mapa, mapa_f: _Mapa) -> None:
        ws.conditional_formatting = ConditionalFormattingList()
        for sqref, lista in reglas:
            rangos = [r for r in (remapear_formula(p, mapa_c, mapa_f) for p in sqref.split()) if r]
            if not rangos:
                continue
            for regla in lista:
                if regla.formula:
                    regla.formula = [remapear_formula(f, mapa_c, mapa_f) or f for f in regla.formula]
                ws.conditional_formatting.add(" ".join(rangos), regla)

    def _verificar(self, original: Cronograma, destino: Path, filas_quitadas: List[int],
                   rotulos: List[str], formulas_a_valor: int) -> ResumenEntrega:
        """Relee lo generado y comprueba que cuadra con el original menos lo quitado."""
        try:
            nuevo = self._loader.cargar(destino)
        except CronogramaError as exc:
            destino.unlink(missing_ok=True)
            raise EntregaError(f"El archivo generado no se pudo leer: {exc}") from exc

        esperadas = len(original.df) - len(filas_quitadas)
        if len(nuevo.df) != esperadas:
            destino.unlink(missing_ok=True)
            raise EntregaError(f"La entrega tiene {len(nuevo.df)} filas y debía tener {esperadas}.")

        def totales(c: Cronograma) -> Tuple[float, int]:
            imp = float(pd.to_numeric(c.df.get("P65_Importe"), errors="coerce").fillna(0).sum())
            usu = int(pd.to_numeric(c.df.get("P65_Usuarios"), errors="coerce").fillna(0).sum())
            return imp, usu

        io, uo = totales(original)
        ie, ue = totales(nuevo)
        return ResumenEntrega(
            destino=str(destino), filas_original=len(original.df), filas_entrega=len(nuevo.df),
            importe_p65_original=io, importe_p65_entrega=ie,
            usuarios_p65_original=uo, usuarios_p65_entrega=ue,
            columnas_quitadas=rotulos, formulas_convertidas_a_valor=formulas_a_valor,
        )

    @staticmethod
    def _escribir_bitacora(original: Path, destino: Path, cambios: CambiosEntrega,
                           resumen: ResumenEntrega, usuario: str) -> Path:
        ruta = destino.with_suffix(".cambios.json")
        contenido = {
            "generado_en": datetime.now().isoformat(timespec="seconds"),
            "generado_por": usuario,
            "version_app": __version__,
            "original": original.name,
            "entrega": destino.name,
            "cambios": cambios.a_dict(),
            "resumen": {
                "filas_original": resumen.filas_original,
                "filas_entrega": resumen.filas_entrega,
                "importe_p65_original": resumen.importe_p65_original,
                "importe_p65_entrega": resumen.importe_p65_entrega,
                "usuarios_p65_original": resumen.usuarios_p65_original,
                "usuarios_p65_entrega": resumen.usuarios_p65_entrega,
                "columnas_quitadas": resumen.columnas_quitadas,
            },
        }
        ruta.write_text(json.dumps(contenido, ensure_ascii=False, indent=2), encoding="utf-8")
        return ruta
