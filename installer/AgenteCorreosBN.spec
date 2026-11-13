# -*- mode: python ; coding: utf-8 -*-
# PyInstaller: carpeta "dist\AgenteCorreosBN" con el .exe y todo lo que necesita.
# Se compila con installer\construir.ps1 desde un entorno virtual limpio (.venv_build).
import os

RAIZ = os.path.abspath(os.path.join(SPECPATH, '..'))            # raíz del repositorio
ICONO = os.path.abspath(os.path.join(RAIZ, 'assets', 'icono_programa.ico'))

a = Analysis(
    [os.path.join(RAIZ, 'main.py')],
    pathex=[RAIZ],
    binaries=[],
    datas=[(os.path.join(RAIZ, 'agente_correos', 'ui', 'web'), os.path.join('agente_correos', 'ui', 'web'))],
    # win32timezone: pywin32 lo importa al leer fechas de Outlook (SentOn, DeferredDeliveryTime…) y PyInstaller no lo
    # detecta; sin él, en el .exe fallan el envío y la búsqueda del hilo con «No module named win32timezone».
    hiddenimports=['win32com.client', 'pythoncom', 'pywintypes', 'win32timezone'],
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'scipy', 'IPython', 'pytest',
              'PyQt5', 'PyQt6', 'PySide2', 'PySide6'],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name='AgenteCorreosBN',
    console=False,                      # sin ventana negra; los fallos se muestran en un aviso y en el registro
    icon=ICONO if os.path.isfile(ICONO) else None,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='AgenteCorreosBN')
