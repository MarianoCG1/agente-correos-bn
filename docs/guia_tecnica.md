# Agente de Correos BN — v2.0

Reescritura ordenada de `../correos.py`. La v1 sigue funcionando sin cambios.
Estado y decisiones: [`proyecto.md`](proyecto.md).

## Fase 1 — núcleo (sin Outlook ni interfaz)

| Paquete | Qué hace |
|---|---|
| `agente_correos.configuracion` | Ajustes editables: jefatura, dominio, exclusiones, feriados, rutas |
| `agente_correos.dominio` | `Campana`, `TipoAviso`, `EstadoAviso`, `ClaveAviso`, `EventoAviso` |
| `agente_correos.datos` | `CronogramaLoader` (Excel flexible) y `DirectorioAgencias` (correos) |
| `agente_correos.datos.generador_entrega` | `GeneradorEntrega`: arma la entrega desde el original (solo lectura), con bitácora |
| `agente_correos.datos.auditoria_entrega` | Compara una entrega manual con su original |
| `agente_correos.reglas` | `CalendarioHabil` (viernes → lunes, feriados) y `PreflightValidator` |
| `agente_correos.historial` | `RegistroEjecuciones`: un archivo por persona y campaña; `reclamar()` evita el doble envío |
| `agente_correos.datos.repositorio_agencias` | `RepositorioAgencias`: correos editables con historial |
| `agente_correos.repositorio_configuracion` | `RepositorioConfiguracion` y `estado_de_rutas`: configuración y rutas auditadas |
| `agente_correos.contenido` | `construir_tabla` y `Plantillas` (mismo HTML que v1) |
| `agente_correos.usuario` | `PerfilUsuario` y `construir_firma` (firma por usuario) |

El enlace con Outlook (`OutlookGateway`) está escrito pero solo se puede validar en el banco: ver `tools/prueba_outlook.py`. El resto se prueba con una puerta simulada.

| Fase 2 | Qué hace |
|---|---|
| `correo.buscador_hilo` | Hilo por asunto exacto; si hay dos candidatos lo decide la persona |
| `correo.respaldo_red` | Lee las tres ubicaciones de respaldo de v1 y escribe en `BACKUP_CORREOS` |
| `correo.constructor` | Arma asunto, destinatarios, cuerpo, firma y cita: el mismo correo para la vista previa y el envío |
| `datos.excel_filtrador` | Adjunto de cada agencia a partir de la entrega vigente |
| `servicios.envio` | Revisión previa → reclamo → armado → Outlook → registro → respaldo |
| `correo.outlook_gateway` | Única clase con `win32com`; borrador, envío con espera para anular y envío de prueba |

Herramientas en `tools/`: `humo_datos_reales.py` (qué avisos saldrían), `auditar_entrega.py` (entrega manual contra original), `explorar_sharepoint.py` (solo lectura), `prueba_outlook.py` (enlace con Outlook) y `ordenar_respaldos.py` (junta en `BACKUP_CORREOS` los respaldos que v1 dejó dispersos; simula antes de copiar).

## Ejecutar la aplicación

```
py -m pip install -r requirements-ui.txt
py main.py
```

La interfaz está en `agente_correos/ui/web`. Para revisar sus pantallas en un navegador, sin Outlook ni datos
reales, sirva esa carpeta y abra `index.html?dev` (usa `dev_api.js`):

```
py -m http.server 8765 --directory agente_correos/ui/web
```

## Probar

Pruebas automáticas (datos sintéticos; incluyen paridad contra v1 si `correos.py` se puede importar):

```
pip install -r requirements-dev.txt
python -m pytest
```

Archivos de dependencias (desde la carpeta `v2`, no la raíz del repositorio, que es la de v1):
`requirements.txt` (núcleo), `requirements-dev.txt` (núcleo y pruebas) y
`requirements-ui.txt` (agrega pywebview; se usa desde la Fase 3).

Prueba de humo con los archivos reales. No envía nada ni imprime correos:

```
python tools/humo_datos_reales.py "RUTA\cronograma.xlsx" "RUTA\agencias_correos.xlsx" 2026-10-14
```

## Reglas del proyecto

- Todo acceso a Outlook (`win32com`) vivirá en una sola clase, `OutlookGateway` (Fase 2).
- La interfaz solo llama a servicios; no decide reglas.
- Ningún dato real del banco entra al repositorio: las pruebas usan Excel generados al vuelo.

## Instalador (PC sin git)

```powershell
powershell -ExecutionPolicy Bypass -File installer\construir.ps1
```

Compila con PyInstaller desde un entorno limpio (`.venv_build`) y arma `installer\Output\AgenteCorreosBN_<versión>_Setup.exe` con Inno Setup 6. Se instala sin administrador en `%LOCALAPPDATA%\AgenteCorreosBN`; los datos de cada persona (perfil, firma, registro de actividad) quedan en `%APPDATA%\AgenteCorreosBN` y no se tocan al actualizar. Si existe `..\data\agencias.json`, el instalador lo lleva como lista de partida (no está en git: tiene correos reales). Si algo falla, **Configuración › Soporte › Exportar diagnóstico** genera un zip con el registro y un resumen del equipo.

## Manual de usuario

`docs/Manual_de_usuario_Agente_Correos_BN.docx` (y su PDF). Las capturas usan la Api de ejemplo (`index.html?dev`, datos ficticios). Para regenerarlo: servir `agente_correos/ui/web` con `python -m http.server 8766`, ejecutar `node docs/manual/capturar.mjs` y luego `python docs/manual/construir_manual.py` (requiere `python-docx`).
