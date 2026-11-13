# Agente de Correos BN — Resumen por versiones

> Nodo de síntesis: qué aportó cada versión al proceso del área, con qué evidencia y qué falta validar.
> Pensado para alimentar el resumen de aportes de proyectos que se presentará a la Gerencia.
> Estado detallado y decisiones: [Estado del proyecto](proyecto.md). Última actualización: 4 de noviembre de 2026 (v2.0.4-beta).

## 1. El proceso que mejora

Cada campaña bimestral de entrega de fondos a ETV exige avisar a cada agencia del Banco de la Nación (hoy 20 en la lista, 18 por campaña) con su cronograma de pagos: **un correo de inicio** y **recordatorios** por cada fecha de pago (~36 fechas por campaña).

| Antes (manual) | Riesgo |
|---|---|
| Armar a mano un Excel por agencia, redactar cada correo, buscar el hilo para el recordatorio | Errores de copia, olvidos, tiempo del practicante |
| Dos personas pueden enviar el mismo aviso | Duplicados y avisos contradictorios a la agencia |
| La firma depende de cada persona | Formato desigual |
| Archivos dispersos entre carpetas | Se pierde la continuidad si cambia quien opera |

## 2. Resumen por versión

| Versión | Período | Qué es | Aporte principal | Estado |
|---|---|---|---|---|
| **Manual** | hasta ~mar/2026 | Excel + Outlook a mano | Línea base | Referencia |
| **v1** (`correos.py`, tkinter) | ~mar–abr/2026 → hoy | Genera borradores por agencia con tabla HTML y Excel filtrado adjunto; recordatorio en el hilo | Automatiza la redacción y el armado; ya usada por el área | ✅ en uso (la monitora la usa) |
| **Flujo desatendido** | 2026 | Envío programado sin persona | Intento de quitar la intervención humana | ❌ descartado: ocasionó problemas |
| **v2.0** (`v2/`) | desde 13/10/2026 | Rehecha por clases; control de campaña, envío desde la app con confirmación, firma por usuario | Control, trazabilidad y continuidad entre operadores | ⏳ construida; falta validar en el banco |
| **v2.1.0-beta** | 04/11/2026 | Revisa Enviados en segundo plano y puede enviar solo los recordatorios del día bajo supervisión | Lo enviado por fuera del programa se anota solo; el envío de la mañana puede salir sin intervención manual, con cuenta regresiva y anulación | ⏳ por validar con Outlook real (05/11 y 06/11) |
| **v2.0.1 → 2.0.4-beta** | 30/10 → 04/11/2026 | Ajustes para lanzar la campaña SO 2026 con el cronograma real | Correo de inicio con copia a la jefatura y al área; borradores propios regenerables; tabla del correo con ETV y entrega al frente y filas por fecha | ✅ instalador listo; ⏳ validar en el banco |

## 3. v1 — lo que logró y lo que la limitó

**Logró:** correos con tabla y adjunto por agencia, recordatorio en hilo, respaldo en SharePoint que permite a otra persona continuar.

**Límites medidos en el análisis (12 hallazgos, 13/10/2026):**

| Límite | Consecuencia |
|---|---|
| Sin registro de lo enviado | Correr dos veces duplicaba los avisos |
| `auto_send` activado por defecto | Riesgo de envío sin revisión |
| Hilo buscado por texto parcial | Podía responder en el hilo equivocado |
| Celda de correo vacía quedaba como `nan` | Figuraba "generado" sin destinatario |
| Sin encabezado detectado, el adjunto llevaba todas las filas | Una agencia podía ver datos de otras |
| Rutas y textos escritos en el código | Cada cambio exigía tocar código |
| 2.780 líneas en una clase, sin pruebas | Costoso de mantener |
| Sin firma individual | Se dejaba como borrador y cada uno enviaba a mano |

## 4. v2.0 — qué cambia en el proceso

| Capacidad | Qué resuelve |
|---|---|
| **Tablero de control** (agencias × fechas de pago) | Se ve qué avisos salieron, cuáles faltan y cuáles están bloqueados |
| **Envío desde la app con confirmación** y ventana de anulación | La persona decide con la lista a la vista; hay un margen para deshacer |
| **Anti doble envío** (registro compartido y reclamo previo) | Practicante y monitora no se pisan |
| **Registro de quién envió qué y cuándo** | Trazabilidad por campaña y por persona |
| **Firma por usuario** generada por la app (logo "60 años", línea, texto) | Formato uniforme sin depender de Outlook |
| **Genera el archivo de ENTREGA** desde el cronograma original | Reemplaza armarlo a mano; el original queda intacto |
| **Agencias y correos editables** con historial | Un cambio de correo ya no es un cambio de código |
| **Rutas auditables y modificables** | Cualquier ruta que cambie se corrige desde Configuración |
| **Reutiliza las carpetas de SharePoint** que ya existen | La monitora no cambia su forma de trabajar |
| **222 pruebas automáticas**, incluida paridad con v1 | El cambio no rompe lo que ya funcionaba |
| **Correo de inicio enviable desde la pantalla**, con copia fija del área | La campaña arranca desde la misma herramienta y la jefatura y el área reciben copia como antes |
| **Tabla del correo ordenada por fecha**, con ETV, Base, N° Pagadores, Agencia, Fecha y Hora al frente | Quien recibe ve de inmediato a qué ETV pedir los fondos y en qué orden (pedido de la monitora, 04/11) |
| **Manual de usuario** (Word y PDF, 31 páginas) | Una persona nueva puede operar el programa sin acompañamiento |
| **Instalador propio** y diagnóstico exportable | Se instala sin administrador y los fallos se pueden revisar sin acceso al equipo |
| **Confirmación de lectura** opcional por envío | Permite saber qué agencias abrieron el aviso (si aceptan enviar el acuse) |

## 5. Evidencia disponible

| Dato | Fuente | Condición |
|---|---|---|
| El generador reproduce la entrega manual de JA 2026 (310 filas, 29 columnas) | Comparación con archivos reales | ✅ verificado |
| Detectó 2 defectos en la entrega armada a mano (referencia `#REF!` en 310 filas; un valor suelto en totales) | Auditoría contra el original | ✅ verificado |
| 10 puntos suspendidos identificados (S/ 243,805 y 974 usuarios) | Original vs. entrega | ✅ verificado |
| Estructura y velocidad de SharePoint (listar ≈ 100 ms; escribir ≈ 1 s) | `explorar_sharepoint.py` en el banco | ✅ medido |
| 36 carpetas de respaldo dispersas ordenadas sin conflictos | `ordenar_respaldos.py` en el banco | ✅ aplicado |
| Pruebas pasan con Python 3.13 en el banco | pytest en el banco | ✅ (69 de 69 en ese momento) |
| Con el cronograma real de SO 2026 (332 filas, 17 agencias, 34 fechas de pago) se arman los 17 correos de inicio y la entrega sin errores; 9 agencias tienen filas sin importe de Pensión 65, que el programa marca en rojo | Ejecución sobre el archivo real (04/11) | ✅ verificado (sin enviar) |
| Tiempo manual de 4–6 h y de la app menor de 3 min | Declarado por el área | ⚠️ **sin medir**; no usar como cifra defendible aún |
| Envío real, firma y anulación con Outlook del banco | — | ⏳ pendiente |

## 6. Pendiente para completar el relato

- Cronometrar un envío manual y uno con la app para obtener una cifra propia (igual que en AutoPSJN).
- Una campaña real completa con v2 y su registro como evidencia.
- Confirmación de lectura de los correos: ✅ implementada el 21/10 (casilla en cada envío); falta verla en el banco y leer los acuses para medir qué agencias abrieron el aviso (ver [Estado del proyecto](proyecto.md) §8).
- Instalador `.exe` para instalarlo en cada trabajador que se incorpore: ✅ generado (2.0.4-beta, 04/11); instalado y abierto en el banco el 21/10, falta el envío real.
- Ideas siguientes (sin construir): lectura del Outlook propio en segundo plano para registrar lo enviado por fuera de la app y los acuses; envío automático supervisado por la mañana. Detalle en [Estado del proyecto](proyecto.md) §8.

## 7. Cómo reutilizar este nodo en el resumen de aportes

Cada proyecto del área puede resumirse con el mismo formato: **proceso antes → qué cambió → evidencia medida → qué falta validar**. La fila de «Evidencia» separa lo verificado de lo declarado para que cada cifra presentada sea defendible.
