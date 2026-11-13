"""Ordena los respaldos de v1 en la carpeta BACKUP_CORREOS, sin borrar nada.

Uso (desde la carpeta v2):
    py tools/ordenar_respaldos.py                       simula y muestra el plan (no cambia nada)
    py tools/ordenar_respaldos.py --aplicar             copia lo que falta
    py tools/ordenar_respaldos.py --raiz "RUTA\\ENTREGA DE FONDOS" --canonica "RUTA\\BACKUP_CORREOS"

Qué hace: busca respaldos de agencia fuera de BACKUP_CORREOS (las formas que v1 fue dejando) y los
COPIA a BACKUP_CORREOS/<año>/<campaña>/<AGENCIA>. Las carpetas originales quedan como están.
Lo que ya existe en BACKUP_CORREOS no se pisa: si el de origen es más reciente se avisa como conflicto.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agente_correos.correo.ordenar_respaldos import aplicar, planificar, resumen   # noqa: E402
from agente_correos.entorno import ruta_desde_url_sharepoint                        # noqa: E402

from agente_correos.institucional import raiz_sugerida                              # noqa: E402

RAIZ_SUGERIDA = raiz_sugerida()


def _raiz_de_config() -> str:
    for base in (Path.cwd(), Path.cwd().parent, Path(__file__).resolve().parents[1]):
        cfg = base / "etv_config.json"
        if cfg.is_file():
            try:
                ruta = json.loads(cfg.read_text(encoding="utf-8")).get("cronograma_path", "")
            except (OSError, ValueError):
                ruta = ""
            if ruta:
                return str(Path(ruta_desde_url_sharepoint(ruta)).parent)
    return RAIZ_SUGERIDA


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raiz", default="")
    ap.add_argument("--canonica", default="")
    ap.add_argument("--aplicar", action="store_true")
    ap.add_argument("--reemplazar-conflictos", action="store_true")
    a = ap.parse_args()

    raiz = Path(ruta_desde_url_sharepoint(a.raiz)) if a.raiz else Path(_raiz_de_config())
    canonica = Path(ruta_desde_url_sharepoint(a.canonica)) if a.canonica else raiz / "BACKUP_CORREOS"
    if not raiz.is_dir():
        print(f"No se puede abrir la carpeta: {raiz}")
        return 2

    print(f"Raíz     : {raiz}\nDestino  : {canonica}\n")
    plan = planificar(raiz, canonica)
    if not plan:
        print("No hay respaldos fuera de BACKUP_CORREOS: ya está todo ordenado.")
        return 0

    etiquetas = {"copiar": "COPIAR", "ya_ordenado": "YA ESTÁ", "conflicto": "REVISAR", "duplicado": "OMITIR"}
    actual = ""
    for m in plan:
        if m.campana != actual:
            actual = m.campana
            print(f"\n{actual}")
        print(f"  {etiquetas[m.accion]:8} {m.agencia:14} desde …{str(m.origen.parent.relative_to(raiz))}"
              + (f"  ({m.motivo})" if m.accion in ('conflicto', 'duplicado') else ""))

    r = resumen(plan)
    print(f"\nResumen: {r['copiar']} por copiar · {r['ya_ordenado']} ya ordenadas · "
          f"{r['conflicto']} por revisar · {r['duplicado']} duplicadas")

    if not a.aplicar:
        print("\nSolo simulación. Para copiar lo que falta use --aplicar.")
        return 0
    n = aplicar(plan, reemplazar_conflictos=a.reemplazar_conflictos)
    print(f"\nListo: {n} carpetas copiadas a {canonica}. No se borró nada.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
