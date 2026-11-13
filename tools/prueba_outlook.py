"""Prueba del enlace con Outlook en la PC del banco. Por defecto SOLO LEE: no crea ni envía nada.

Uso (desde la carpeta v2):
    py tools/prueba_outlook.py                                   lee: identidad y busca un hilo
    py tools/prueba_outlook.py --agencia CUSCO --campana "JULIO – AGOSTO 2026"
    py tools/prueba_outlook.py --agencia CUSCO --borrador        deja UN borrador de prueba en Borradores
    py tools/prueba_outlook.py --enviarme-prueba                 envía un correo de prueba SOLO a usted

Qué comprueba, en orden:
  1. Que Outlook responde y de quién es la cuenta (nombre, cargo, anexo del directorio).
  2. Cuántos buzones ve y si encuentra el correo de inicio de la agencia (solo asunto y fecha).
  3. Con --borrador: que el borrador se crea con la firma, el logo incrustado y se puede verificar.
  4. Con --enviarme-prueba: que el envío llega a su propia bandeja.
Nada de esto toca a las agencias: el borrador y la prueba llevan como único destinatario su correo.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agente_correos.correo.buscador_hilo import elegir_hilo                          # noqa: E402
from agente_correos.correo.modelos import CorreoPreparado                             # noqa: E402
from agente_correos.correo.outlook_gateway import OutlookGateway                      # noqa: E402
from agente_correos.correo.puerta import ErrorCorreo                                  # noqa: E402
from agente_correos.contenido.plantillas import asunto_inicio                         # noqa: E402
from agente_correos.dominio.avisos import TipoAviso                                   # noqa: E402
from agente_correos.entorno import nombre_completo_windows, usuario_windows           # noqa: E402
from agente_correos.usuario.firma import buscar_logo_en_firmas_outlook, construir_firma  # noqa: E402
from agente_correos.usuario.perfil import PerfilUsuario                               # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agencia", default="")
    ap.add_argument("--campana", default="JULIO – AGOSTO 2026")
    ap.add_argument("--borrador", action="store_true")
    ap.add_argument("--enviarme-prueba", action="store_true")
    a = ap.parse_args()

    puerta = OutlookGateway()
    print("1) Conexión con Outlook")
    try:
        ident = puerta.identidad()
    except ErrorCorreo as exc:
        print(f"   FALLÓ: {exc}")
        return 2
    print(f"   Cuenta de Windows : {usuario_windows()} ({nombre_completo_windows() or 'sin nombre de dominio'})")
    print(f"   Nombre en Outlook : {ident.nombre or '(vacío)'}")
    print(f"   Cargo / dependencia: {ident.cargo or '(vacío)'} / {ident.departamento or '(vacío)'}")
    print(f"   Teléfono / oficina : {ident.telefono or '(vacío)'} / {ident.oficina or '(vacío)'}")
    print(f"   Correo            : {'sí' if ident.correo else 'NO se obtuvo'}")

    logo = buscar_logo_en_firmas_outlook()
    print(f"   Logo en sus firmas de Outlook: {logo.name if logo else 'no encontrado'}")

    if a.agencia:
        print(f"\n2) Búsqueda del correo de inicio de {a.agencia}")
        asunto = asunto_inicio(a.agencia, a.campana)
        print(f"   Asunto buscado: {asunto}")
        try:
            r = elegir_hilo(puerta.buscar_enviados(asunto), asunto)
            print(f"   Resultado: {r.estado} · {len(r.candidatos)} candidato(s)")
            for m in r.candidatos[:5]:
                print(f"     - {m.enviado_en:%d/%m/%Y %H:%M}  {m.asunto[:90]}  [{m.almacen}]"
                      if m.enviado_en else f"     - {m.asunto[:90]}  [{m.almacen}]")
        except ErrorCorreo as exc:
            print(f"   FALLÓ: {exc}")

    if not (a.borrador or a.enviarme_prueba):
        print("\nSolo lectura. Agregue --borrador o --enviarme-prueba para probar la creación.")
        return 0
    if not ident.correo:
        print("\nNo se pudo obtener su correo: no se crea nada.")
        return 2

    perfil = PerfilUsuario.inicial(ident.nombre or nombre_completo_windows(), ident.correo)
    perfil.cargo = ident.cargo or "Practicante"
    firma = construir_firma(perfil, logo_src="cid:logo_firma" if logo else None)
    correo = CorreoPreparado(
        agencia=a.agencia or "PRUEBA", tipo=TipoAviso.RECORDATORIO,
        asunto="Prueba del Agente de Correos BN v2.0",
        para=[ident.correo], cc=[],
        html="<p>Este es un correo de prueba. Compruebe la firma y el logo.</p><br><br>" + firma,
        modo="nuevo", logo=logo,
    )
    accion = "borrador" if a.borrador else "prueba"
    print(f"\n3) Creación ({accion})")
    try:
        res = puerta.crear(correo, accion, prueba_para=ident.correo)
        print("   Creado. Destinatarios resueltos y adjuntos:", puerta.verificar(res.id_outlook))
        for adv in res.advertencias:
            print("   Aviso:", adv)
    except ErrorCorreo as exc:
        print(f"   FALLÓ: {exc}")
        return 2
    print("   Revise su carpeta Borradores o su Bandeja de entrada y confirme que la firma y el logo se ven bien.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
