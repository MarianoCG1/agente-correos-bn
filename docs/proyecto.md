# Agente de Correos BN — Estado del proyecto

> Nota viva del proyecto. Vive en este repositorio y **no** se mezcla con la bóveda de AutoPSJN ni con `Flujo_completo_correos_etv`.
> Última actualización: 4 de noviembre de 2026 (versión 2.1.0-beta, campaña SO 2026). Resumen por versión y aportes al proceso: [Resumen por versiones](resumen_por_versiones.md).

> **Nota sobre las rutas.** Esta nota viva se escribió en el repositorio de trabajo, donde el código vivía en `v2/` y la versión original en la raíz. En este repositorio el código actual está en la raíz y la versión original en `legacy/v1/`. Los nombres de personas, direcciones y rutas de red reales fueron reemplazados por valores de ejemplo.

## 1. Qué es

Aplicativo de escritorio (Python + Outlook COM) que prepara y envía a las agencias del Banco de la Nación los correos de entrega de fondos de las ETV:

- **Inicio de campaña:** un correo por agencia con tabla HTML y Excel filtrado adjunto.
- **Recordatorio:** correo de seguimiento para una fecha objetivo, en el hilo original cuando existe.

Lo opera el personal de Caja y Valores; hoy, un practicante. **Cada envío lo decide una persona tras revisar.**

## 2. Dónde estamos

| Elemento | Estado | Nota |
|---|---|---|
| v1 (`correos.py`, tkinter) | ✅ en uso | 2.780 líneas en una sola clase; no se toca |
| Automatización desatendida (`Flujo_completo_correos_etv`) | ❌ descartada | Ocasionó problemas; no se retoma |
| v2.0 Fase 1: núcleo sin Outlook (`v2/`) | ✅ construido · ⏳ validar en banco | 69 pruebas, incluida paridad con v1 |
| v2.0 Fase 1b: preparar la entrega desde el original | ✅ construido | 84 pruebas; reproduce el archivo real JA 2026 (ver §4) |
| v2.0 Fase 1c: espacio compartido (registro con reclamo, agencias editables, configuración auditada) | ✅ construido | 108 pruebas |
| v2.0 Fase 2: capa de correo (hilo exacto, respaldo, adjunto vigente, armado, envío con reclamo) | ✅ construida con puerta simulada · ⏳ validar `OutlookGateway` en el banco | 131 pruebas; falta `tools/prueba_outlook.py` |
| v2.0 Fase 3: `Api` de pywebview e interfaz conectada (`main.py`) | ✅ construida · ⏳ validar en el banco | 150 pruebas; interfaz revisada contra una Api de ejemplo |
| v2.0 Fase 3: interfaz pywebview (maqueta v3) | ⏳ | Contrato en `docs/contrato_api.md` |
| Maqueta v3 | ✅ aprobada | `docs/maqueta/index.html`; se conecta a datos reales en Fase 3 |
| **v2.0.4-beta en la campaña SO 2026** (inicio 04/11, primer pago 05/11) | ✅ instalador listo · ⏳ validar en el banco | 222 pruebas. Verificada con el cronograma real: 332 filas, 17 agencias, 34 fechas de pago; los 17 correos de inicio se arman con Para 1 y CC 5. La monitora y el practicante comparten `BACKUP_CORREOS\_PROGRAMA` y el registro |
| **v2.1.0-beta: revisar Enviados y envío automático supervisado** | ✅ construido (255 pruebas, con Outlook simulado) · ⏳ validar en el banco: 05/11 en el equipo del usuario, 06/11 en el de la monitora | Ver §3 y §8; ajustes en Configuración › Automático |
| Manual de usuario (Word y PDF, 31 págs.) | ✅ | `docs/Manual_de_usuario_Agente_Correos_BN.docx`; aún no incluye Configuración › Automático (pendiente de regenerar) |

## 3. Decisiones tomadas

| Decisión | Motivo | Fecha |
|---|---|---|
| Rehacer como **v2.0 en `v2/`**, sin tocar v1 | v1 sigue operando; v2 se prueba en paralelo | 13/10 |
| Código por **clases de una sola responsabilidad**; solo `OutlookGateway` importa `win32com` | v1 repite la lógica de Outlook en tres proyectos | 13/10 |
| **Envío desde la app con confirmación explícita**; "dejar como borrador" como alternativa | La app sabe qué salió (estado "Enviado" real) y deja de depender de la firma de cada persona. Reemplaza la decisión previa "solo borradores" | 13/10 |
| Frenos al envío: confirmación con lista, ventana de anulación (entrega diferida de Outlook), "enviarme una prueba" y registro **antes** de enviar | El error en un envío es irreversible | 13/10 |
| **Buzón personal de cada usuario**; el nombre se detecta al abrir el programa | La app estará instalada en cada trabajador que se incorpore | 13/10 |
| **Firma por usuario**, generada por la app con el formato del banco | Cada persona hoy la arma en Outlook; ver §6 | 13/10 |
| Registro de avisos como **archivos JSON sin modificar, uno por evento**, en la carpeta compartida | Varias personas escriben a la vez sin pisarse; SQLite sobre carpeta de red no es seguro | 13/10 |
| Interfaz con **pywebview** sobre la maqueta v3 | Ya funciona en el banco con AutoPSJN 6.0 | 13/10 |
| Pantalla principal = **tablero de control de campaña** (agencias × fechas de pago) | El objetivo es controlar el avance de los avisos, no solo generar | 13/10 |
| **SharePoint es la única ubicación de trabajo**: original, entrega, respaldos y registro | La monitora ya envía los correos y la lógica continúa gracias al respaldo subido ahí; afianza el trabajo y lo agiliza | 13/10 |
| **El original es de solo lectura**; los cambios se hacen siempre en copias | Orden de trabajo del área | 13/10 |
| La app **genera el archivo de entrega** a partir del original, aplicando los cambios | Hoy se arma a mano; es lo que precede a todo envío | 13/10 |
| El tablero y los correos usan el archivo de **entrega**; la copia de seguimiento por programa social queda fuera de esta app | Es el que el área ya usa para enviar | 13/10 |
| **Sin login propio**: la identidad es la cuenta de Windows | El banco ya autentica; una contraseña más no aporta seguridad | 13/10 |
| **Sin roles ni flujo de aprobación**: quien opera envía. Hay trazabilidad (quién, cuándo) pero no permisos por rol | El practicante envía y la monitora a veces se adelanta; ambos apuntan al mismo respaldo en SharePoint | 13/10 |
| **Anti doble envío**: antes de enviar se relee el registro compartido, se reclama el aviso y se vuelve a comprobar que nadie lo reclamó antes | Es el riesgo real cuando dos personas operan el mismo día | 13/10 |
| **Se reutilizan las carpetas que ya hay**: lo nuevo cuelga de `BACKUP_CORREOS`. Una sola carpeta nueva, `_PROGRAMA` (configuración, agencias, perfiles); el registro de avisos vive en `BACKUP_CORREOS/<año>/<campaña>/_REGISTRO` | v1 ya generaba esas carpetas y la monitora depende de ellas; no se agrega una estructura aparte | 13/10 |
| **La entrega vigente se detecta sola**: la configurada si existe; si no, la campaña más reciente de la carpeta (por año y orden bimestral). Los mensajes de la aplicación nunca piden un archivo concreto | La entrega de v1 quedaba apuntando a una campaña anterior (MA) y la app pedía ese archivo | 13/10 |
| La hoja de trabajo es `CRONOGRAMA ETV`; las hojas «original», copia o respaldo solo se usan si no hay otra | En la entrega real había una hoja `CRONOGRAMA ETV_ORIGINAL` y se estaba leyendo esa | 13/10 |
| **La lista de agencias se convierte sola**: al primer arranque, si aún no hay agencias, se toma el Excel de v1 (buscado donde v1 lo buscaba) y queda como JSON compartido; después se edita desde el programa | Evitar que cada persona tenga que importarla | 13/10 |
| **El JSON de agencias se prepara una vez** con `tools/cargar_agencias.py` y se coloca en `BACKUP_CORREOS/_PROGRAMA` o en la carpeta `data` del programa; no se sube al repositorio porque lleva correos reales | Los datos del banco no entran a git | 13/10 |
| En Configuración, **Agencias y correos** tiene su propia pestaña: agregar, editar, desactivar y **eliminar**, con historial | Pedido del usuario | 13/10 |
| La firma de Outlook por defecto **nunca funcionó** (ni en v1): no estaba configurada. La firma que sirve es la del programa | El usuario lo confirmó; la opción de Outlook ya no se ofrece salvo que alguien la tenga elegida | 13/10 |
| **La ventana abre siempre maximizada** | Pedido del usuario; igual que AutoPSJN | 13/10 |
| **Se distribuye con un instalador** (PyInstaller + Inno Setup) que se pasa por SharePoint; se instala en el perfil del usuario, sin administrador | En el banco no hay git; es lo que ya hace AutoPSJN | 21/10 |
| El instalador puede llevar `agencias.json` como lista de partida; solo se copia si no existe y no está en el repositorio | Evita el paso manual del primer arranque; los correos del banco no entran a git | 21/10 |
| Sin entrega o sin agencias, la pantalla principal muestra **«Antes de empezar»**: qué falta y un botón por cada cosa | La pantalla vacía no explicaba nada | 21/10 |
| **Confirmación de lectura** opcional en cada envío (valor inicial configurable) | Idea planteada por el área; el acuse no prueba que no leyó si no llega | 21/10 |
| El programa puede **exportar un diagnóstico** (log + resumen) | No hay acceso al equipo del banco para ver qué falló | 21/10 |
| Tres formas de firma por persona: la del programa (recomendada), la que ya tiene en Outlook, o ninguna | La del programa se ve igual en la vista previa y en cualquier PC; la de Outlook conserva firmas que el programa no puede reproducir | 13/10 |
| ~~El tablero muestra por defecto el inicio y las fechas de la última semana en adelante; «Ver toda la campaña» las muestra todas~~ → **El tablero muestra el inicio y como máximo 5 fechas**; la persona se mueve con la barra, las flechas (de 5 en 5) o «Ir a hoy». Abre con un día pasado, hoy y los siguientes. Un botón «Sin registrar (n fechas)» lleva a la fecha más antigua con avisos sin registro | Con todo visible se pierde lo pendiente del día; a la vez hay que poder revisar si faltó un recordatorio en el pasado. Pedido del usuario tras probar el instalador | 21/10 |
| Los respaldos que v1 dejó dispersos se **ordenan copiándolos** a `BACKUP_CORREOS` (`tools/ordenar_respaldos.py`: primero simula; nunca borra ni pisa) | v1 los dejó en tres ubicaciones según la ruta configurada ese día | 13/10 |
| El cronograma original se **arrastra a una zona** de la pantalla (como en el Extractor de notas); el archivo se lee en JavaScript y pasa a Python en base64 | Técnica que ya funciona en el banco; el navegador no entrega la ruta del archivo | 13/10 |
| Tras generar, la persona **elige dónde guardar** la entrega; el programa recuerda la carpeta y la propone en cada inicio de campaña | Que toda campaña apunte siempre a la misma carpeta | 13/10 |
| **Todas las rutas se pueden auditar y cambiar** desde Configuración; cada cambio guarda quién, cuándo, valor anterior y nuevo | Pedido del usuario | 13/10 |
| **El correo de inicio de campaña se envía desde la app**: botón «Correos de inicio (n)» en el tablero y la misma revisión previa de los recordatorios (correo nuevo con el Excel de la agencia). Una agencia con respaldo del inicio (v1, v2 u otra persona) se omite; si se anula un inicio a tiempo, se retira su respaldo para poder reenviarlo. Al comenzar la campaña, el inicio sin registrar figura como «pendiente de hoy» y después como «vencido» | Hasta el 21/10 la pantalla solo podía enviar recordatorios, aunque la campaña nueva empieza con el inicio | 21/10 |
| **La tabla del correo lleva al frente ETV, Base, N° Pagadores, Agencia, Fecha y Hora de entrega y sus filas van por fecha y hora de entrega** (a igual fecha, por ETV, distrito y punto); el resto del contenido sigue igual y lo que se movió no se repite al final. Vale para el inicio, los recordatorios y la vista previa. El Excel adjunto no se reordena | Pedido de la monitora: quien recibe el correo debe ver ordenado por fecha a qué ETV pedir los fondos; antes salía tal cual el archivo | 04/11 |
| **Copia fija del área en los correos**: lista editable en Configuración › Jefatura y envío (compartida). Va en CC del correo de inicio, sumada a la copia de cada agencia (administrador), sin repetidos; en los recordatorios sin hilo se le quitan los «excluidos». Viene cargada con la jefatura y tres integrantes del área, tomados del correo de inicio de la campaña EF 2026 (`email_formato_recordatorio.txt`). Admite pegar varias direcciones de una vez, incluso en el formato de Outlook | El programa nuevo solo copiaba la columna del Excel de agencias; la versión anterior tenía al jefe y al área en esa celda | 04/11 |
| **Un borrador propio se puede volver a generar** (el de otra persona se sigue omitiendo); el tablero ofrece «Inicios en borrador (n)» y mantiene activo «Preparar avisos» cuando solo hay borradores | Si se descartaba el borrador en Outlook, el programa lo seguía dando por hecho | 04/11 |
| **Dos niveles de configuración**: lo compartido (jefatura, exclusiones, feriados, minutos, lectura, respaldo) vive en `_PROGRAMA\config.json`; lo propio del equipo (entrega vigente, carpeta del original, carpeta de entregas, carpeta compartida, Excel de agencias) vive en `%APPDATA%\AgenteCorreosBN\local.json`. Cada ruta indica «Solo este equipo» o «Compartida con todos». La carpeta compartida nueva se usa al reabrir | Una ruta local (Descargas) guardada en lo compartido llegaba a las demás personas | 21/10 |
| **El programa revisa la carpeta Enviados de la persona** (solo lectura, cada 3 minutos mientras está abierto) y anota en el registro compartido los avisos que salieron por fuera de él (a mano, con v1 o por la monitora desde su Outlook). Solo cuenta un correo cuyo asunto es exactamente el de un aviso de la campaña y sin «RE:/RV:/[PRUEBA]»; el recordatorio se identifica además por la fecha de pago escrita en su cuerpo (si no se puede leer, no se anota). No se leen los acuses «Leído:» | El registro solo veía lo enviado desde el programa; un borrador enviado a mano seguía figurando como borrador y, con el envío automático, habría duplicados. Los acuses se descartan por ahora: el usuario los ve complicados y poco necesarios | 04/11 |
| **Envío automático supervisado** (opcional, apagado de fábrica, por equipo): a la hora elegida prepara los recordatorios cuya víspera hábil es hoy y los envía tras una cuenta regresiva en pantalla (ventana al frente y sonido; «Cancelar» y «Enviar ahora»). Solo salen los que pasan la revisión **sin advertencias** y se pueden responder en el hilo o con el respaldo en red; el resto queda para revisión manual con su motivo. **Nunca envía correos de inicio.** Conserva la ventana de anulación. Si el programa se abre pasadas 3 h de la hora, ese día no se envía solo. «Probar ahora» hace lo mismo sin esperar la hora y puede dejar borradores en lugar de enviar (ensayo). Requiere programa y Outlook abiertos y carpeta compartida accesible | Pedido del usuario (04/11): estando presente por la mañana, que el programa mande solo. Se descartó el envío sin persona y sin revisión (flujo desatendido anterior) | 04/11 |
| **Correos de las agencias editables** desde el programa (alta, cambio, desactivar) con historial; no se borran, se desactivan | Puede añadirse una agencia en cualquier campaña | 13/10 |
| El registro de avisos es **un archivo por persona y campaña**, escrito directo, sin renombrar y por lotes | SharePoint: crear ≈ 0,9 s, renombrar ≈ 2,7 s, leer ≈ 0,2 s (medido 13/10) | 13/10 |

## 4. Hallazgos de v1 y su estado en v2.0

Referencias a líneas de `correos.py`.

| # | Hallazgo en v1 | Línea | Resuelto en v2.0 por | Estado |
|---|---|---|---|---|
| 1 | Sin encabezado "Agencia" detectado, el Excel filtrado copia **todas** las filas a cada agencia | 2269 | `ExcelFiltrador`: sin encabezado no hay adjunto y la agencia se bloquea | ⏳ F2 |
| 2 | El hilo se busca por subcadena (`"LIMA" in asunto`) | 1849 | `BuscadorHilo`: asunto exacto + decisión manual si hay 2 hilos | ⏳ F2 |
| 3 | `auto_send` en `True` por defecto | 370 | Sin programador; envío solo tras confirmar | ✅ |
| 4 | Sin registro: correr dos veces duplica | 2373 | `RegistroEjecuciones` + `PreflightValidator` | ✅ |
| 5 | Celda de correo vacía queda como `'nan'` y figura `GENERADO` | 2505 | `DirectorioAgencias` + `PreflightValidator` | ✅ |
| 6 | El Excel filtrado usa `wb.active`, no la hoja detectada | 2241 | `Cronograma.hoja` se entrega al filtrador | ⏳ F2 |
| 7 | Se recarga el Excel de SharePoint y se re-escanea Outlook por agencia | 2240, 1933 | Carga única del Excel ✅; un solo barrido de Enviados ⏳ | parcial |
| 8 | El respaldo solo se busca junto al cronograma; guarda la hora del borrador | 2044 | `RespaldoRed` | ⏳ F2 |
| 9 | Jefe, dominio y textos escritos en el código | 1692, 2535 | `Configuracion` | ✅ |
| 10 | Reporte a un portal inexistente: 28 timeouts | 2732 | Eliminado | ✅ |
| 11 | Temporales sin limpiar; `requirements.txt` del stack antiguo | — | `requirements.txt` nuevo ✅; `GestorTemporales` ⏳ | parcial |
| 12 | Sin pruebas automáticas | — | `v2/tests` | ✅ |

**Hallazgos nuevos al construir la Fase 1**

- `detect_header_row` de v1 calculaba los vacíos sobre texto, así que nunca penalizaba celdas vacías. v2 lo calcula sobre los datos; sobre el archivo real elige la misma fila.
- `texto_relativo` de v1 decía "el día de mañana" también cuando la fecha era hoy. v2 distingue hoy y mañana.
- **La entrega armada a mano trae dos defectos** (detectados al compararla con el original): la última columna (clave `ddpp` + `Cod`) tiene `=AC3&#REF!` en las 310 filas, porque al borrar la columna "Cod" se perdió la referencia; y la fila de totales tiene un `321` suelto en la columna N°. El generador conserva el valor calculado de esa clave y no deja el total con residuos.
- El nombre de la campaña indica el período cubierto y los pagos caen **2 meses después** (EF → marzo–abril, MA → mayo–junio, MJ → julio–agosto, JA → septiembre–octubre; verificado en 4 archivos reales). Una primera versión de la advertencia de coherencia lo trató como error; ya está corregida y avisa solo cuando las fechas no corresponden a ese desfase.

## 4b. SharePoint: estructura real (explorada el 13/10/2026)

Raíz: `…/PPSS/PROGRAMAS SOCIALES - ETV/ENTREGA DE FONDOS` (enlace `https://servidor/bn/operaciones/sitio/Documentos compartidos/…`, ruta Windows `//servidor@SSL/DavWWWRoot/…`).

```
ENTREGA DE FONDOS/
  ENTREGA DE FONDOS ETV JA 2026 difusion.xlsx       entrega vigente (modificada 24/09)
  ENTREGA DE FONDOS ETV MJ 2026 difusion.xlsx       entrega anterior
  prueba.xlsx                                       archivo suelto
  2025/   entregas ND 2025 y SO 2025 BN
  2026/   entregas EF y MA 2026 · carpetas 'MARZO – ABRIL 2026', 'MAYO – JUNIO 2026' y una '2026' anidada
          2026/MARZO – ABRIL 2026/<AGENCIA>/{cuerpo_principal.html, entrega.xlsx, metadata.json}
          2026/2026/JULIO – AGOSTO 2026/<AGENCIA>/…            (respaldo del 02/09)
  BACKUP_CORREOS/2026/
          JULIO – AGOSTO 2026/<18 agencias>                    (respaldo del 07/09)
          MAYO – JUNIO 2026/<AREQUIPA, CHICLAYO, PIURA>        (solo 3 de 18)
```

| Observación | Consecuencia para v2 |
|---|---|
| Los respaldos de v1 viven en **tres ubicaciones** según la ruta que tenía configurada cada día: `año/campaña/agencia`, `año/año/campaña/agencia` y `BACKUP_CORREOS/año/campaña/agencia` | `RespaldoRed` lee las tres y elige la copia más reciente; escribe solo en `BACKUP_CORREOS/año/campaña/agencia` |
| El respaldo de MJ en `BACKUP_CORREOS` tiene 3 de 18 agencias; las 18 están en la ubicación anterior | Lo anterior evita que la continuidad dependa de dónde se guardó |
| Carpetas de agencia sin prefijo (`CUSCO`, `JAEN`), campañas con el guion largo `–` | Mismos nombres que v1; v2 no cambia ninguna convención |
| `metadata.json` con los campos `campaign, agency, subject, to, cc, sent_by, pc_name, saved_at, excel_filename` | v2 lo lee tal cual y escribe el mismo formato |
| La entrega JA se modificó el 24/09; los respaldos son del 02/09 y 07/09 | Hipótesis: el Excel dentro del respaldo puede traer fechas anteriores a una reprogramación. v2 regenera el adjunto desde la entrega vigente |
| Mediana de 104 ms por listado, máximo 505 ms; escribir ≈ 0,9 s y renombrar ≈ 2,7 s | Un registro con cientos de archivos pequeños sería lento: **un archivo por usuario y campaña**, escrito directo y por lotes |
| Ningún archivo `~$` abierto | Sin bloqueos al momento de explorar |

## 5. Arquitectura de v2.0

```
v2/
  agente_correos/
    entorno.py              usuario, equipo y carpetas de Windows
    configuracion.py        Configuracion                       ✅ F1
    dominio/                Campana, TipoAviso, EstadoAviso     ✅ F1
    datos/                  CronogramaLoader, DirectorioAgencias ✅ F1
                            GeneradorEntrega, auditoria_entrega ✅ F1b · ExcelFiltrador ⏳ F2
    reglas/                 CalendarioHabil, PreflightValidator ✅ F1
    historial/              RegistroEjecuciones (un archivo por persona, reclamo antes de enviar) ✅ F1c
    repositorio_configuracion.py   configuración con historial y estado de rutas        ✅ F1c
    datos/repositorio_agencias.py  agencias editables con historial y conflicto de edición ✅ F1c
    contenido/              construir_tabla, Plantillas         ✅ F1
    usuario/                PerfilUsuario, construir_firma      ✅ F1
    correo/                 OutlookGateway (único con win32com), BuscadorHilo, RespaldoRed, ConstructorCorreo ✅ F2
    servicios/              EnvioService (revisión → reclamo → armado → envío → registro → respaldo) ✅ F2
    datos/excel_filtrador.py  ExcelFiltrador (adjunto de cada agencia desde la entrega vigente)   ✅ F2
    ui/                     Api (pywebview) + web/ (index.html, app.css, app.js, dev_api.js)  ✅ F3
  main.py                   arranque: ventana de pywebview con la Api
  tests/   tools/
```

Capas: `ui` solo llama a `servicios`; las reglas y el contenido se prueban sin Outlook.

## 6. Firma por usuario

Modelo: las firmas de la sección tienen el mismo formato. Logo "60 años" a la izquierda, línea vertical y bloque de texto:

| Línea | Ejemplo |
|---|---|
| Cargo - Nombre (negrita) | `Practicante - Ana B. Pérez Quispe`; sin cargo, solo el nombre |
| Dependencia | `Sección Caja y Valores en Custodia \| Sub Gerencia Caja y Valores \| Gerencia de Operaciones \| BN` |
| Teléfono y anexo | `Telf: 519-2000 Anexo 12345` (anexo en negrita) |
| Dirección | `Oficina Principal del BN – San Borja` o `Av. Javier Prado Este 2499 - San Borja` |
| Correo (opcional) | `E-mail: pra_aperez@bn.com.pe` (enlace en negrita) |
| Confidencialidad (opcional) | `Este correo y sus adjuntos son confidenciales…` en cursiva pequeña |

- Al abrir por primera vez, el nombre se detecta del equipo (Fase 1) y de Outlook (Fase 2: nombre, anexo y correo desde el directorio). La persona confirma y ajusta.
- El logo se **reutiliza de la firma que ya tiene guardada en Outlook** (`%APPDATA%\Microsoft\Signatures`), sin distribuirlo con la aplicación. Se adjunta al correo como imagen incrustada.
- Tres modos por usuario: firma de la app, firma de Outlook (como v1) o ninguna.

## 7. Reglas de negocio que se conservan de v1

- Asunto de inicio: `Programación de Fondos – BN {agencia} – {campaña}`. Recordatorio: `RECORDATORIO: Entrega de Fondos – BN {agencia} – {campaña}`.
- Fecha objetivo: el siguiente día hábil (viernes y sábado → lunes); los feriados se configuran.
- Recordatorio en hilo: `ReplyAll`, solo adjuntos `.xlsx` del padre, sin destinatarios externos ni la jefatura excluida.
- Sin hilo en este Outlook: se reconstruye desde el respaldo en red con cabecera de mensaje citado.
- Juntos y Contigo solo se mencionan si el punto tiene usuarios.
- Tabla con los colores del Excel; dato faltante = celda roja.

### Archivos de una campaña

La campaña arranca con el cronograma original y de él salen dos copias de trabajo. Verificado con JA 2026:

| Archivo | Para qué sirve | Estado |
|---|---|---|
| `CRONOGRAMA ETV {código} {año} difusion` | Original que inicia la campaña (320 filas, 32 columnas) | ✅ carga |
| `ENTREGA DE FONDOS ETV {código} {año} difusion` | Copia reordenada; de aquí salen los correos y el Excel filtrado (310 filas, 29 columnas) | ✅ carga |
| Tercera copia de seguimiento | Se arma para verificar también por programa social | ⏳ no recibida |

Diferencias verificadas entre el original y la entrega (JA 2026):

| Cambio | Detalle |
|---|---|
| Puntos suspendidos | 10 filas quitadas (JAÉN 6, TARAPOTO 3, AYACUCHO 1; S/ 243,805 y 974 usuarios). Confirmado: son puntos suspendidos |
| Reprogramación | 1 fecha de pago movida (HUANCAYO, 18/09 → 19/09) |
| Columnas | Se quitan 3 de la sección "Preparación y entrega": Categoría, Cod y Días de anticipación |
| Sin cambios | Orden de filas, numeración N° del original (no se renumera) y el resto de los valores |

**Regla: el original no se modifica nunca; todo cambio se hace en las copias.** En el original, 7 de las 10 filas suspendidas tienen en rojo las columnas 4 a 13 (un patrón que no aparece en ninguna fila normal), pero las otras 3 no llevan marca. La suspensión no se puede deducir del original: la indica una persona.

Reglas nuevas: la revisión previa **bloquea** a la agencia sin correo, con correo inválido o fuera del dominio interno; **omite** lo ya enviado o con borrador; y pide decisión si un envío anterior quedó a medias.

## 8. Pendientes

| Pendiente | Estado |
|---|---|
| `python -m pytest` en la PC del banco (Python 3.13.12): 69 pruebas pasan | ✅ 13/10 |
| Correr `tools/humo_datos_reales.py` en el banco con la lista de agencias real | ⏳ |
| `tools/explorar_sharepoint.py` ejecutado en el banco (13/10): estructura y velocidad conocidas, ver §4b | ✅ |
| `--probar-escritura` ejecutado (13/10): crear 936 ms, renombrar 2.691 ms, leer 186 ms, borrar 925 ms | ✅ |
| La monitora también usa la aplicación (v1): ya no se arman envíos a mano. "Marcar como enviado" queda como recurso opcional, no como requisito | ✅ 13/10 |
| El cronograma original se carga arrastrándolo a una zona: no hace falta conocer su carpeta | ✅ 13/10 |
| El respaldo válido de JA es el de `BACKUP_CORREOS` (07/09): la simulación de `ordenar_respaldos.py` lo da por ordenado, sin conflictos con el del 02/09 | ✅ 13/10 |
| Importar la lista de agencias actual (`agencias_correos.xlsx`) a la carpeta compartida la primera vez | ⏳ |
| Cada campaña nueva: la entrega se propone con el nombre `ENTREGA DE FONDOS ETV {código} {año} difusion.xlsx` en la carpeta recordada | ✅ |
| Las suspensiones llegan por correo y hoy se eliminan las filas a mano: la app pide el origen (correo, fecha) de cada cambio | ✅ definido |
| Estructura de carpetas de SharePoint de la campaña (original, entrega, seguimiento, respaldo) | ⏳ |
| `RespaldoRed` lee el formato de v1 en las tres ubicaciones y escribe en `BACKUP_CORREOS` | ✅ F2 |
| `ordenar_respaldos.py` simulado en el banco (13/10): JA 18 ya ordenadas; MA 18 y MJ 18 por copiar; 0 conflictos, 0 duplicadas | ✅ |
| Aplicar `ordenar_respaldos.py --aplicar` (copia 36 carpetas; las de MJ en `BACKUP_CORREOS` existían vacías) | ⏳ |
| Correr `py tools/prueba_outlook.py` (lectura) y luego con `--borrador` y `--enviarme-prueba` en el banco | ⏳ |
| Abrir la interfaz real en el banco (`py main.py`, con `requirements-ui.txt`) y recorrer: tablero, revisión, borrador de prueba, entrega, configuración | ⏳ |
| Empaquetar con PyInstaller (incluir `agente_correos/ui/web`) | ✅ 21/10 (ver instalador más abajo) |
| Velocidad sobre SharePoint: copiar el original a una carpeta temporal antes de leerlo y guardar una caché local del registro | ⏳ |
| Feriados: fuente del calendario (hoy solo sábado y domingo; lista editable en la configuración) | ⏳ |
| Validar en el banco la entrega diferida de Outlook como ventana de anulación | ⏳ F2 |
| Reconstruir el pasado de una campaña en curso (qué se envió con v1): leer Enviados o marcarlo a mano | ⏳ F2 |
| Detección del nombre desde el directorio de Outlook (`GetExchangeUser`): verificar que traiga cargo y anexo | ⏳ F2 |
| Conectar la maqueta v3 a la `Api` y aplicar los cambios de pantalla del contrato | ⏳ F3 |
| Medir el tiempo real del proceso manual y el de la app (las cifras "4–6 h" y "<3 min" son declaradas) | ⏳ |
| **Confirmación de lectura** (`ReadReceiptRequested` de Outlook): casilla en cada envío, valor inicial en Configuración › Jefatura y envío. Implementada y probada con un Outlook simulado; **falta verla funcionar en el banco** | ✅ 21/10 · ⏳ banco |
| **Separar la configuración por equipo de la compartida** (antes todas las rutas, incluida «Entrega vigente» con una ruta como `C:\...\Downloads`, iban al `config.json` compartido y afectaban a todos; la fila «Carpeta compartida» no tenía efecto) | ✅ 21/10 · ⏳ banco |
| Aviso «Hay una entrega más reciente» cuando en las carpetas conocidas aparece la de una campaña posterior a la que se usa | ✅ 21/10 · ⏳ banco |
| Leer los acuses «Leído:» de la bandeja para marcar el aviso como leído en el tablero (la agencia puede rechazar el acuse: no leído ≠ no leyó) | ⏳ |
| Primer uso: panel «Antes de empezar» con carpeta compartida, agencias, entrega, Outlook y firma; «Elegir una entrega…» | ✅ 21/10 · ⏳ banco |
| «Exportar diagnóstico» (zip con log y resumen, sin correos de agencias) en Configuración › Soporte | ✅ 21/10 |
| Instalador `AgenteCorreosBN_<versión>_Setup.exe` (PyInstaller + Inno Setup, sin administrador, en `%LOCALAPPDATA%`): se genera con `v2\installer\construir.ps1` | ✅ 21/10 · ⏳ instalar en el banco |
| Alinear la versión visible: v1 muestra "v8.1" y el historial git llega a "V15" | ⏳ |
| Commitear `DOCUMENTO_MAESTRO_FLUJO_CORREOS.md` e `INFORME_PRESENTACION_EQUIPO.md` | ⏳ |
| **Para la campaña SO 2026**: cargar feriados 8, 9 y 25 de diciembre (cambia el aviso del pago del 10/12: 09/12 → 07/12); confirmar que los 4 correos de la copia fija siguen siendo el área; generar la entrega real con «Preparar entrega» desde `CRONOGRAMA ETV SO 2026 difusion.xlsx`; en el banco: Outlook, carpeta compartida «Accesible», «Enviarme una prueba», una agencia, «Anular envío», el resto. Enviar primero los inicios y, cuando estén en Enviados, los recordatorios | ⏳ 04/11 |
| **Leer el Outlook del usuario en segundo plano** (idea 04/11): revisar la carpeta *Enviados* propia cada pocos minutos para registrar lo que se envió a mano, con v1 o por la monitora desde Outlook, y los acuses «Leído:» de la bandeja. Solo lectura, solo de los correos del programa (asunto de la campaña), sin tocar el resto. Hoy el tablero no ve lo que sale por fuera de la app: un borrador enviado a mano sigue figurando como borrador. Es **requisito previo** del envío automático. Los acuses «Leído:» quedan fuera (el usuario los ve complicados y poco necesarios) | ✅ 04/11 (2.1.0) · ⏳ banco |
| **Envío automático supervisado** (idea 04/11, la persona presente por la mañana): a una hora fija el programa prepara los avisos del día y los envía solo si pasan la revisión sin bloqueos ni advertencias (sin celdas rojas, hilo único, agencia con correo válido), con cuenta regresiva, botón «Cancelar» y la ventana de anulación de siempre; lo dudoso queda para revisión manual. Opcional, apagado por defecto. Exige la app y Outlook abiertos y el equipo sin bloquear. No es el flujo desatendido descartado: ahí no había persona ni revisión. **Plan de prueba:** 05/11 en el equipo del usuario (primero con «Solo dejar borradores», luego enviar; 05/11 cubre los pagos del 06/11: 2 agencias); 06/11 en el equipo de la monitora | ✅ 04/11 (2.1.0) · ⏳ banco |

## 9. Bitácora

| Fecha | Cambio |
|---|---|
| 13/10/2026 | Análisis de v1 (12 hallazgos), decisión de rehacer como v2.0, maquetas v2 y v3 |
| 13/10/2026 | Cambio de decisión: envío con confirmación y firma por usuario. Fase 1 construida: 69 pruebas, paridad con v1 verificada sobre el cronograma real |
| 04/11/2026 | **2.1.0-beta.** Revisión de Enviados en segundo plano y envío automático supervisado (Configuración › Automático), a pedido del usuario: probar el 05/11 en su equipo y el 06/11 en el de la monitora. Nuevo: `servicios/enviados.py` (reconoce avisos enviados por fuera), `ui/vigilancia.py` (hilo, cuenta regresiva, estado), `EnvioService.plan_automatico`, `OutlookGateway.enviados_desde` (solo lectura). El registro se protege con un candado porque ahora escriben varios hilos. 255 pruebas con Outlook simulado; la lectura real de Enviados y el envío automático **no se han probado con Outlook real** |
| 04/11/2026 | Ideas del usuario tras la 2.0.4: que el programa trabaje en segundo plano leyendo el Outlook propio, y saber si podría enviar solo por la mañana cuando él está presente. Quedan como propuestas en §8; no se construye nada hasta validar la campaña en el banco. Registrado el estado de la campaña SO 2026 |
| 04/11/2026 | **2.0.4-beta.** Tabla del correo reordenada (columnas de la ETV y la entrega al frente) y filas por fecha y hora de entrega; comprobado con el cronograma real SO 2026 (Cusco: 77 filas, 05/11 → 03/12). Las pruebas de paridad con v1 comparan ahora el contenido de las filas, no su orden. 222 pruebas |
| 04/11/2026 | **2.0.3-beta.** Copia fija del área (jefe + 3 integrantes) en los correos de inicio: con el cronograma real cada inicio sale con Para 1 y CC 5; borradores propios regenerables; validación de las direcciones al guardar. 215 pruebas. Manual actualizado |
| 04/11/2026 | **2.0.2-beta.** Verificado con el cronograma real SO 2026 (332 filas, 17 agencias, 34 fechas de pago del 05/11 al 21/12; todas las agencias figuran en la lista de correos; sin advertencias de coherencia): los 17 correos de inicio se arman sin errores y la entrega se genera y se vuelve a leer bien. Corregido: el inicio sin registrar sigue pendiente mientras la campaña tenga pagos por avisar (antes dejaba de ofrecerse el botón al pasar la primera fecha de aviso). 204 pruebas. Avisos para la campaña: cargar los feriados 8, 9 y 25 de diciembre (cambia el aviso del pago del 10/12: 09/12 → 07/12); 9 agencias tienen filas sin importe de Pensión 65 (celdas rojas en la tabla) |
| 30/10/2026 | 2.0.1-beta: la interfaz se abre como `file://` para que pywebview no levante su servidor local (commit `e05aeda`) |
| 21/10/2026 | Manual de usuario en Word y PDF (31 páginas, con capturas de datos ficticios): `docs/Manual_de_usuario_Agente_Correos_BN.docx`; se regenera con `docs/manual/capturar.mjs` y `docs/manual/construir_manual.py` |
| 21/10/2026 | Correo de inicio de campaña enviable desde la pantalla, con protección contra doble envío y retiro del respaldo al anular. 203 pruebas · ⏳ probar en el banco antes de la campaña nueva |
| 21/10/2026 | Configuración por equipo separada de la compartida; aviso de entrega más reciente. 196 pruebas |
| 21/10/2026 | Primera prueba del instalador en el banco: abre, usa la carpeta compartida de SharePoint y carga las 20 agencias. Tablero con ventana de 5 fechas y barra |
| 21/10/2026 | **Error corregido:** sin `local.json`, la carpeta compartida resultaba ser la carpeta desde donde se ejecutaba (`Path("")` es `"."`), no `BACKUP_CORREOS\_PROGRAMA`; las pruebas del 13/10 en el banco usaron `v2\` como «compartida». Además, SharePoint y Outlook tienen ahora un tope de espera al abrir (12 s y 10 s): antes la ventana podía quedarse en «Conectando…». 189 pruebas |
| 21/10/2026 | Sin git en el banco: instalador (`v2/installer`), primeros pasos, exportar diagnóstico, confirmación de lectura y aviso de error al arrancar sin consola. 186 pruebas |
| 13/10/2026 | Nodo `Resumen_por_Versiones.md` (aportes por versión, para el resumen a la Gerencia) y pendiente de confirmación de lectura |
| 13/10/2026 | `agencias.json` generado desde el Excel; eliminar agencias; pestañas en Configuración; firma de Outlook por defecto retirada de las opciones. 172 pruebas |
| 13/10/2026 | Importación automática de agencias (una sola escritura), ventana maximizada y explicación de las opciones de firma. 169 pruebas |
| 13/10/2026 | Primeras pruebas en el banco: corregidos el error de `_cfg` al iniciar, la hoja equivocada, la entrega desactualizada, el calendario saturado y los mensajes con nombre de archivo. 166 pruebas |
| 13/10/2026 | Fase 3: Api de pywebview, interfaz conectada (control, preparar entrega, revisión, resultado con anulación, historial, configuración con perfil, rutas y agencias) y `main.py`. 150 pruebas |
| 13/10/2026 | Fase 2: capa de correo completa contra una puerta simulada (hilo exacto, respaldo en 3 ubicaciones, adjunto vigente, reclamo, registro). 131 pruebas |
| 13/10/2026 | Fase 1c: registro por persona con reclamo antes de enviar, agencias editables con historial, configuración y rutas auditadas. 108 pruebas |
| 13/10/2026 | SharePoint explorado (115 archivos, 85 carpetas): tres ubicaciones de respaldo de v1 y velocidad medida; se agrega la conversión de enlace SharePoint a ruta |
| 13/10/2026 | Fase 1b: generación de la entrega desde el original, bitácora y auditoría de entregas manuales. 84 pruebas; contra los archivos reales JA 2026 reproduce la entrega manual salvo dos defectos de ella |
| 13/10/2026 | Validada en el banco (69 pruebas con Python 3.13). Verificados los archivos JA 2026; corregida la regla de coherencia por el desfase de 2 meses entre nombre y fechas (71 pruebas) |
