# Contrato de API — interfaz ↔ programa

Implementado en `v2/agente_correos/ui/api.py` y consumido por `v2/agente_correos/ui/web/app.js`.
La maqueta v3 dejó de calcular datos: toda regla vive en Python y la interfaz solo pinta.

## Convenciones

- `webview.create_window(..., js_api=Api())`, el mismo patrón de `AutoPSJN/Auto_PSJN_6.0.py`.
- Cada método devuelve `{"ok": true, "datos": …}` o `{"ok": false, "error": "texto para la persona"}`. Nunca lanza excepciones a JavaScript.
- Cada llamada de pywebview corre en un hilo distinto: `OutlookGateway` guarda su conexión COM por hilo.
- Los envíos son un **lote en segundo plano**: `confirmar_envio` devuelve un `lote` y la interfaz consulta `progreso` cada 600 ms.
- Fechas en ISO (`2026-10-14`); la interfaz las acorta. El correo llega ya armado.
- La carpeta compartida se abre la primera vez que se necesita (la ventana aparece sin esperar a la red).

## Métodos

| Método | Para qué | Devuelve (`datos`) |
|---|---|---|
| `iniciar()` | Arranque de la ventana | `usuario`, `nombre`, `hoy_largo`, `outlook`, `compartida_ok`, `perfil_completo`, `hay_entrega`, `hay_agencias`, `minutos_anulacion` |
| `estado_campana(refrescar)` | Tablero | `campana`, `coherencia`, `objetivo`, `fechas[]`, `agencias[{nombre, etvs, celdas{fecha: {estado, motivo}}, para, cc, sin_correo}]` |
| `preparar_revision(tipo, fecha)` | Revisión previa | `filas[{agencia, veredicto, motivo, advertencias, hilo{estado, candidatos[]}}]` |
| `vista_previa(agencia, tipo, fecha, id_hilo)` | El correo exacto | `asunto`, `para`, `cc`, `html` (para `<iframe srcdoc>`), `modo`, `adjunto{nombre, filas}` |
| `confirmar_envio(selecciones, accion)` | Enviar o dejar borradores | `lote`, `total` |
| `progreso(lote)` | Seguimiento | `hechos`, `total`, `actual`, `terminado`, `resultados[]`, `anulable_hasta` |
| `cancelar_envio(lote)` | Detener lo que falta | `true` |
| `anular_envio(lote)` | Anular durante la espera | `anulados`, `solicitados` |
| `enviarme_prueba(agencia, tipo, fecha, id_hilo)` | Prueba al propio correo | `enviado_a` |
| `historial(agencia, estado, texto)` | Registro de avisos | `campana`, `total`, `filas[]` |
| `entrega_elegir_original()` / `entrega_subir_original(nombre, base64)` | Cargar el original (diálogo o arrastre) | `token`, `puntos[]`, `campana`, `nombre_sugerido`, `carpeta_sugerida` |
| `entrega_elegir_destino(nombre, carpeta)` | «Guardar como…» | `ruta` |
| `entrega_generar(token, destino, suspendidos, reprogramaciones, usar_como_vigente)` | Generar la entrega | `filas_entrega`, `filas_quitadas`, `columnas_quitadas`, `bitacora` |
| `agencias_listar` · `agencia_agregar` · `agencia_actualizar` · `agencia_estado` · `agencias_historial` · `agencias_importar` | Lista de agencias editable | agencias, historial o resumen de importación |
| `config_obtener()` · `config_guardar(valores)` · `config_elegir_ruta(campo)` | Configuración y rutas auditadas | `valores`, `rutas[{campo, estado}]`, `historial[]` |
| `perfil_obtener()` · `perfil_guardar(valores)` · `firma_vista_previa(valores)` | Perfil y firma | `perfil`, `detectado_de`, `firma_html` |

## Estados que pinta la interfaz

`env` enviado · `borr` borrador · `hoy` pendiente de hoy · `pend` pendiente · `omit` omitido o anulado ·
`bloq` bloqueado · `dec` requiere decisión o falló · `venc` vencido sin registro.

## Cambios respecto de la maqueta v3

1. Se quitó el selector de campaña (la campaña la da el archivo de entrega vigente).
2. Revisión previa: **Enviar N correos**, **Dejar como borradores** y **Enviarme una prueba**; confirmación con la lista.
3. Tras enviar, cuenta regresiva y botón **Anular envío** mientras dura la espera.
4. La vista previa es el correo real dentro de un `<iframe>`: tabla, firma y logo como saldrán.
5. Pantalla nueva **Preparar entrega**: zona de arrastre, puntos suspendidos sugeridos por la marca roja, reprogramaciones y «Guardar como…».
6. Configuración: **Mi perfil y firma**, **Rutas** con su estado, **Agencias y correos** editables y **cambios recientes**.
7. Nuevo estado `venc` para fechas pasadas sin registro de aviso (incluye lo enviado antes de usar esta versión).
