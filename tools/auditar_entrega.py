"""Audita una entrega armada a mano contra su cronograma original. No modifica ningún archivo.

Uso (desde la carpeta v2):
    python tools/auditar_entrega.py "CRONOGRAMA ETV JA 2026 difusion.xlsx" "ENTREGA DE FONDOS ETV JA 2026 difusion.xlsx"

Muestra: qué puntos se quitaron, qué fechas se movieron, cualquier otro cambio, y si la
entrega manual trae fórmulas rotas (#REF!). Luego genera la entrega con el programa en una
carpeta temporal y la compara celda por celda con la manual.
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agente_correos.datos.auditoria_entrega import comparar_archivos, inferir_cambios   # noqa: E402
from agente_correos.datos.generador_entrega import GeneradorEntrega                      # noqa: E402


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    original, manual = Path(argv[0]), Path(argv[1])

    inf = inferir_cambios(original, manual)
    print(f"Puntos quitados          : {len(inf.cambios.suspendidos)}")
    for s in inf.cambios.suspendidos:
        print(f"   {s.clave}")
    print(f"Fechas / horas movidas   : {len(inf.cambios.reprogramaciones)}")
    for r in inf.cambios.reprogramaciones:
        print(f"   {r.clave} · {r.campo} → {r.valor}")
    print(f"Otros cambios de valores : {len(inf.otras_diferencias)}")
    for d in inf.otras_diferencias[:15]:
        print(f"   {d}")
    print(f"Puntos solo en la entrega: {len(inf.solo_en_entrega)}")

    with tempfile.TemporaryDirectory() as tmp:
        generado = Path(tmp) / "entrega_generada.xlsx"
        resumen = GeneradorEntrega().generar(original, generado, inf.cambios, usuario="auditoria")
        valores, formulas = comparar_archivos(generado, manual)

    print(f"\nEntrega generada: {resumen.filas_entrega} filas "
          f"(original {resumen.filas_original}); columnas quitadas: {resumen.columnas_quitadas}")
    print(f"Celdas con valor distinto frente a la manual : {len(valores)}")
    for d in valores[:15]:
        print(f"   {d}")
    rotas = [f for f in formulas if "#REF!" in f]
    print(f"Fórmulas distintas                           : {len(formulas)} (con #REF! en la manual: {len(rotas)})")
    for d in formulas[:4]:
        print(f"   {d}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
