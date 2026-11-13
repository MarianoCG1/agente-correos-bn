"""Perfil de quien opera la aplicación: de ahí sale su firma."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, fields
from pathlib import Path

DEPENDENCIA_BN = ("Sección Caja y Valores en Custodia | Sub Gerencia Caja y Valores | "
                  "Gerencia de Operaciones | BN")
AVISO_CONFIDENCIAL = ("Este correo y sus adjuntos son confidenciales. Si usted no es el destinatario, "
                      "elimine este mensaje y notifíquelo al remitente.")

MODOS_FIRMA = ("app", "outlook", "ninguna")


def normalizar_nombre(texto: str) -> str:
    """'PEREZ, Ana B.' → 'Ana B. Perez'; pasa a Título cada palabra que venga en MAYÚSCULAS."""
    limpio = re.sub(r"\s+", " ", (texto or "").strip())
    if "," in limpio:
        apellidos, _, nombres = limpio.partition(",")
        limpio = f"{nombres.strip()} {apellidos.strip()}".strip()
    return " ".join(p.title() if p.isupper() else p for p in limpio.split(" "))


def separar_cargo_y_nombre(texto: str) -> tuple:
    """'PRACTICANTE - ANA PEREZ' -> ('Practicante', 'Ana Perez'). Sin cargo: ('', nombre)."""
    limpio = re.sub(r"\s+", " ", (texto or "").strip())
    m = re.match(r"^([^-\u2013\d]{3,40}?)\s+[-\u2013]\s+(.+)$", limpio)
    if m and len(m.group(1).split()) <= 3:
        return normalizar_nombre(m.group(1)), normalizar_nombre(m.group(2))
    return "", normalizar_nombre(limpio)


@dataclass
class PerfilUsuario:
    nombre: str = ""
    cargo: str = ""                 # p. ej. 'Practicante'; vacío si solo va el nombre
    dependencia: str = DEPENDENCIA_BN
    telefono: str = "519-2000"
    anexo: str = ""
    direccion: str = "Oficina Principal del BN – San Borja"
    email: str = ""
    mostrar_email: bool = True
    aviso_confidencial: bool = False
    logo_path: str = ""
    modo_firma: str = "app"         # 'app' | 'outlook' | 'ninguna'

    @property
    def linea_titulo(self) -> str:
        """Primera línea de la firma: 'Cargo - Nombre', o solo el nombre."""
        return f"{self.cargo.strip()} - {self.nombre.strip()}" if self.cargo.strip() else self.nombre.strip()

    @property
    def completo(self) -> bool:
        return bool(self.nombre.strip())

    @classmethod
    def inicial(cls, nombre_detectado: str = "", email: str = "") -> "PerfilUsuario":
        """Perfil de primer uso, con lo que se pudo detectar del equipo o de Outlook."""
        cargo, nombre = separar_cargo_y_nombre(nombre_detectado)
        return cls(nombre=nombre, cargo=cargo, email=(email or "").strip().lower())

    # ------------------------------------------------------------------
    @classmethod
    def cargar(cls, ruta: Path) -> "PerfilUsuario":
        ruta = Path(ruta)
        if not ruta.exists():
            return cls()
        try:
            crudo = json.loads(ruta.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        conocidos = {f.name for f in fields(cls)}
        perfil = cls(**{k: v for k, v in crudo.items() if k in conocidos})
        if perfil.modo_firma not in MODOS_FIRMA:
            perfil.modo_firma = "app"
        return perfil

    def guardar(self, ruta: Path) -> None:
        ruta = Path(ruta)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
