"""Valores propios de la institución que NO viajan en el repositorio.

El código trae valores genéricos (jefatura, copia fija, carpeta de SharePoint…). Cada despliegue puede completar los
suyos con un archivo `data/institucional.json` junto al programa: el instalador lo copia a `{app}\\data` si existe
al compilar, y el repositorio lo ignora (`data/` está en .gitignore). Claves admitidas: cualquier campo de
`Configuracion` (por_encargo_nombre, por_encargo_cargo, correos_excluidos, copia_fija, dominio_interno…) y
`raiz_sugerida` (carpeta de las entregas en la red).

Variables de entorno: `AGENTE_CORREOS_INSTITUCIONAL` apunta a otro archivo; `AGENTE_CORREOS_SIN_INSTITUCIONAL=1` lo
ignora (las pruebas lo usan para no depender de datos locales).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .entorno import carpeta_base, carpeta_datos_usuario


def _cargar() -> Dict[str, Any]:
    if os.environ.get("AGENTE_CORREOS_SIN_INSTITUCIONAL"):
        return {}
    candidatas: List[Path] = []
    if os.environ.get("AGENTE_CORREOS_INSTITUCIONAL"):
        candidatas.append(Path(os.environ["AGENTE_CORREOS_INSTITUCIONAL"]))
    candidatas.append(carpeta_base() / "data" / "institucional.json")
    for ruta in candidatas:
        try:
            if ruta.is_file():
                datos = json.loads(ruta.read_text(encoding="utf-8"))
                return dict(datos) if isinstance(datos, dict) else {}
        except (OSError, ValueError):
            continue
    return {}


_VALORES = _cargar()


def valor(clave: str, defecto: Any) -> Any:
    encontrado = _VALORES.get(clave)
    return defecto if encontrado in (None, "") else encontrado


def lista(clave: str, defecto: Iterable[str]) -> List[str]:
    encontrado = _VALORES.get(clave)
    return list(encontrado) if isinstance(encontrado, list) and encontrado else list(defecto)


def raiz_sugerida() -> str:
    """Carpeta donde se buscan las entregas si la persona no eligió otra."""
    return str(valor("raiz_sugerida", carpeta_datos_usuario() / "ENTREGA DE FONDOS"))
