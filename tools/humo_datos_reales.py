"""Prueba de humo con los archivos reales: no envía nada ni toca Outlook.

Uso (desde la carpeta v2):
    python tools/humo_datos_reales.py "RUTA\\cronograma.xlsx" "RUTA\\agencias_correos.xlsx" [AAAA-MM-DD]

Sin argumentos usa ../data/ y la fecha del primer día con pagos. Muestra qué avisos saldrían,
cuáles quedan bloqueados y por qué. No imprime correos electrónicos.
"""

import sys
import tempfile
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from agente_correos.configuracion import Configuracion                         # noqa: E402
from agente_correos.datos.cronograma_loader import CronogramaLoader            # noqa: E402
from agente_correos.datos.directorio_agencias import DirectorioAgencias        # noqa: E402
from agente_correos.dominio.avisos import TipoAviso                            # noqa: E402
from agente_correos.historial.registro import RegistroEjecuciones              # noqa: E402
from agente_correos.reglas.fecha_objetivo import CalendarioHabil               # noqa: E402
from agente_correos.reglas.preflight import PreflightValidator, resumen        # noqa: E402


def main(argv):
    datos = RAIZ.parent / "data"
    ruta_crono = Path(argv[0]) if len(argv) > 0 else next(datos.glob("*ENTREGA*.xlsx"))
    ruta_ag = Path(argv[1]) if len(argv) > 1 else datos / "agencias_correos.xlsx"

    config = Configuracion()
    crono = CronogramaLoader().cargar(ruta_crono)
    directorio = DirectorioAgencias.cargar(ruta_ag)

    print(f"Cronograma : {Path(crono.ruta).name}")
    print(f"Campaña    : {crono.campana.nombre}")
    print(f"Hoja       : {crono.hoja} (encabezado en la fila {crono.fila_encabezado})")
    print(f"Filas      : {len(crono.df)}   Agencias: {len(crono.agencias())}   "
          f"Fechas de pago: {len(crono.fechas_objetivo())}")
    if crono.columnas_faltantes:
        print(f"FALTAN columnas: {crono.columnas_faltantes}")
    aviso = crono.aviso_de_coherencia()
    if aviso:
        print(f"ATENCIÓN   : {aviso}")

    sin_correo = [a for a in crono.agencias() if not directorio.existe(a)]
    print(f"Directorio : {len(directorio.agencias())} agencias; duplicadas: {directorio.duplicadas or 'ninguna'}")
    print(f"Agencias del cronograma que no figuran en el directorio: {sin_correo or 'ninguna'}")

    fecha = date.fromisoformat(argv[2]) if len(argv) > 2 else crono.fechas_objetivo()[0]
    hoy_hipotetico = CalendarioHabil(config.feriados_como_fechas()).fecha_de_aviso(fecha)
    print(f"\nRecordatorio para el {fecha:%d/%m/%Y} (se enviaría el {hoy_hipotetico:%d/%m/%Y})")

    with tempfile.TemporaryDirectory() as tmp:
        pf = PreflightValidator(crono, directorio, RegistroEjecuciones(tmp), config)
        resultados = pf.evaluar(TipoAviso.RECORDATORIO, fecha)
    for r in resultados:
        extra = f" | {r.motivo}" if r.motivo else ""
        avisos = f" | {'; '.join(r.advertencias)}" if r.advertencias else ""
        print(f"  {r.veredicto.value.upper():9} {r.agencia:22} {r.filas:3} fila(s){extra}{avisos}")
    print("\nResumen:", resumen(resultados))


if __name__ == "__main__":
    main(sys.argv[1:])
