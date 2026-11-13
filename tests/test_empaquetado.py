"""Lo que el .exe necesita y PyInstaller no detecta solo."""

from pathlib import Path

SPEC = Path(__file__).resolve().parents[1] / "installer" / "AgenteCorreosBN.spec"


def test_el_paquete_incluye_win32timezone():
    # pywin32 lo importa al leer fechas de Outlook; sin él, en el .exe no se puede enviar ni buscar el hilo
    assert "'win32timezone'" in SPEC.read_text(encoding="utf-8")
