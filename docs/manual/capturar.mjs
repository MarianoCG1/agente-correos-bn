// Genera las capturas del manual con Edge sin pantalla, SOLO de la ventana del programa (nunca del escritorio).
// Usa la Api de ejemplo (index.html?dev): los datos son ficticios.
//
//   cd agente_correos\ui\web && python -m http.server 8766 --bind 127.0.0.1
//   node docs\manual\capturar.mjs
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const AQUI = path.dirname(fileURLToPath(import.meta.url));
const SALIDA = path.join(AQUI, 'capturas');
const URL = 'http://127.0.0.1:8766/index.html?dev';
const EDGE = ['C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', 'C:/Program Files/Microsoft/Edge/Application/msedge.exe']
  .find(p => fs.existsSync(p));
const PUERTO = 9444;
const dormir = ms => new Promise(r => setTimeout(r, ms));

fs.mkdirSync(SALIDA, { recursive: true });
const perfil = fs.mkdtempSync(path.join(os.tmpdir(), 'edge_manual_'));
const edge = spawn(EDGE, ['--headless=new', `--remote-debugging-port=${PUERTO}`, `--user-data-dir=${perfil}`, '--hide-scrollbars',
  '--no-first-run', '--disable-extensions', 'about:blank'], { stdio: 'ignore' });

async function pagina() {
  for (let i = 0; i < 60; i++) {
    try {
      const lista = await (await fetch(`http://127.0.0.1:${PUERTO}/json`)).json();
      const p = lista.find(x => x.type === 'page');
      if (p) return p;
    } catch { /* aún no arranca */ }
    await dormir(500);
  }
  throw new Error('Edge no respondió');
}

const p = await pagina();
const ws = new WebSocket(p.webSocketDebuggerUrl);
await new Promise(r => ws.addEventListener('open', r));
let n = 0; const espera = new Map();
ws.addEventListener('message', e => { const m = JSON.parse(e.data); if (m.id && espera.has(m.id)) { espera.get(m.id)(m); espera.delete(m.id); } });
const cdp = (method, params = {}) => new Promise(r => { const id = ++n; espera.set(id, r); ws.send(JSON.stringify({ id, method, params })); });
const ev = async js => {
  const r = await cdp('Runtime.evaluate', { expression: js, awaitPromise: true, returnByValue: true });
  if (r.result.exceptionDetails) throw new Error(JSON.stringify(r.result.exceptionDetails).slice(0, 400));
  return r.result.result.value;
};
const foto = async nombre => {
  const r = await cdp('Page.captureScreenshot', { format: 'png' });
  fs.writeFileSync(path.join(SALIDA, nombre + '.png'), Buffer.from(r.result.data, 'base64'));
  console.log('ok', nombre);
};

const MARCAS = `window.__mk = function(items){
  document.querySelectorAll('.__mk').forEach(function(e){e.remove()});
  items.forEach(function(it){
    var el = document.querySelector(it[0]); if (!el) { console.log('sin elemento', it[0]); return; }
    var r = el.getBoundingClientRect(), pos = it[2] || 'tl', x = r.left, y = r.top;
    if (pos === 'tr') x = r.right; if (pos === 'tc') x = (r.left + r.right) / 2; if (pos === 'ml') y = (r.top + r.bottom) / 2;
    if (pos === 'mr') { x = r.right; y = (r.top + r.bottom) / 2; } if (pos === 'bl') y = r.bottom;
    var d = document.createElement('div'); d.className = '__mk'; d.textContent = it[1];
    d.style.cssText = 'position:fixed;z-index:99999;width:26px;height:26px;border-radius:50%;background:#C8102E;color:#fff;font:700 14px Arial;' +
      'display:flex;align-items:center;justify-content:center;box-shadow:0 0 0 3px #fff;left:' + (x - 13 + (it[3] || 0)) + 'px;top:' + (y - 13 + (it[4] || 0)) + 'px';
    document.body.appendChild(d);
  });
}; window.__sinmarcas = function(){document.querySelectorAll('.__mk').forEach(function(e){e.remove()})};`;

async function cargar(url = URL) {
  await cdp('Page.navigate', { url });
  await dormir(1800);
  await ev(MARCAS);
}
const marcar = async items => ev(`__mk(${JSON.stringify(items)})`);
const fotoHasta = async (nombre, jsBottom, margen = 28) => {
  const alto = await ev(`Math.min(window.innerHeight, Math.ceil(${jsBottom}) + ${margen})`);
  const r = await cdp('Page.captureScreenshot', { format: 'png', clip: { x: 0, y: 0, width: await ev('window.innerWidth'), height: alto, scale: 1 } });
  fs.writeFileSync(path.join(SALIDA, nombre + '.png'), Buffer.from(r.result.data, 'base64'));
  console.log('ok', nombre);
};
const BAJO_CFG = "Math.max(...Array.from(document.querySelectorAll('#cfg .card')).map(c => c.getBoundingClientRect().bottom))";
const recorte = async (selector, nombre, margen = 8) => {
  const r = await ev(`(function(){var e = document.querySelector(${JSON.stringify(selector)}).getBoundingClientRect(); return {x:e.left, y:e.top, w:e.width, h:e.height}})()`);
  const clip = { x: Math.max(0, r.x - margen), y: Math.max(0, r.y - margen), width: r.w + margen * 2, height: r.h + margen * 2, scale: 1 };
  const f = await cdp('Page.captureScreenshot', { format: 'png', clip });
  fs.writeFileSync(path.join(SALIDA, nombre + '.png'), Buffer.from(f.result.data, 'base64'));
  console.log('ok', nombre);
};
const esperar = (ms = 900) => dormir(ms);

await cdp('Page.enable');
await cdp('Emulation.setDeviceMetricsOverride', { width: 1240, height: 800, deviceScaleFactor: 1.5, mobile: false });

// ---- 1. Primer uso: equipo sin entrega ni agencias
await cargar();
await ev(`(function(){
  var f = window.__apiFalsa, orig = f.iniciar;
  f.iniciar = function(){ return Promise.resolve(orig()).then(function(r){ var d = r.datos; d.hay_entrega = false; d.entrega_archivo = ''; d.agencias_n = 0; d.hay_agencias = false; d.perfil_completo = false; d.compartida_ok = false; return r; }); };
  f.estado_campana = function(){ return {ok:false, error:'No se encontró la entrega vigente. Genérela en «Preparar entrega» o indíquela en Configuración › Rutas.'} };
})()`);
await ev(`recargarCampana(true)`); await esperar(1200);
await marcar([['.paso:nth-child(4)', 1, 'tl', 6, 10], ['.paso:nth-child(5)', 2, 'tl', 6, 10], ['.paso:nth-child(6)', 3, 'tl', 6, 10],
  ['.paso:nth-child(7)', 4, 'tl', 6, 10], ['.paso:nth-child(8)', 5, 'tl', 6, 10]]);
await fotoHasta('01_primeros_pasos', "document.querySelector('.primeros').getBoundingClientRect().bottom");

// ---- 2. Tablero
await cargar(); await esperar(1000);
await marcar([['#nav', 1, 'tr', -10, 8], ['#hoy', 2, 'tl', 4, 4], ['#camp', 3, 'tl', 4, 4], ['#seg', 4, 'tl', 0, 0], ['#f-etv', 5, 'tl', 0, 0],
  ['#vent', 6, 'tl', 0, 0], ['#matriz', 7, 'tl', 8, 8], ['#leyenda', 8, 'tl', 0, 0], ['#v-control .fila button', 9, 'tl', 0, 0], ['#btn-inicio', 10, 'tl', 0, 0], ['#btn-avisos', 11, 'tl', 0, 0]]);
await foto('02_tablero');
await ev(`__sinmarcas()`);
await recorte('#leyenda', '23_leyenda');
await recorte('#vent', '24_navegacion_fechas');
await recorte('#hoy', '25_panel_hoy');

// ---- 3. Detalle de una agencia
await ev(`__sinmarcas(); elegir(AG.findIndex(function(a){return a.n === 'CUSCO'}), HOY)`); await esperar(800);
await marcar([['#det', 1, 'tl', 18, 26]]);
await foto('03_detalle');
await ev(`__sinmarcas(); cerrarDetalle()`); await esperar(500);

// ---- 4. Revisión previa
await ev(`abrirRevision()`); await esperar(1800);
await marcar([['.pasos', 1, 'tl', -6, -6], ['#rev-tabla', 2, 'tl', 8, 8], ['#rev-mail', 3, 'tl', 8, 8], ['#btn-prueba', 4, 'tl', 0, 0],
  ['#btn-borr', 5, 'tl', 0, 0], ['#btn-env', 6, 'tl', 0, 0]]);
await foto('04_revision');

// 4b. Una agencia con dos hilos posibles
await ev(`__sinmarcas(); verFila(REV.filas.findIndex(function(f){return f.agencia === 'HUANCAYO'}))`); await esperar(1000);
await foto('05_revision_hilos');

// ---- 5. Confirmación
await ev(`confirmar('enviar')`); await esperar(500);
await marcar([['#m-lectura', 1, 'tl', -6, -4], ['#dlg .aviso', 2, 'tl', -6, -4]]);
await foto('06_confirmar');
await ev(`__sinmarcas(); $('dlg-b1').click()`); await esperar(6500);
await marcar([['#res-anular', 1, 'tl', 4, 4], ['#res-kpis', 2, 'tl', 4, 4], ['#res-tabla', 3, 'tl', 8, 8]]);
await foto('07_resultado');

// ---- 5b. Correo de inicio de campaña
await ev(`__sinmarcas(); ir('control')`); await esperar(700);
await marcar([['#btn-inicio', 1, 'tl', 0, 0], ['#btn-avisos', 2, 'tl', 0, 0]]);
await foto('21_tablero_inicio');
await ev(`__sinmarcas(); abrirRevision('inicio')`); await esperar(1500);
await ev(`verFila(REV.filas.findIndex(function(f){return f.agencia === 'IQUITOS'}))`); await esperar(900);
await marcar([['#rev-tabla', 1, 'tl', 8, 8], ['#rev-mail', 2, 'tl', 8, 8], ['#btn-env', 3, 'tl', 0, 0]]);
await foto('22_inicio_revision');

// ---- 6. Preparar entrega
await ev(`__sinmarcas(); ir('entrega')`); await esperar(600);
await marcar([['#drop', 1, 'tl', 6, 6]]);
await fotoHasta('08_entrega_arrastrar', "document.querySelector('#drop').getBoundingClientRect().bottom");
await ev(`__sinmarcas(); api('entrega_subir_original', 'CRONOGRAMA ETV JA 2026 difusion.xlsx', '').then(entCargado)`); await esperar(1000);
await marcar([['#ent-resumen', 1, 'tl', 4, 4], ['#ent-puntos', 2, 'tl', 8, 8], ['.ent-lado', 3, 'tl', 4, 4], ['#ent-generar', 4, 'tl', 0, 0]]);
await foto('09_entrega_suspendidos');
await ev(`__sinmarcas(); reprogramar(ENT.d.puntos.filter(function(p){return !p.sugerido})[0].clave)`); await esperar(600);
await recorte('#dlg', '10_entrega_reprogramar', 24);
await ev(`$('dlg-b1').click()`); await esperar(500);
await ev(`entListo({destino:'//…/ENTREGA DE FONDOS/ENTREGA DE FONDOS ETV JA 2026 difusion.xlsx', filas_entrega:310, filas_quitadas:10, columnas_quitadas:['Categoría','Cod','Días de anticipación']})`);
await esperar(500);
await fotoHasta('11_entrega_lista', "document.querySelector('#ent-3 .card').getBoundingClientRect().bottom");

// ---- 7. Historial
await ev(`ir('historial')`); await esperar(1000);
await marcar([['#h-ag', 1, 'tl', 0, 0], ['#h-res', 2, 'tl', 0, 0], ['#h-q', 3, 'tl', 0, 0], ['#hist-tabla', 4, 'tl', 8, 8]]);
await fotoHasta('12_historial', "document.querySelector('#hist-tabla table').getBoundingClientRect().bottom");

// ---- 8. Configuración
const CFG = [['agencias', '13_config_agencias', [['#cfg-tabs', 1, 'tl', -8, -8], ['#cfg .btn.pri', 2, 'tl', 0, 0], ['#cfg table', 3, 'tl', 8, 8]]],
  ['perfil', '14_config_perfil', [['#p-nombre', 1, 'tl', -8, 4], ['#p-modo', 2, 'tl', -8, 4], ['#p-prev', 3, 'tl', 4, 4], ['#cfg .btn.pri:last-of-type', 4, 'tl', 0, 0]]],
  ['general', '15_config_general', [['#c-jefe', 1, 'tl', -8, 4], ['#c-excl', 2, 'tl', 0, 0], ['#c-copia', 3, 'tl', 0, 0], ['#c-min', 4, 'tl', -8, 4], ['#c-lec', 5, 'tl', -10, -2], ['#c-fer', 6, 'tl', -8, 4]]],
  ['rutas', '16_config_rutas', [['.rt:nth-of-type(1)', 1, 'tl', -22, 4], ['.rt:nth-of-type(2)', 2, 'tl', -22, 4], ['.rt:nth-of-type(3)', 3, 'tl', -22, 4],
    ['.rt:nth-of-type(4)', 4, 'tl', -22, 4], ['.rt:nth-of-type(5)', 5, 'tl', -22, 4], ['.rt:nth-of-type(6)', 6, 'tl', -22, 4]]],
  ['cambios', '17_config_cambios', []],
  ['soporte', '18_config_soporte', [['#cfg .btn.pri', 1, 'tl', 0, 0]]]];
for (const [tab, nombre, marcas] of CFG) {
  await ev(`__sinmarcas(); irConfig('${tab}')`); await esperar(1100);
  if (tab === 'perfil') await cdp('Emulation.setDeviceMetricsOverride', { width: 1240, height: 1150, deviceScaleFactor: 1.5, mobile: false });
  if (marcas.length) await marcar(marcas);
  if (tab === 'perfil') await foto(nombre); else await fotoHasta(nombre, BAJO_CFG);
  if (tab === 'perfil') await cdp('Emulation.setDeviceMetricsOverride', { width: 1240, height: 800, deviceScaleFactor: 1.5, mobile: false });
}
await ev(`__sinmarcas(); irConfig('agencias')`); await esperar(900);
await ev(`editarAgencia('CUSCO')`); await esperar(600);
await recorte('#dlg', '19_agencia_editar', 24);
await ev(`cerrarModal()`);

// ---- 9. Entrega más reciente
await cargar(); await esperar(800);
await ev(`(function(){ var f = window.__apiFalsa, orig = f.estado_campana;
  f.estado_campana = function(){ return Promise.resolve(orig()).then(function(r){ r.datos.entrega_nueva = {archivo:'ENTREGA DE FONDOS ETV SO 2026 difusion.xlsx', ruta:'x'}; return r; }); }; })()`);
await ev(`recargarCampana(true)`); await esperar(1200);
await marcar([['#c-aviso .aviso', 1, 'tl', -4, -4]]);
await foto('20_entrega_nueva');

ws.close(); edge.kill();
try { fs.rmSync(perfil, { recursive: true, force: true }); } catch { /* ignorar */ }
process.exit(0);
