"""Convierte la lista de agencias de v1 (Excel) en el archivo agencias.json que usa v2.

Uso (desde la carpeta v2):
    py tools/cargar_agencias.py "RUTA\\agencias_correos.xlsx"
    py tools/cargar_agencias.py "RUTA\\agencias_correos.xlsx" --salida "RUTA\\_PROGRAMA\\agencias.json"

Sin --salida escribe `agencias.json` junto al Excel. Ese archivo se copia una sola vez a la carpeta
compartida (BACKUP_CORREOS\\_PROGRAMA) o a la carpeta data del programa: la aplicación lo toma sola.
Muestra cuántas agencias convirtió y cuáles se rechazaron y por qué; no imprime correos.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agente_correos.datos.repositorio_agencias import RepositorioAgencias   # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("excel")
    ap.add_argument("--salida", default="")
    ap.add_argument("--dominio", default="bn.com.pe")
    a = ap.parse_args()

    origen = Path(a.excel)
    if not origen.is_file():
        print("No se encontró el archivo indicado.")
        return 2
    salida = Path(a.salida) if a.salida else origen.with_name("agencias.json")
    if salida.exists():
        print(f"Ya existe {salida.name}: no se sobrescribe. Bórrelo o elija otra salida con --salida.")
        return 2

    repo = RepositorioAgencias(salida, dominio=a.dominio)
    r = repo.importar(origen)
    print(f"Convertidas: {len(r.agregadas)}")
    for nombre, motivo in r.rechazadas.items():
        print(f"  RECHAZADA {nombre}: {motivo}")
    print(f"Archivo: {salida}")
    return 0 if r.agregadas else 1


if __name__ == "__main__":
    sys.exit(main())
