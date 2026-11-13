"""Explora la carpeta de SharePoint de la entrega de fondos. SOLO LEE: no abre Excel ni cambia nada.

Para qué sirve: ver cómo está organizada la carpeta (campañas, copias, respaldos), qué tan rápido
responde y qué forma tiene el respaldo que dejó v1, antes de diseñar el uso de SharePoint en v2.

Uso (desde la carpeta v2):
    python tools/explorar_sharepoint.py
    python tools/explorar_sharepoint.py "RUTA\\DE\\LA\\CARPETA" --profundidad 4
    python tools/explorar_sharepoint.py --probar-escritura        (opcional, ver abajo)

Sin ruta, toma la carpeta del cronograma guardado en etv_config.json.

Qué guarda: nombres de carpetas y archivos, tamaños, fechas y tiempos de respuesta. NO guarda
contenido de archivos ni correos: de los metadata.json solo anota los nombres de sus campos.
Revise el archivo de salida antes de compartirlo.

--probar-escritura crea, en la carpeta raíz, un archivo temporal de 1 línea, lo renombra, lo lee y
lo borra, para medir si el registro de avisos podrá escribirse ahí. Es lo único que escribe.
"""

import argparse
import json
import os
import re
import statistics
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

MAX_ENTRADAS = 60
PATRON_CAMPANA = re.compile(r"\b(EF|MA|MJ|JA|SO|ND)\b.*\b20\d{2}\b", re.IGNORECASE)


def ruta_desde_config():
    for base in (Path.cwd(), Path.cwd().parent, Path(__file__).resolve().parents[1],
                 Path(__file__).resolve().parents[2]):
        cfg = base / "etv_config.json"
        if cfg.is_file():
            try:
                ruta = json.loads(cfg.read_text(encoding="utf-8")).get("cronograma_path", "")
            except (OSError, ValueError):
                ruta = ""
            if ruta:
                return os.path.dirname(ruta)
    return ""


def tamano(n):
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024 or u == "GB":
            return f"{n:.0f} {u}" if u == "B" else f"{n:.1f} {u}"
        n /= 1024


class Explorador:
    def __init__(self, salida, profundidad):
        self.salida = salida
        self.profundidad = profundidad
        self.tiempos = []          # (segundos, ruta) de cada listado
        self.carpetas = 0
        self.archivos = 0
        self.extensiones = Counter()
        self.bloqueos = []         # '~$archivo.xlsx': alguien lo tiene abierto
        self.errores = []
        self.respaldos = []        # carpetas BACKUP_CORREOS encontradas
        self.metadata = []

    def linea(self, texto=""):
        print(texto)
        self.salida.write(texto + "\n")

    def listar(self, ruta):
        t0 = time.perf_counter()
        try:
            with os.scandir(ruta) as it:
                entradas = sorted(it, key=lambda e: (not e.is_dir(), e.name.lower()))
                datos = [(e.name, e.is_dir(), *self._stat(e)) for e in entradas]
        except OSError as exc:
            self.errores.append(f"{ruta}: {exc}")
            return []
        self.tiempos.append((time.perf_counter() - t0, ruta))
        return datos

    @staticmethod
    def _stat(e):
        try:
            st = e.stat()
            return st.st_size, datetime.fromtimestamp(st.st_mtime)
        except OSError:
            return 0, None

    def recorrer(self, ruta, nivel=0):
        datos = self.listar(ruta)
        sangria = "  " * nivel
        mostrados = 0
        for nombre, es_dir, tam, fecha in datos:
            if es_dir:
                self.carpetas += 1
            else:
                self.archivos += 1
                self.extensiones[Path(nombre).suffix.lower() or "(sin extensión)"] += 1
                if nombre.startswith("~$"):
                    self.bloqueos.append(os.path.join(ruta, nombre))
            if mostrados < MAX_ENTRADAS:
                mostrados += 1
                marca = "[carpeta]" if es_dir else tamano(tam)
                cuando = fecha.strftime("%d/%m/%Y %H:%M") if fecha else "?"
                self.linea(f"{sangria}{'+' if es_dir else '-'} {nombre}   ({marca} · {cuando})")
        if len(datos) > MAX_ENTRADAS:
            resto = Counter(Path(n).suffix.lower() or "(carpeta/sin ext.)" for n, *_ in datos[MAX_ENTRADAS:])
            self.linea(f"{sangria}  … y {len(datos) - MAX_ENTRADAS} más: {dict(resto)}")

        for nombre, es_dir, _, _ in datos:
            if not es_dir:
                continue
            hija = os.path.join(ruta, nombre)
            if nombre.upper().startswith("BACKUP_CORREOS"):
                self.respaldos.append(hija)
            if nivel + 1 < self.profundidad:
                self.recorrer(hija, nivel + 1)

    # ------------------------------------------------------------------
    def describir_respaldo(self, ruta):
        """Estructura del respaldo: sin leer el contenido, solo la forma de los metadata.json."""
        self.linea(f"\n--- Respaldo: {ruta}")
        niveles = self.listar(ruta)
        self.linea(f"Contiene: {[n for n, d, *_ in niveles][:12]}")
        encontrados = 0
        for dirpath, _, files in os.walk(ruta):
            if "metadata.json" in files and encontrados < 2:
                encontrados += 1
                destino = os.path.join(dirpath, "metadata.json")
                try:
                    datos = json.loads(Path(destino).read_text(encoding="utf-8"))
                    forma = {k: type(v).__name__ for k, v in datos.items()}
                except (OSError, ValueError) as exc:
                    forma = f"ilegible: {exc}"
                self.linea(f"Ejemplo de metadata.json en …{os.sep}{os.path.relpath(dirpath, ruta)}")
                self.linea(f"   campos: {forma}")
                self.linea(f"   archivos de esa carpeta: {sorted(files)}")
        total = sum(1 for _, _, f in os.walk(ruta) if "metadata.json" in f)
        self.linea(f"Carpetas de agencia con metadata.json: {total}")

    def probar_escritura(self, raiz):
        self.linea("\n--- Prueba de escritura (archivo temporal que se borra)")
        base = os.path.join(raiz, f".prueba_agente_correos_{os.getpid()}")
        resultados = {}
        try:
            t0 = time.perf_counter()
            with open(base + ".tmp", "w", encoding="utf-8") as f:
                f.write("prueba\n")
            resultados["crear"] = time.perf_counter() - t0
            t0 = time.perf_counter()
            os.replace(base + ".tmp", base + ".json")
            resultados["renombrar (os.replace)"] = time.perf_counter() - t0
            t0 = time.perf_counter()
            with open(base + ".json", encoding="utf-8") as f:
                f.read()
            resultados["leer"] = time.perf_counter() - t0
            t0 = time.perf_counter()
            os.remove(base + ".json")
            resultados["borrar"] = time.perf_counter() - t0
            for k, v in resultados.items():
                self.linea(f"   {k:26} OK · {v * 1000:.0f} ms")
        except OSError as exc:
            self.linea(f"   FALLÓ: {exc}")
            for extra in (base + ".tmp", base + ".json"):
                try:
                    os.remove(extra)
                except OSError:
                    pass

    def resumen(self):
        self.linea("\n=== RESUMEN")
        self.linea(f"Carpetas: {self.carpetas} · Archivos: {self.archivos}")
        self.linea(f"Tipos de archivo: {dict(self.extensiones.most_common(10))}")
        if self.tiempos:
            seg = [t for t, _ in self.tiempos]
            lento = max(self.tiempos)
            self.linea(f"Listados: {len(seg)} · mediana {statistics.median(seg) * 1000:.0f} ms · "
                       f"máximo {lento[0] * 1000:.0f} ms ({lento[1]})")
        self.linea(f"Archivos abiertos por alguien (~$): {len(self.bloqueos)}"
                   + ("".join(f"\n   {b}" for b in self.bloqueos[:5]) if self.bloqueos else ""))
        if self.errores:
            self.linea(f"Errores de lectura: {len(self.errores)}")
            for e in self.errores[:5]:
                self.linea(f"   {e}")


def main():
    ap = argparse.ArgumentParser(description="Explora la carpeta de SharePoint (solo lectura).")
    ap.add_argument("ruta", nargs="?", default="")
    ap.add_argument("--profundidad", type=int, default=3)
    ap.add_argument("--salida", default="")
    ap.add_argument("--probar-escritura", action="store_true")
    a = ap.parse_args()

    raiz = a.ruta or ruta_desde_config()
    if not raiz:
        print("No encontré la ruta. Indíquela: python tools/explorar_sharepoint.py \"RUTA\"")
        return 2
    if not os.path.isdir(raiz):
        print(f"La ruta no es accesible: {raiz}")
        return 2

    nombre_salida = a.salida or f"exploracion_sharepoint_{datetime.now():%Y%m%d_%H%M}.txt"
    with open(nombre_salida, "w", encoding="utf-8") as f:
        ex = Explorador(f, a.profundidad)
        ex.linea(f"Exploración de: {raiz}")
        ex.linea(f"Fecha: {datetime.now():%d/%m/%Y %H:%M} · profundidad {a.profundidad}\n")
        ex.recorrer(raiz)
        for respaldo in ex.respaldos[:2]:
            ex.describir_respaldo(respaldo)
        if a.probar_escritura:
            ex.probar_escritura(raiz)
        ex.resumen()
    print(f"\nGuardado en: {os.path.abspath(nombre_salida)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
