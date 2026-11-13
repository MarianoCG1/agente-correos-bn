"""Diálogos de archivo del sistema, a través de la ventana de pywebview."""

from __future__ import annotations

from typing import Optional


class Dialogos:
    def __init__(self, ventana):
        self._ventana = ventana

    def abrir_archivo(self, carpeta: str = "") -> Optional[str]:
        import webview
        r = self._ventana.create_file_dialog(
            webview.FileDialog.OPEN, directory=carpeta or "", allow_multiple=False,
            file_types=("Excel o lista de agencias (*.xlsx;*.xlsm;*.json)", "Todos los archivos (*.*)"))
        return r[0] if r else None

    def elegir_carpeta(self, carpeta: str = "") -> Optional[str]:
        import webview
        r = self._ventana.create_file_dialog(webview.FileDialog.FOLDER, directory=carpeta or "")
        return r[0] if r else None

    def guardar_como(self, nombre: str, carpeta: str = "", tipos: tuple = ("Excel (*.xlsx)",)) -> Optional[str]:
        import webview
        r = self._ventana.create_file_dialog(
            webview.FileDialog.SAVE, directory=carpeta or "", save_filename=nombre,
            file_types=tipos)
        if not r:
            return None
        return r if isinstance(r, str) else r[0]
