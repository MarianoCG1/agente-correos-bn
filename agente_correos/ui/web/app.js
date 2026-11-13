'use strict';
/* Agente de Correos BN v2.0 · interfaz.
   Toda regla vive en Python (agente_correos/ui/api.py). Aquí solo se pinta lo que llega y se
   pasan al programa las decisiones de la persona. */

// ---------- Íconos (línea, 1.5 px) ----------
var ICO = {
  tablero:'<rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/><rect x="4" y="13" width="7" height="7" rx="1.5"/><rect x="13" y="13" width="7" height="7" rx="1.5"/>',
  reloj:'<circle cx="12" cy="12" r="8"/><path d="M12 8v4l3 2"/>',
  ajustes:'<path d="M4 7h9M19 7h1M4 17h1M11 17h9"/><circle cx="16" cy="7" r="2.5"/><circle cx="8" cy="17" r="2.5"/>',
  check:'<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  doc:'<path d="M7 3.5h7l4 4V20.5H7z"/><path d="M14 3.5v4h4"/>',
  correo:'<rect x="3" y="6" width="18" height="12" rx="2"/><path d="M3.5 8l8.5 6 8.5-6"/>',
  saltar:'<path d="M6 6l8 6-8 6z"/><path d="M18 6v12"/>',
  candado:'<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
  alerta:'<path d="M12 4.5l8.5 15h-17z"/><path d="M12 10.5v4M12 17v.3"/>',
  buscar:'<circle cx="11" cy="11" r="6"/><path d="M20 20l-4.5-4.5"/>',
  x:'<path d="M6 6l12 12M18 6L6 18"/>',
  atras:'<path d="M14.5 6l-6 6 6 6"/>',
  seguro:'<path d="M12 3.5l7 3v5c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9v-5z"/><path d="M9 12l2.2 2.2L15 10.5"/>',
  subir:'<path d="M12 16V5"/><path d="M7.5 9.5L12 5l4.5 4.5"/><path d="M5 19h14"/>',
  persona:'<circle cx="12" cy="8" r="3.5"/><path d="M5 20c1-4 4-6 7-6s6 2 7 6"/>'
};
function ico(n){return '<svg class="i" viewBox="0 0 24 24" aria-hidden="true">' + (ICO[n] || '') + '</svg>'}

var EST = {
  env:  {t:'Enviado',                i:'check'},
  borr: {t:'Borrador generado',      i:'doc'},
  hoy:  {t:'Pendiente de hoy',       i:'correo'},
  pend: {t:'Pendiente',              i:null},
  omit: {t:'Omitido',                i:'saltar'},
  bloq: {t:'Bloqueado',              i:'candado'},
  dec:  {t:'Requiere decisión',      i:'alerta'},
  venc: {t:'Vencido, sin registro',  i:'reloj'}
};

// ---------- Estado de la pantalla ----------
var E = null, FECHAS = [], AG = [], HOY = -1;
var sel = null, filtro = 'todas', vista = 'control', VENT = 5, VENT_I = null;
var REV = null, LOTE = null, ENT = null, CFG = null, PERFIL = null, AGS = null, CFG_TAB = 'agencias';
var SESION = {nombre: '', hoy_largo: '', minutos: 2}, ENTREGA_NUEVA = '', AUTO = null;

// ---------- Utilidades ----------
function $(id){return document.getElementById(id)}
function esc(s){return String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')}
function plural(n, s, p){return n + ' ' + (n === 1 ? s : p)}
function pil(e){return '<span class="p s-' + e + '">' + (EST[e].i ? ico(EST[e].i) : '') + '</span>'}
function chip(e, txt){return '<span class="chip s-' + e + '">' + (EST[e].i ? ico(EST[e].i) : '') + esc(txt || EST[e].t) + '</span>'}
function corta(iso){return iso ? iso.slice(8, 10) + '/' + iso.slice(5, 7) : ''}
var tt;
function toast(m){var t = $('toast'); t.innerHTML = ico('check') + esc(m); t.classList.add('on'); clearTimeout(tt); tt = setTimeout(function(){t.classList.remove('on')}, 3200)}

/* Llama a un método de Python. Devuelve los datos o lanza Error con el mensaje para la persona. */
function api(nombre){
  var args = Array.prototype.slice.call(arguments, 1);
  var puente = (window.pywebview && window.pywebview.api) || window.__apiFalsa;
  if (!puente || !puente[nombre]) return Promise.reject(new Error('El programa no está disponible (' + nombre + ').'));
  return Promise.resolve(puente[nombre].apply(puente, args)).then(function(r){
    if (!r || r.ok !== true) throw new Error((r && r.error) || 'No se pudo completar la operación.');
    return r.datos;
  });
}
function falla(e){toast(e && e.message ? e.message : String(e))}

// ---------- Navegación ----------
function ir(v){
  vista = v;
  ['control','entrega','revision','resultado','historial','config'].forEach(function(x){$('v-' + x).classList.toggle('on', x === v)});
  if (v !== 'control') sel = null;
  pintarNav();
  if (v === 'control'){pintarControl()} else {$('main').classList.remove('open')}
  if (v === 'historial') cargarHistorial();
  if (v === 'config') cargarConfig();
  if (v === 'entrega') entReiniciar();
}
function pintarNav(){
  var act = {revision:'control', resultado:'control'}[vista] || vista;
  var n = AG.filter(function(a){return a.est[HOY] === 'hoy'}).length;
  $('nav').innerHTML = [['control','tablero','Control'],['entrega','subir','Preparar entrega'],
                        ['historial','reloj','Historial'],['config','ajustes','Configuración']].map(function(x){
    return '<button class="' + (act === x[0] ? 'on' : '') + '" onclick="ir(\'' + x[0] + '\')">' + ico(x[1]) + x[2] +
      (x[0] === 'control' && n ? '<span class="cta" title="Pendientes de hoy">' + n + '</span>' : '') + '</button>';
  }).join('');
}

// ---------- Modal ----------
function modal(titulo, cuerpo, botones, ancho){
  var b = (botones || []).map(function(x, i){
    return '<button class="btn' + (x.pri ? ' pri' : '') + '" id="dlg-b' + i + '">' + esc(x.t) + '</button>';
  }).join('');
  $('dlg').style.width = (ancho || 520) + 'px';
  $('dlg').innerHTML = '<div class="dlg-t"><div class="grow"><h2>' + esc(titulo) + '</h2></div>' +
    '<button class="btn liso ico" aria-label="Cerrar" onclick="cerrarModal()">' + ico('x') + '</button></div>' +
    '<div class="dlg-c">' + cuerpo + '</div><div class="dlg-f"><span class="sec grow" id="dlg-pie"></span>' + b + '</div>';
  (botones || []).forEach(function(x, i){$('dlg-b' + i).onclick = x.f});
  $('velo').classList.add('on');
}
function cerrarModal(){$('velo').classList.remove('on')}
document.addEventListener('keydown', function(e){
  if (e.key !== 'Escape') return;
  if ($('velo').classList.contains('on')) cerrarModal(); else if (sel) cerrarDetalle();
});

// =====================================================================
// 1. CONTROL
// =====================================================================
function adaptar(e){
  E = e;
  FECHAS = [{d:'Campaña', dia:'', largo:'inicio de campaña', aviso:'', iso:'inicio'}].concat(e.fechas.map(function(f){
    return {d:f.d, dia:f.dia, largo:f.largo, aviso:corta(f.aviso), avisoIso:f.aviso, iso:f.fecha};
  }));
  HOY = e.objetivo ? 1 + e.fechas.findIndex(function(f){return f.fecha === e.objetivo}) : -1;
  AG = e.agencias.map(function(a){
    var o = {n:a.nombre, etv:a.etvs.join(' / ') || '—', est:{}, mot:{}, pagos:[], mail:a.para.join('; '),
             cc:a.cc.join('; '), sinCorreo:a.sin_correo, motivoBloqueo:a.motivo_bloqueo};
    FECHAS.forEach(function(x, f){
      var c = a.celdas[x.iso];
      if (c){o.est[f] = c.estado; o.mot[f] = c.motivo; if (f > 0) o.pagos.push(f)}
    });
    return o;
  });
}
function conProblema(a){return a.sinCorreo || a.est[HOY] === 'dec'}

function recargarCampana(refrescar){
  return api('estado_campana', !!refrescar).then(function(e){
    adaptar(e);
    ENTREGA_NUEVA = e.entrega_nueva ? e.entrega_nueva.ruta : '';
    $('v-control').classList.remove('vacia');
    $('c-titulo').textContent = 'Control de campaña · ' + e.campana;
    $('c-sub').textContent = 'Pensión 65 · Juntos · Contigo · ' + e.archivo + (e.hoja ? ' · hoja ' + e.hoja : '');
    VENT_I = null;
    $('c-aviso').innerHTML =
      (!e.hay_agencias ? '<div class="aviso dec" style="margin-bottom:8px">' + ico('alerta') + '<div class="grow"><b>Faltan los correos de las agencias</b>' +
        'Sin ellos ningún aviso se puede preparar. Cargue la lista que usaba la versión anterior o agréguelas una por una en Configuración.</div>' +
        '<button class="btn" onclick="importarAgencias()">Importar lista de agencias…</button></div>' : '') +
      (e.entrega_nueva ? '<div class="aviso dec" style="margin-bottom:8px">' + ico('alerta') + '<div class="grow"><b>Hay una entrega más reciente</b>' +
        esc(e.entrega_nueva.archivo) + '. Ahora está usando ' + esc(e.archivo) + '.</div>' +
        '<button class="btn pri" onclick="cambiarEntrega()">Usar esa entrega</button></div>' : '') +
      (e.coherencia ? '<div class="aviso dec">' + ico('alerta') + '<div><b>Revise el archivo</b>' + esc(e.coherencia) + '</div></div>' : '');
    if (vista === 'control') pintarControl(); else pintarNav();
  }).catch(function(e){
    AG = []; FECHAS = []; HOY = -1; E = null;
    $('c-titulo').textContent = 'Control de campaña';
    $('c-sub').textContent = 'Primeros pasos';
    $('v-control').classList.add('vacia');
    $('hoy').innerHTML = $('camp').innerHTML = $('seg').innerHTML = $('matriz').innerHTML = $('leyenda').innerHTML = '';
    primerosPasos(e.message);
    pintarNav();
  });
}

// ---- Primer uso: lo que falta para ver la campaña ----
function paso(ok, titulo, detalle, botones){
  return '<div class="paso' + (ok ? ' ok' : '') + '"><span class="pm">' + ico(ok ? 'check' : 'alerta') + '</span>' +
    '<div class="grow"><b>' + titulo + '</b><div class="sec">' + detalle + '</div></div>' +
    '<div class="fila" style="gap:8px">' + (botones || '') + '</div></div>';
}
function irConfig(tab){CFG_TAB = tab; ir('config')}
function primerosPasos(motivo){
  api('iniciar').then(function(s){
    var b = function(t, f, pri){return '<button class="btn' + (pri ? ' pri' : '') + '" onclick="' + f + '">' + t + '</button>'};
    $('c-aviso').innerHTML = '<div class="card primeros"><div class="rot">Antes de empezar</div>' +
      '<h2>Revise estos pasos para ver su campaña</h2>' +
      '<p class="sec" style="margin:2px 0 8px">Esto es lo que el programa encontró en este equipo. Cuando todo esté en orden, el tablero aparece solo.</p>' +
      paso(s.compartida_ok, 'Carpeta compartida',
        s.compartida_ok ? esc(s.compartida) : 'No se pudo abrir la carpeta compartida de SharePoint. Por ahora el programa usa una carpeta local de este equipo y solo podrá crear borradores.',
        s.compartida_ok ? '' : b('Revisar rutas', 'irConfig(\'rutas\')')) +
      paso(s.agencias_n > 0, 'Agencias y correos',
        s.agencias_n > 0 ? plural(s.agencias_n, 'agencia cargada', 'agencias cargadas') + '.' :
          'Todavía no hay agencias. Sin sus correos no se puede preparar ningún aviso.',
        s.agencias_n > 0 ? b('Ver agencias', 'irConfig(\'agencias\')') :
          b('Importar lista…', 'importarAgencias()', true) + b('Agregar a mano', 'irConfig(\'agencias\')')) +
      paso(false, 'Campaña (entrega vigente)',
        s.red_lenta ? esc(motivo) :
        s.hay_entrega ? 'No se pudo leer «' + esc(s.entrega_archivo) + '»: ' + esc(motivo) :
          'No se encontró ninguna entrega en las carpetas conocidas. Elija una que ya exista o prepárela desde el cronograma original.',
        b('Elegir una entrega…', 'usarEntregaExistente()', true) + b('Preparar desde el original', 'ir(\'entrega\')')) +
      paso(s.outlook, 'Outlook', s.outlook ? 'Conectado.' : s.outlook_lento ? 'Outlook no respondió. Revise si tiene una ventana esperando una respuesta y pulse «Actualizar».' : 'No se pudo conectar. Abra Outlook y pulse «Actualizar».', '') +
      paso(s.perfil_completo, 'Mi firma', s.perfil_completo ? 'Perfil completo.' : 'Complete su nombre y cargo para que los correos salgan con su firma.',
        s.perfil_completo ? '' : b('Completar mi perfil', 'irConfig(\'perfil\')')) +
      '</div>';
  }).catch(function(e){$('c-aviso').innerHTML = '<div class="aviso dec">' + ico('alerta') + '<div>' + esc(motivo || e.message) + '</div></div>'});
}
function cambiarEntrega(){
  if (!ENTREGA_NUEVA) return;
  api('entrega_cambiar', ENTREGA_NUEVA).then(function(r){
    toast('Ahora usa ' + r.archivo);
    recargarCampana(true);
  }).catch(falla);
}
function usarEntregaExistente(){
  api('entrega_usar_existente').then(function(r){
    if (r.cancelado) return;
    toast('Entrega elegida: ' + r.archivo);
    recargarCampana(true);
  }).catch(falla);
}
function exportarDiagnostico(){
  api('diagnostico_exportar').then(function(r){
    if (!r.cancelado) toast('Diagnóstico guardado en ' + r.ruta);
  }).catch(falla);
}

function pintarControl(){
  if (!E){return}
  var k = {prog:0, borr:0, env:0, venc:0}, man = {tot:0, listas:0, dec:0, bloq:0, borr:0, env:0};
  AG.forEach(function(a){
    for (var f in a.est){k.prog++; if (a.est[f] === 'borr') k.borr++; if (a.est[f] === 'env') k.env++; if (a.est[f] === 'venc') k.venc++}
    if (HOY in a.est){
      man.tot++;
      var e = a.est[HOY];
      if (e === 'hoy') man.listas++; else if (e === 'dec') man.dec++; else if (e === 'bloq') man.bloq++;
      else if (e === 'borr') man.borr++; else if (e === 'env') man.env++;
    }
  });
  var falta = man.listas + man.dec;
  var ni = AG.filter(function(a){return a.est[0] === 'hoy'}).length;          // agencias con el correo de inicio por preparar
  var nb = AG.filter(function(a){return a.est[0] === 'borr'}).length;         // inicios que solo están en borrador
  var rot = E.objetivo ? 'Hoy, ' + E.hoy_largo + ' · pago del ' + E.objetivo_largo : 'Hoy, ' + E.hoy_largo;
  var titulo = !E.hay_agencias ? 'Primero cargue los correos de las agencias'
    : ni && !falta ? plural(ni, 'agencia espera', 'agencias esperan') + ' su correo de inicio de campaña'
    : !E.objetivo ? 'No quedan pagos por avisar en esta campaña'
    : falta ? plural(man.tot, 'agencia recibe', 'agencias reciben') + ' fondos el ' + E.objetivo_largo.split(' ').slice(0, 1) + ' ' + E.objetivo_largo.split(' ')[1]
    : 'Los avisos del ' + E.objetivo_largo + ' ya están atendidos';
  $('hoy').innerHTML = '<div class="grow"><div class="rot">' + esc(rot) + '</div><h2>' + esc(titulo) + '</h2><div class="resumen">' +
    (man.listas ? '<span class="chip neutro"><b>' + man.listas + '</b>&nbsp;' + (man.listas === 1 ? 'lista' : 'listas') + '</span>' : '') +
    (man.dec ? chip('dec', plural(man.dec, 'requiere', 'requieren') + ' decisión') : '') +
    (man.bloq ? chip('bloq', plural(man.bloq, 'bloqueada', 'bloqueadas')) : '') +
    (man.borr ? chip('borr', man.borr + ' con borrador') : '') +
    (man.env ? chip('env', man.env + ' enviadas') : '') +
    (ni ? '<span class="chip neutro"><b>' + ni + '</b>&nbsp;por iniciar</span>' : '') +
    '</div></div><div style="display:flex;flex-direction:column;gap:8px">' +
    (ni ? '<button class="btn ' + (falta ? '' : 'pri') + '" id="btn-inicio" onclick="abrirRevision(\'inicio\')">Correos de inicio (' + ni + ')</button>'
        : nb ? '<button class="btn" id="btn-inicio" onclick="abrirRevision(\'inicio\')" title="Vuelva a generar un borrador que haya descartado">Inicios en borrador (' + nb + ')</button>' : '') +
    (E.objetivo ? '<button class="btn pri" id="btn-avisos" onclick="abrirRevision()"' + ((falta || man.borr) ? '' : ' disabled') +
    '>Preparar avisos del ' + esc(E.objetivo_largo.split(' ')[1]) + '</button>' : '') + '</div>';

  var pct = k.prog ? Math.round(k.env / k.prog * 100) : 0;
  $('camp').innerHTML = '<div><div class="fila"><span class="rot grow">Avance de la campaña</span><b style="color:var(--tinta)">' + pct + ' %</b></div>' +
    '<div class="barra"><i style="width:' + pct + '%"></i></div></div><div class="cifras">' +
    cif(AG.length, 'Agencias') + cif(k.prog, 'Avisos') + cif(k.env, 'Enviados') + cif(k.borr, 'Borradores') + '</div>';

  var nh = AG.filter(function(a){return a.est[HOY] === 'hoy'}).length, np = AG.filter(conProblema).length;
  $('seg').innerHTML = seg('todas', 'Todas', AG.length, '') + seg('hoy', 'Pendientes de hoy', nh, 'r') + seg('prob', 'Con problema', np, 'n');
  pintarNav(); pintarMatriz();
}
function cif(n, t){return '<div><b>' + n + '</b><span>' + t + '</span></div>'}
function seg(id, t, n, c){return '<button class="' + (filtro === id ? 'on' : '') + '" onclick="filtro=\'' + id + '\';pintarControl()">' + t + '<em class="' + (n ? c : '') + '">' + n + '</em></button>'}

function pintarMatriz(){
  var fe = $('f-etv').value, q = $('f-q').value.trim().toUpperCase();
  var cols = columnasVisibles();
  var h = '<table class="mx"><colgroup><col class="c1">' + cols.map(function(){return '<col class="cd">'}).join('') +
    '</colgroup><thead><tr><th><span class="rot">Agencia</span></th>';
  cols.forEach(function(f){
    var x = FECHAS[f];
    var cab = f === 0 ? 'INICIO' : f === HOY ? 'HOY · ' + x.dia : x.dia;
    h += '<th class="' + clasesCol(f) + '"><small>' + cab + '</small><b>' + esc(x.d) + '</b></th>';
  });
  h += '</tr></thead><tbody>';
  var n = 0;
  AG.forEach(function(a, i){
    if (filtro === 'hoy' && a.est[HOY] !== 'hoy') return;
    if (filtro === 'prob' && !conProblema(a)) return;
    if (fe && a.etv.indexOf(fe) < 0) return;
    if (q && a.n.toUpperCase().indexOf(q) < 0) return;
    n++;
    var tot = Object.keys(a.est).length, env = Object.keys(a.est).filter(function(f){return a.est[f] === 'env'}).length;
    h += '<tr class="' + (sel && sel.a === i ? 'sel' : '') + '"><td><button class="ag" onclick="elegir(' + i + ',null)"><b>' + esc(a.n) + '</b><span>' + esc(a.etv) +
      '</span><i title="Avisos enviados">' + env + '/' + tot + '</i></button></td>';
    cols.forEach(function(f){
      var x = FECHAS[f];
      h += '<td class="' + clasesCol(f) + '">';
      if (f in a.est){
        var e = a.est[f], tip = EST[e].t + ' · ' + a.mot[f];
        h += '<button class="cel' + (sel && sel.a === i && sel.f === f ? ' sel' : '') + '" title="' + esc(tip) + '" aria-label="' + esc(a.n + ', ' + x.d + ': ' + tip) +
          '" onclick="elegir(' + i + ',' + f + ')">' + pil(e) + '</button>';
      }
      h += '</td>';
    });
    h += '</tr>';
  });
  h += '</tbody></table>';
  if (!n) h += '<div class="vacio"><b style="color:var(--tinta)">Ninguna agencia coincide.</b><br>Cambie los filtros o borre la búsqueda.</div>';
  $('matriz').innerHTML = h;
  pintarVentana();
  $('leyenda').innerHTML = ['env','borr','hoy','dec','bloq','omit','venc','pend'].map(function(e){
    return '<span>' + pil(e) + (e === 'pend' ? 'Pendiente futuro' : e === 'venc' ? 'Vencido: sin registro' : EST[e].t) + '</span>';
  }).join('') + '<span>Vacío: sin pago</span>';
  pintarDetalle();
}
// La tabla muestra el inicio y como máximo VENT fechas; la persona las recorre con la barra o las flechas.
function ventanaMax(){return Math.max(1, FECHAS.length - VENT)}          // primera fecha posible de la última ventana
function inicioVentana(){
  if (VENT_I === null){                                                    // al abrir: un día pasado, hoy y los siguientes
    VENT_I = HOY > 0 ? HOY - 1 : ventanaMax();
  }
  VENT_I = Math.max(1, Math.min(VENT_I, ventanaMax()));
  return VENT_I;
}
function columnasVisibles(){
  var cols = [0];
  if (!E) return cols;
  var ini = inicioVentana();
  for (var f = ini; f < Math.min(FECHAS.length, ini + VENT); f++) cols.push(f);
  return cols;
}
function ponerVentana(i){VENT_I = i; pintarMatriz()}
function moverVentana(d){ponerVentana(inicioVentana() + d)}
function irAHoy(){ponerVentana(HOY > 0 ? Math.max(1, HOY - 1) : ventanaMax())}
function vencidos(){                                                       // fechas de pago con avisos sin registrar, ya pasadas
  var por = {};
  AG.forEach(function(a){Object.keys(a.est).forEach(function(f){
    if (+f > 0 && a.est[f] === 'venc') por[f] = (por[f] || 0) + 1;
  })});
  return por;
}
function irAVencidos(){
  var fs = Object.keys(vencidos()).map(Number).sort(function(a, b){return a - b});
  if (fs.length) ponerVentana(fs[0]);
}
function pintarVentana(){
  var total = FECHAS.length - 1, ini = inicioVentana(), fin = Math.min(total, ini + VENT - 1);
  $('v-barra').max = ventanaMax(); $('v-barra').value = ini;
  $('v-ant').disabled = ini <= 1; $('v-sig').disabled = ini >= ventanaMax();
  $('v-rango').textContent = total ? 'Fechas ' + ini + '–' + fin + ' de ' + total : '';
  $('vent').style.display = total > VENT ? '' : 'none';
  var venc = vencidos(), n = Object.keys(venc).length;
  $('v-venc').style.display = n ? '' : 'none';
  $('v-venc').textContent = 'Sin registrar (' + plural(n, 'fecha', 'fechas') + ')';
  $('v-venc').title = 'Fechas de pago ya pasadas con avisos sin registro: lleva a la más antigua';
}
function clasesCol(f){
  var x = FECHAS[f], c = [];
  if (f === HOY) c.push('dia-hoy');
  if (x.dia === 'SÁB' || x.dia === 'DOM') c.push('fin');
  if (x.dia === 'LUN') c.push('sem');
  if (f > 0 && E && x.avisoIso && x.avisoIso < E.hoy) c.push('pas');
  return c.join(' ');
}
function elegir(a, f){sel = {a:a, f:f}; pintarMatriz()}
function cerrarDetalle(){sel = null; pintarMatriz()}

function pintarDetalle(){
  $('main').classList.toggle('open', !!sel && vista === 'control');
  if (!sel) return;
  var a = AG[sel.a], i = sel.a;
  var f = sel.f === null ? (HOY in a.est ? HOY : 0) : sel.f;
  var cab = HOY in a.est ? chip(a.est[HOY]) : '<span class="chip s-pend">Sin pago próximo</span>';
  var h = '<div class="det-h"><div class="fila"><div class="grow"><h2 style="font-size:18px">' + esc(a.n) + '</h2><div class="sec">ETV ' + esc(a.etv) +
    ' · ' + plural(a.pagos.length, 'fecha', 'fechas') + ' de pago</div></div>' +
    '<button class="btn liso ico" aria-label="Cerrar detalle" onclick="cerrarDetalle()">' + ico('x') + '</button></div><div style="margin-top:10px">' + cab + '</div></div><div class="det-b">';

  if (a.sinCorreo)
    h += '<div class="aviso bloq">' + ico('candado') + '<div><b>Bloqueado: ' + esc(a.motivoBloqueo.toLowerCase()) + '</b>No se pueden generar avisos para esta agencia. ' +
      'Corrija sus correos en Configuración › Agencias.</div></div>';

  h += '<div><div class="rot">Línea de tiempo</div><div class="tl">';
  [0].concat(a.pagos).forEach(function(x){
    h += '<button class="' + (x === f ? 'cur' : '') + '" onclick="elegir(' + i + ',' + x + ')">' + pil(a.est[x]) +
      '<span><b>' + (x === 0 ? 'Inicio de campaña' : 'Recordatorio · pago ' + esc(FECHAS[x].d)) + '</b><small>' + EST[a.est[x]].t + '</small></span><em>' +
      (x === 0 ? '' : 'aviso ' + esc(FECHAS[x].aviso)) + '</em></button>';
  });
  h += '</div><div class="sec" style="margin-top:8px">' + esc(a.mot[f] || '') + '.</div></div>';

  h += '<div><div class="rot">Destinatarios</div><dl class="kv">';
  if (a.sinCorreo) h += '<dt>Para</dt><dd style="color:var(--gris)">Sin correo válido</dd>';
  else h += '<dt>Para</dt><dd>' + esc(a.mail) + '</dd><dt>CC</dt><dd>' + esc(a.cc || '—') + '</dd>';
  h += '</dl></div></div><div class="det-f"><button class="btn grow" ' + (a.sinCorreo || f === 0 ? 'disabled' : '') +
    ' onclick="verCorreo(' + i + ',' + f + ')">' + ico('correo') + 'Ver correo</button></div>';
  $('det').innerHTML = h;
}

function verCorreo(i, f){
  var a = AG[i];
  modal(a.n + ' · Recordatorio del pago ' + FECHAS[f].d, '<div class="sec">Cargando el correo…</div>', [{t:'Cerrar', f:cerrarModal}], 760);
  api('vista_previa', a.n, 'recordatorio', FECHAS[f].iso, null).then(function(v){
    $('dlg').querySelector('.dlg-c').innerHTML = cabeceraCorreo(v) +
      '<iframe class="iframe-correo" style="height:420px" sandbox srcdoc="' + esc(v.html) + '"></iframe>';
    $('dlg-pie').textContent = 'Vista de solo lectura.';
  }).catch(function(e){$('dlg').querySelector('.dlg-c').innerHTML = '<div class="aviso dec">' + ico('alerta') + '<div>' + esc(e.message) + '</div></div>'});
}
function cabeceraCorreo(v){
  var modo = {respuesta:'Responde al hilo original', reconstruido:'Hilo reconstruido desde el respaldo en red',
              nuevo:'Correo nuevo'}[v.modo] || v.modo;
  return '<dl class="kv" style="margin:0 0 12px"><dt>Asunto</dt><dd><b>' + esc(v.asunto) + '</b></dd>' +
    '<dt>Para</dt><dd>' + esc((v.para || []).join('; ') || 'Los de la respuesta al hilo') + '</dd>' +
    '<dt>CC</dt><dd>' + esc((v.cc || []).join('; ') || '—') + '</dd>' +
    '<dt>Adjunto</dt><dd>' + esc(v.adjunto.nombre) + ' · ' + plural(v.adjunto.filas, 'fila', 'filas') + ' de la agencia</dd>' +
    '<dt>Forma</dt><dd>' + esc(modo) + '</dd></dl>' +
    (v.advertencias && v.advertencias.length ? '<div class="aviso dec" style="margin-bottom:12px">' + ico('alerta') + '<div>' +
      v.advertencias.map(esc).join('<br>') + '</div></div>' : '');
}

// =====================================================================
// 2. REVISIÓN PREVIA
// =====================================================================
function abrirRevision(tipo){
  tipo = tipo === 'inicio' ? 'inicio' : 'recordatorio';
  if (!E || (tipo === 'recordatorio' && !E.objetivo)) return;
  ir('revision');
  $('rev-sub').textContent = tipo === 'inicio' ? 'Correos de inicio de la campaña ' + E.campana : 'Recordatorios para el pago del ' + E.objetivo_largo;
  $('rev-tabla').innerHTML = '<div class="vacio">' + (tipo === 'inicio' ? 'Revisando agencias y respaldos…' : 'Revisando agencias y buscando los hilos en Outlook…') + '</div>';
  $('rev-mail').innerHTML = '';
  var fecha = tipo === 'inicio' ? null : E.objetivo;
  api('preparar_revision', tipo, fecha).then(function(r){
    REV = {tipo:tipo, filas:r.filas, fecha:fecha, marcadas:{}, hilo:{}, cur:null, espera:r.minutos_anulacion, lectura:r.confirmacion_lectura !== false, tok:0};
    r.filas.forEach(function(f, i){if (f.veredicto === 'lista') REV.marcadas[i] = true});
    REV.cur = r.filas.length ? 0 : null;
    pintarRevision(); cargarVistaRev();
  }).catch(function(e){$('rev-tabla').innerHTML = '<div class="vacio">' + esc(e.message) + '</div>'});
}
function revOk(i){
  var f = REV.filas[i];
  return f.veredicto === 'lista' || (f.veredicto === 'revisar' && f.hilo.estado === 'ambiguo' && !!REV.hilo[i]);
}
function pintarRevision(){
  var h = '<table class="tb" style="table-layout:fixed"><thead><tr><th style="width:44px"></th><th>Agencia y destinatario</th><th style="width:210px">Hilo</th><th style="width:190px">Estado</th></tr></thead><tbody>';
  REV.filas.forEach(function(f, i){
    var ok = revOk(i), hilo = '<span class="sec">—</span>';
    if (REV.tipo === 'inicio') hilo = '<span class="sec">Correo nuevo con el Excel de la agencia</span>';
    else if (f.hilo.estado === 'unico') hilo = 'Responde al hilo de inicio';
    else if (f.hilo.estado === 'ninguno') hilo = '<span class="sec">Sin hilo: respaldo o correo nuevo</span>';
    else if (f.hilo.estado === 'sin_outlook') hilo = '<span class="sec">Outlook no disponible</span>';
    else if (f.hilo.estado === 'ambiguo') hilo = '<select class="campo" style="width:190px;height:28px" aria-label="Hilo de ' + esc(f.agencia) +
      '" onclick="event.stopPropagation()" onchange="elegirHilo(' + i + ',this.value)"><option value="">Elija el hilo…</option>' +
      f.hilo.candidatos.map(function(c){return '<option value="' + esc(c.id) + '"' + (REV.hilo[i] === c.id ? ' selected' : '') + '>' +
        esc(c.enviado_en + ' · ' + c.almacen) + '</option>'}).join('') + '</select>';
    var estado = ok ? chip('env', 'Lista para enviar')
      : f.veredicto === 'omitida' ? chip('omit', 'Se omitirá')
      : f.veredicto === 'bloqueada' ? chip('bloq', 'Bloqueada')
      : chip('dec', 'Elija el hilo');
    h += '<tr class="clic ' + (REV.cur === i ? 'cur ' : '') + (ok ? '' : 'off') + '" onclick="verFila(' + i + ')">' +
      '<td><input type="checkbox" aria-label="Incluir ' + esc(f.agencia) + '" ' + (REV.marcadas[i] ? 'checked ' : '') + (ok ? '' : 'disabled ') +
      'onclick="event.stopPropagation()" onchange="marcar(' + i + ',this.checked)"></td>' +
      '<td><b>' + esc(f.agencia) + '</b><div class="sec">' + esc(f.motivo || f.para.join('; ') || '—') + '</div></td><td>' + hilo + '</td><td>' + estado + '</td></tr>';
  });
  $('rev-tabla').innerHTML = h + '</tbody></table>';
  var n = Object.keys(REV.marcadas).length;
  $('rev-nota').innerHTML = ico('seguro') + 'Nada sale hasta que confirme.';
  $('rev-info').textContent = REV.espera ? 'Después de enviar podrá anular durante ' + REV.espera + ' min.' : '';
  $('btn-env').textContent = n ? 'Enviar ' + plural(n, 'correo', 'correos') : 'Enviar';
  $('btn-env').disabled = $('btn-borr').disabled = n === 0;
  $('btn-prueba').disabled = REV.cur === null || !revOk(REV.cur);
}
function verFila(i){REV.cur = i; pintarRevision(); cargarVistaRev()}
function marcar(i, v){if (v) REV.marcadas[i] = true; else delete REV.marcadas[i]; pintarRevision()}
function elegirHilo(i, v){
  if (v){REV.hilo[i] = v; REV.marcadas[i] = true} else {delete REV.hilo[i]; delete REV.marcadas[i]}
  REV.cur = i; pintarRevision(); cargarVistaRev();
}
function cargarVistaRev(){
  if (REV.cur === null){$('rev-mail').innerHTML = '<div class="vacio">' + (REV.tipo === 'inicio' ? 'No hay agencias para el correo de inicio.' : 'No hay agencias con pagos para esa fecha.') + '</div>'; return}
  var f = REV.filas[REV.cur], tok = ++REV.tok;
  if (f.veredicto === 'bloqueada' || f.veredicto === 'omitida'){
    $('rev-mail').innerHTML = '<div class="mail-h"><h2>' + esc(f.agencia) + '</h2><div class="sec">' + esc(f.motivo) + '</div></div>';
    return;
  }
  $('rev-mail').innerHTML = '<div class="mail-h"><h2>' + esc(f.agencia) + '</h2><div class="sec">Armando el correo…</div></div>';
  api('vista_previa', f.agencia, REV.tipo, REV.fecha, REV.hilo[REV.cur] || null).then(function(v){
    if (tok !== REV.tok) return;
    $('rev-mail').innerHTML = '<div class="mail-h">' + cabeceraCorreo(v) + '</div><iframe class="iframe-correo" sandbox srcdoc="' + esc(v.html) + '"></iframe>';
  }).catch(function(e){
    if (tok !== REV.tok) return;
    $('rev-mail').innerHTML = '<div class="mail-h"><h2>' + esc(f.agencia) + '</h2><div class="aviso dec" style="margin-top:8px">' + ico('alerta') + '<div>' + esc(e.message) + '</div></div></div>';
  });
}
function enviarPrueba(){
  var f = REV.filas[REV.cur];
  api('enviarme_prueba', f.agencia, REV.tipo, REV.fecha, REV.hilo[REV.cur] || null)
    .then(function(r){toast('Prueba enviada a ' + r.enviado_a)}).catch(falla);
}
function selecciones(){
  return Object.keys(REV.marcadas).map(function(i){
    return {agencia:REV.filas[i].agencia, tipo:REV.tipo, fecha:REV.fecha, id_hilo:REV.hilo[i] || null};
  });
}
function confirmar(accion){
  var s = selecciones(), enviar = accion === 'enviar';
  var lista = '<ul class="lista">' + s.map(function(x){return '<li>' + esc(x.agencia) + '</li>'}).join('') + '</ul>';
  modal(enviar ? 'Confirmar envío' : 'Dejar como borradores',
    '<p style="margin:0">' + (enviar ? 'Se enviarán <b>' + (REV.tipo === 'inicio' ? plural(s.length, 'correo de inicio', 'correos de inicio') : plural(s.length, 'correo', 'correos')) + '</b> desde su cuenta, con su firma:'
      : 'Se crearán <b>' + plural(s.length, 'borrador', 'borradores') + '</b> en su Outlook, sin enviar:') + '</p>' + lista +
    (enviar && REV.espera ? '<div class="aviso dec" style="margin-top:14px">' + ico('reloj') + '<div><b>Podrá anularlos durante ' + REV.espera +
      ' minutos</b>Los correos esperan en la Bandeja de salida. Mantenga Outlook abierto.</div></div>' : '') +
    '<div class="fila-chk" style="margin-top:14px"><input type="checkbox" id="m-lectura"' + (REV.lectura ? ' checked' : '') + '>' +
    '<label for="m-lectura" style="margin:0">Pedir confirmación de lectura</label></div>' +
    '<p class="sec" style="margin:4px 0 0 24px">Outlook pedirá a cada agencia que confirme que abrió el correo. ' +
    'Recibirá un mensaje «Leído:» en su bandeja. Si la agencia no lo envía, no significa que no lo haya leído.</p>',
    [{t:'Cancelar', f:cerrarModal}, {t: enviar ? 'Enviar ' + plural(s.length, 'correo', 'correos') : 'Crear borradores', pri:true, f:function(){
      REV.lectura = $('m-lectura').checked; iniciarLote(accion, s, REV.lectura)}}]);
}
function iniciarLote(accion, s, lectura){
  $('dlg').innerHTML = '';
  modal(accion === 'enviar' ? 'Enviando…' : 'Creando borradores…',
    '<div class="sec" id="lote-actual">Preparando…</div><div class="barra-prog"><i id="lote-barra"></i></div><div class="sec" id="lote-n"></div>',
    [{t:'Cancelar lo que falta', f:function(){if (LOTE) api('cancelar_envio', LOTE)}}]);
  api('confirmar_envio', s, accion, lectura).then(function(r){
    LOTE = r.lote;
    sondear(r.lote);
  }).catch(function(e){cerrarModal(); falla(e)});
}
function sondear(id){
  api('progreso', id).then(function(p){
    var pct = p.total ? Math.round(p.hechos / p.total * 100) : 0;
    if ($('lote-barra')){
      $('lote-barra').style.width = pct + '%';
      $('lote-actual').textContent = p.actual ? 'Procesando ' + p.actual + '…' : 'Preparando…';
      $('lote-n').textContent = p.hechos + ' de ' + p.total;
    }
    if (!p.terminado) return setTimeout(function(){sondear(id)}, 600);
    cerrarModal();
    if (p.error) return falla(new Error(p.error));
    mostrarResultado(id, p);
  }).catch(function(e){cerrarModal(); falla(e)});
}

// =====================================================================
// 3. RESULTADO
// =====================================================================
var relojAnular = null;
function mostrarResultado(id, p){
  ir('resultado');
  var r = p.resultados, g = r.filter(function(x){return x.estado === 'env' || x.estado === 'borr'}).length;
  var otros = r.filter(function(x){return x.estado === 'omit' || x.estado === 'bloq'}).length;
  var prob = r.length - g - otros;
  var borr = p.accion === 'borrador';
  $('res-titulo').textContent = borr ? 'Borradores creados' : 'Envío realizado';
  $('res-sub').textContent = new Date().toLocaleString('es-PE') + ' · ' + (borr ? 'Quedaron en Borradores de su Outlook' : 'Enviados desde su cuenta');
  $('res-kpis').innerHTML = '<div class="card"><b>' + g + '</b><span class="sec">' + (borr ? 'Borradores generados' : 'Correos enviados') + '</span></div>' +
    '<div class="card"><b>' + otros + '</b><span class="sec">Omitidos o bloqueados</span></div>' +
    '<div class="card"><b' + (prob ? ' style="color:var(--rojo)"' : '') + '>' + prob + '</b><span class="sec">Con problema o por decidir</span></div>';
  var t = '<table class="tb"><thead><tr><th style="width:170px">Agencia</th><th style="width:200px">Resultado</th><th>Detalle</th></tr></thead><tbody>';
  r.forEach(function(x){
    var det = x.detalle || '';
    if (x.estado === 'env' || x.estado === 'borr') det = {respuesta:'Respuesta al hilo original', reconstruido:'Hilo reconstruido desde el respaldo en red', nuevo:'Correo nuevo'}[x.modo] || det;
    if (x.advertencias && x.advertencias.length) det += ' · ' + x.advertencias.join(' · ');
    t += '<tr><td><b>' + esc(x.agencia) + '</b></td><td>' + chip(x.estado) + '</td><td class="sec">' + esc(det) + '</td></tr>';
  });
  $('res-tabla').innerHTML = t + '</tbody></table>';
  clearInterval(relojAnular);
  $('res-anular').innerHTML = '';
  if (p.anulable_hasta){
    var hasta = new Date(p.anulable_hasta).getTime();
    var pintar = function(){
      var s = Math.max(0, Math.round((hasta - Date.now()) / 1000));
      if (!s){clearInterval(relojAnular); $('res-anular').innerHTML = ''; return}
      $('res-anular').innerHTML = '<div class="anular">' + ico('reloj') + '<div class="grow"><b>Los correos salen en <span class="cuenta">' +
        Math.floor(s / 60) + ':' + ('0' + s % 60).slice(-2) + '</span></b><br>Hasta entonces puede anularlos. Mantenga Outlook abierto.</div>' +
        '<button class="btn" onclick="anular(\'' + id + '\')">Anular envío</button></div>';
    };
    pintar(); relojAnular = setInterval(pintar, 1000);
  }
}
function anular(id){
  api('anular_envio', id).then(function(r){
    clearInterval(relojAnular); $('res-anular').innerHTML = '<div class="anular">' + ico('check') + '<div><b>Envío anulado</b><br>' +
      plural(r.anulados, 'correo retirado', 'correos retirados') + ' de la Bandeja de salida. Los avisos vuelven a estar pendientes.</div></div>';
    recargarCampana(true);
  }).catch(falla);
}

// =====================================================================
// 4. HISTORIAL
// =====================================================================
function cargarHistorial(){
  var sel = $('h-ag'), previo = sel.value;
  sel.innerHTML = '<option value="">Todas las agencias</option>' + AG.map(function(a){return '<option>' + esc(a.n) + '</option>'}).join('');
  sel.value = previo;
  pintarHistorial();
}
function pintarHistorial(){
  api('historial', $('h-ag').value, $('h-res').value, $('h-q').value).then(function(d){
    var h = '<table class="tb"><thead><tr><th style="width:130px">Fecha</th><th style="width:110px">Usuario</th><th style="width:150px">Agencia</th><th style="width:190px">Tipo de aviso</th><th style="width:190px">Resultado</th><th>Detalle</th></tr></thead><tbody>';
    d.filas.forEach(function(x){
      h += '<tr><td>' + esc(x.fecha + ' ' + x.hora) + '</td><td>' + esc(x.usuario) + '</td><td><b>' + esc(x.agencia) + '</b></td><td>' + esc(x.tipo) +
        '</td><td>' + chip(x.estado) + '</td><td class="sec">' + esc(x.detalle) + '</td></tr>';
    });
    $('hist-tabla').innerHTML = h + '</tbody></table>' + (d.filas.length ? '' :
      '<div class="vacio"><b style="color:var(--tinta)">No hay registros.</b><br>Aquí aparecerá cada aviso que prepare o envíe con esta versión.</div>');
    $('hist-n').textContent = d.campana + ' · ' + d.filas.length + ' de ' + d.total + ' registros';
  }).catch(function(e){$('hist-tabla').innerHTML = '<div class="vacio">' + esc(e.message) + '</div>'});
}

// =====================================================================
// 5. PREPARAR ENTREGA
// =====================================================================
function entReiniciar(){
  ENT = null;
  $('ent-1').style.display = ''; $('ent-2').style.display = 'none'; $('ent-3').style.display = 'none';
}
function leerArchivo(archivo){
  if (!/\.xlsx?m?$/i.test(archivo.name)) return falla(new Error('El archivo debe ser un Excel (.xlsx).'));
  var lector = new FileReader();
  lector.onload = function(){
    var b64 = String(lector.result).split(',')[1];
    $('drop').innerHTML = '<b>Leyendo ' + esc(archivo.name) + '…</b>';
    api('entrega_subir_original', archivo.name, b64).then(entCargado).catch(function(e){falla(e); restaurarDrop()});
  };
  lector.readAsDataURL(archivo);
}
function restaurarDrop(){
  $('drop').innerHTML = '<div>' + ico('subir') + '</div><b>Suelte aquí el cronograma original</b><span class="sec">Archivo Excel (.xlsx)</span>' +
    '<button class="btn" onclick="elegirOriginal()">Elegir archivo…</button>';
}
function elegirOriginal(){
  api('entrega_elegir_original').then(function(d){if (!d.cancelado) entCargado(d)}).catch(falla);
}
function entCargado(d){
  ENT = {d:d, sus:{}, reprog:[], q:''};
  d.puntos.forEach(function(p){if (p.sugerido) ENT.sus[p.clave] = true});
  $('ent-1').style.display = 'none'; $('ent-2').style.display = 'flex';
  $('ent-resumen').innerHTML = '<div class="k"><span class="sec">Archivo</span><b>' + esc(d.nombre) + '</b></div>' +
    '<div class="k"><span class="sec">Campaña</span><b>' + esc(d.campana) + '</b></div>' +
    '<div class="k"><span class="sec">Puntos</span><b>' + d.filas + '</b></div>' +
    '<div class="k"><span class="sec">Agencias</span><b>' + d.agencias + '</b></div>' +
    (d.coherencia ? '<div class="aviso dec" style="flex:1">' + ico('alerta') + '<div>' + esc(d.coherencia) + '</div></div>' : '');
  pintarPuntos(); pintarReprog();
}
function pintarPuntos(){
  var q = $('ent-q').value.trim().toUpperCase();
  var h = '<table class="tb"><thead><tr><th style="width:44px"></th><th>Agencia</th><th>Distrito · punto</th><th style="width:90px">Fecha</th><th style="width:120px">ETV</th><th style="width:110px"></th></tr></thead><tbody>';
  var n = 0, ocultos = 0;
  ENT.d.puntos.forEach(function(p){
    var texto = (p.agencia + ' ' + p.distrito + ' ' + p.punto + ' ' + p.clave).toUpperCase();
    if (q && texto.indexOf(q) < 0) return;
    if (!q && !ENT.sus[p.clave] && !p.sugerido && n >= 40){ocultos++; return}
    n++;
    h += '<tr class="' + (ENT.sus[p.clave] ? 'cur' : '') + '"><td><input type="checkbox" aria-label="Suspendido" ' + (ENT.sus[p.clave] ? 'checked ' : '') +
      'onchange="susMarcar(\'' + esc(p.clave) + '\',this.checked)"></td><td><b>' + esc(p.agencia) + '</b></td><td>' + esc(p.distrito) +
      '<div class="sec">' + esc(p.punto) + ' · ' + esc(p.clave) + '</div></td><td>' + esc(corta(p.fecha)) + '</td><td>' + esc(p.etv) + '</td><td>' +
      (p.sugerido ? '<span class="chip s-dec">Marcado en rojo</span>' : '<button class="btn liso" onclick="reprogramar(\'' + esc(p.clave) + '\')">Reprogramar</button>') + '</td></tr>';
  });
  $('ent-puntos').innerHTML = h + '</tbody></table>' + (ocultos ? '<div class="vacio">Hay ' + ocultos + ' puntos más. Use la búsqueda para encontrarlos.</div>' : '');
  var s = Object.keys(ENT.sus).length;
  $('ent-sus-n').textContent = s ? plural(s, 'punto se quitará', 'puntos se quitarán') + ' de la entrega' : 'Marque los puntos que se suspendieron';
  $('ent-nota').textContent = 'Se guardará como «' + ENT.d.nombre_sugerido + '». El original no cambia.';
}
function susMarcar(clave, v){if (v) ENT.sus[clave] = true; else delete ENT.sus[clave]; pintarPuntos()}
function pintarReprog(){
  $('ent-reprog').innerHTML = ENT.reprog.length ? ENT.reprog.map(function(r, i){
    var p = ENT.d.puntos.filter(function(x){return x.clave === r.clave})[0];
    return '<div class="rp"><span class="grow"><b>' + esc(p ? p.agencia : r.clave) + '</b> · ' + esc(p ? p.distrito : '') + '<br><span class="sec">' +
      esc(r.campo.replace('_', ' ')) + ' → ' + esc(r.valor.slice(8, 10) + '/' + r.valor.slice(5, 7) + '/' + r.valor.slice(0, 4)) + '</span></span>' +
      '<button aria-label="Quitar" onclick="ENT.reprog.splice(' + i + ',1);pintarReprog()">' + ico('x') + '</button></div>';
  }).join('') : '<div class="sec">Ninguna.</div>';
}
function reprogramar(clave){
  var p = ENT.d.puntos.filter(function(x){return x.clave === clave})[0];
  modal('Reprogramar fecha', '<p class="sec" style="margin:0"><b style="color:var(--tinta)">' + esc(p.agencia) + '</b> · ' + esc(p.distrito) + ' · ' + esc(p.punto) + '</p>' +
    '<label for="rp-campo">Qué fecha cambia</label><select class="campo" id="rp-campo">' +
    ENT.d.campos.filter(function(c){return /^Fecha/.test(c)}).map(function(c){return '<option value="' + c + '">' + c.replace('_', ' ') + '</option>'}).join('') + '</select>' +
    '<label for="rp-fecha">Nueva fecha</label><input class="campo" type="date" id="rp-fecha" value="' + esc(p.fecha || '') + '">',
    [{t:'Cancelar', f:cerrarModal}, {t:'Agregar', pri:true, f:function(){
      var v = $('rp-fecha').value; if (!v) return;
      ENT.reprog.push({clave:clave, campo:$('rp-campo').value, valor:v + 'T00:00:00'});
      cerrarModal(); pintarReprog();
    }}]);
}
function entCancelar(){entReiniciar()}
function entGenerar(){
  var sus = Object.keys(ENT.sus);
  api('entrega_elegir_destino', ENT.d.nombre_sugerido, ENT.d.carpeta_sugerida).then(function(r){
    if (r.cancelado) return;
    var origen = $('ent-origen').value.trim();
    $('ent-generar').disabled = true;
    return api('entrega_generar', ENT.d.token, r.ruta,
      sus.map(function(c){return {clave:c, origen:origen}}),
      ENT.reprog.map(function(x){return {clave:x.clave, campo:x.campo, valor:x.valor, origen:origen}}), true)
      .then(entListo);
  }).catch(falla).then(function(){$('ent-generar').disabled = false});
}
function entListo(g){
  $('ent-2').style.display = 'none'; $('ent-3').style.display = '';
  $('ent-3').innerHTML = '<div class="card" style="padding:24px"><h2>Entrega generada</h2>' +
    '<p class="sec">' + esc(g.destino) + '</p><div class="tres" style="margin-top:14px">' +
    '<div class="card"><b>' + g.filas_entrega + '</b><span class="sec">Puntos en la entrega</span></div>' +
    '<div class="card"><b>' + g.filas_quitadas + '</b><span class="sec">Puntos quitados</span></div>' +
    '<div class="card"><b>' + esc(g.columnas_quitadas.length) + '</b><span class="sec">Columnas quitadas</span></div></div>' +
    '<p class="sec" style="margin-top:14px">Quedó como la entrega vigente y su carpeta se recordará para la próxima campaña. ' +
    'La bitácora con el origen de cada cambio está junto al archivo.</p>' +
    '<div class="fila" style="margin-top:12px"><button class="btn pri" onclick="recargarCampana(true).then(function(){ir(\'control\')})">Ir al control de campaña</button>' +
    '<button class="btn" onclick="entReiniciar()">Preparar otra</button></div></div>';
}

// =====================================================================
// 6. CONFIGURACIÓN
// =====================================================================
function cargarConfig(){
  Promise.all([api('config_obtener'), api('perfil_obtener'), api('agencias_listar', true), api('auto_ajustes_obtener')]).then(function(r){
    CFG = r[0]; PERFIL = r[1]; AGS = r[2]; AUTO = r[3];
    pintarCfg();
  }).catch(function(e){$('cfg').innerHTML = '<div class="vacio">' + esc(e.message) + '</div>'});
}
function pintarCfg(){
  var v = CFG.valores, p = PERFIL.perfil;
  var S = {perfil:'', general:'', rutas:'', agencias:'', cambios:'', soporte:'', auto:''};
  S.auto = htmlAuto();
  S.soporte = '<div class="card"><h2>Soporte</h2>' +
    '<p class="sec">Si algo falla, genere el diagnóstico y envíelo a quien mantiene el programa. Incluye el registro de actividad y un resumen del equipo; ' +
    '<b>no incluye correos de agencias ni el contenido de los avisos</b>.</p>' +
    '<table class="tb"><tbody>' +
    '<tr><td class="sec" style="width:140px">Versión</td><td>' + esc(SESION.version || '') + '</td></tr>' +
    '<tr><td class="sec">Usuario</td><td>' + esc(SESION.usuario || '') + '</td></tr>' +
    '<tr><td class="sec">Equipo</td><td>' + esc(SESION.equipo || '') + '</td></tr>' +
    '<tr><td class="sec">Carpeta compartida</td><td>' + esc(CFG.compartida || '') + '</td></tr></tbody></table>' +
    '<div class="fila" style="margin-top:12px"><span class="grow"></span><button class="btn pri" onclick="exportarDiagnostico()">Exportar diagnóstico…</button></div></div>';
  // Perfil y firma
  S.perfil += '<div class="card"><h2>Mi perfil y firma</h2><p class="sec">' +
    (PERFIL.detectado_de === 'perfil' ? 'Así saldrá su firma en los correos que envíe.' : 'Detectado de ' + (PERFIL.detectado_de === 'outlook' ? 'Outlook' : 'Windows') + ': revíselo y guarde.') + '</p>' +
    campo('p-nombre', 'Nombre', p.nombre) + campo('p-cargo', 'Cargo (opcional)', p.cargo) +
    campo('p-dep', 'Dependencia', p.dependencia) +
    '<div class="fila" style="gap:8px"><div class="grow">' + campo('p-tel', 'Teléfono', p.telefono) + '</div><div style="width:110px">' + campo('p-anexo', 'Anexo', p.anexo) + '</div></div>' +
    campo('p-dir', 'Dirección', p.direccion) + campo('p-email', 'Correo', p.email) +
    '<div class="fila-chk"><input type="checkbox" id="p-mail" ' + (p.mostrar_email ? 'checked' : '') + '><label for="p-mail" style="margin:0">Mostrar el correo en la firma</label></div>' +
    '<div class="fila-chk"><input type="checkbox" id="p-conf" ' + (p.aviso_confidencial ? 'checked' : '') + '><label for="p-conf" style="margin:0">Incluir aviso de confidencialidad</label></div>' +
    '<label for="p-modo">Qué firma usar en los correos</label><select class="campo" id="p-modo">' +
    [['app', 'La firma del programa (recomendada)']].concat(p.modo_firma === 'outlook' ? [['outlook', 'La firma predeterminada de Outlook']] : [])
      .concat([['ninguna', 'Sin firma']]).map(function(o){
      return '<option value="' + o[0] + '"' + (p.modo_firma === o[0] ? ' selected' : '') + '>' + o[1] + '</option>'}).join('') + '</select>' +
    '<p class="sec" id="p-modo-ayuda" style="margin:6px 0 0"></p>' +
    '<div class="firma-prev" id="p-prev">' + PERFIL.firma_html + '</div>' +
    '<div class="fila" style="margin-top:12px"><span class="sec grow">' + (PERFIL.vista_logo ? 'Logo tomado de su firma de Outlook.' : 'No se encontró el logo en sus firmas de Outlook.') + '</span>' +
    '<button class="btn pri" onclick="guardarPerfil()">Guardar perfil</button></div></div>';

  // Jefatura y exclusiones
  S.general += '<div class="card"><h2>Jefatura del correo de inicio</h2><p class="sec">Aparece en «Por encargo del Sr. …». No es la firma de quien envía.</p>' +
    campo('c-jefe', 'Nombre', v.por_encargo_nombre) + campo('c-cargo', 'Cargo', v.por_encargo_cargo) +
    '<h2 style="margin-top:18px">Excluidos de los recordatorios</h2><p class="sec">Reciben el correo de inicio, pero no los recordatorios.</p>' +
    '<div class="excl" id="c-excl">' + v.correos_excluidos.map(function(m, j){
      return '<span>' + esc(m) + '<button aria-label="Quitar ' + esc(m) + '" onclick="quitarExcl(' + j + ')">' + ico('x') + '</button></span>'}).join('') + '</div>' +
    '<div class="fila" style="gap:8px"><input class="campo grow" id="c-nuevo" placeholder="correo@bn.com.pe" onkeydown="if(event.key===\'Enter\')agregarExcl()">' +
    '<button class="btn" onclick="agregarExcl()">Agregar</button></div>' +
    '<h2 style="margin-top:18px">Con copia en los correos</h2><p class="sec">La jefatura y el resto del área reciben copia (CC) del correo de inicio y de los recordatorios que no van como respuesta al hilo. ' +
    'Los «excluidos» de arriba no reciben copia de los recordatorios.</p>' +
    '<div class="excl" id="c-copia">' + (v.copia_fija || []).map(function(m, j){
      return '<span>' + esc(m) + '<button aria-label="Quitar ' + esc(m) + '" onclick="quitarCopia(' + j + ')">' + ico('x') + '</button></span>'}).join('') + '</div>' +
    '<div class="fila" style="gap:8px"><input class="campo grow" id="c-nuevo-copia" placeholder="Pegue uno o varios correos" onkeydown="if(event.key===\'Enter\')agregarCopia()">' +
    '<button class="btn" onclick="agregarCopia()">Agregar</button></div></div>';

  S.general += '<div class="card"><h2>Envío y calendario</h2><p class="sec">Tiempo para anular un envío y días no hábiles.</p>' +
    '<label for="c-min">Minutos para anular un envío (0 = sale de inmediato)</label><input class="campo" type="number" min="0" max="30" id="c-min" value="' + esc(v.minutos_anulacion) + '">' +
    '<div class="fila-chk" style="margin:12px 0 4px"><input type="checkbox" id="c-lec"' + (v.confirmacion_lectura !== false ? ' checked' : '') + '>' +
    '<label for="c-lec" style="margin:0">Pedir confirmación de lectura al enviar (se puede cambiar en cada envío)</label></div>' +
    campo('c-dom', 'Dominio interno', v.dominio_interno) +
    '<label for="c-fer">Feriados (uno por línea, AAAA-MM-DD)</label><textarea class="campo" rows="3" id="c-fer">' + esc(v.feriados.join('\n')) + '</textarea></div>';

  // Rutas
  S.rutas += '<div class="card ancho rutas"><h2>Rutas</h2><p class="sec">Dónde busca y guarda el programa. Las rutas «Solo este equipo» no afectan a otras personas; las «Compartidas con todos» sí. Cada cambio queda registrado. Carpeta compartida: ' + esc(CFG.compartida) +
    (CFG.compartida_ok ? '' : ' <b style="color:#B00020">(sin acceso)</b>') + '</p>' +
    CFG.rutas.map(function(r){
      var e = {ok:['env', 'Accesible'], no_existe:['bloq', 'No existe'], tipo_incorrecto:['dec', r.detalle], sin_configurar:['omit', 'Sin configurar']}[r.estado];
      return '<div class="rt"><span><b style="color:var(--tinta)">' + esc(r.etiqueta) + '</b><br><span class="sec">' +
        (r.alcance === 'equipo' ? 'Solo este equipo' : 'Compartida con todos') + '</span></span><input class="campo" data-ruta="' + r.campo + '" value="' + esc(v[r.campo] != null ? v[r.campo] : r.valor) + '">' +
        chip(e[0], e[1]) + '<button class="btn" onclick="cambiarRuta(\'' + r.campo + '\')">Cambiar…</button></div>';
    }).join('') + '</div>';

  // Agencias
  S.agencias += '<div class="card ancho"><div class="fila"><div class="grow"><h2>Agencias y correos</h2><p class="sec" style="margin:2px 0 0">' +
    plural(AGS.agencias.filter(function(a){return a.activa}).length, 'agencia activa', 'agencias activas') + '. Puede editar sus correos, desactivarla o eliminarla; cada cambio queda en el historial.</p></div>' +
    '<button class="btn" onclick="importarAgencias()">Importar desde Excel</button>' +
    '<button class="btn" onclick="verHistorialAgencias(\'\')">Historial de cambios</button>' +
    '<button class="btn pri" style="height:32px" onclick="editarAgencia(null)">Agregar agencia</button></div>' +
    '<table class="tb" style="margin-top:12px"><thead><tr><th style="width:160px">Agencia</th><th>Para</th><th>CC</th><th style="width:90px">Estado</th><th style="width:270px"></th></tr></thead><tbody>' +
    AGS.agencias.map(function(a){
      return '<tr class="' + (a.activa ? '' : 'off') + '"><td><b>' + esc(a.nombre) + '</b></td><td class="sec">' + esc(a.para.join('; ')) + '</td><td class="sec">' + esc(a.cc.join('; ') || '—') +
        '</td><td>' + chip(a.activa ? 'env' : 'omit', a.activa ? 'Activa' : 'Inactiva') + '</td><td style="text-align:right">' +
        '<button class="btn liso" onclick="editarAgencia(\'' + esc(a.nombre) + '\')">Editar</button>' +
        '<button class="btn liso" onclick="alternarAgencia(\'' + esc(a.nombre) + '\',' + (!a.activa) + ')">' + (a.activa ? 'Desactivar' : 'Activar') + '</button>' +
        '<button class="btn liso" style="color:#B00020" onclick="eliminarAgencia(\'' + esc(a.nombre) + '\')">Eliminar</button></td></tr>';
    }).join('') + '</tbody></table>' +
    (AGS.agencias.length ? '' : '<div class="vacio">Todavía no hay agencias cargadas. Use «Importar desde Excel» o «Agregar agencia».</div>') + '</div>';

  // Historial de cambios de configuración
  S.cambios += '<div class="card ancho"><h2>Cambios recientes de configuración</h2><table class="tb" style="margin-top:8px"><thead><tr><th style="width:150px">Cuándo</th><th style="width:110px">Quién</th><th style="width:200px">Campo</th><th>Antes</th><th>Después</th></tr></thead><tbody>' +
    CFG.historial.slice(0, 12).map(function(c){
      return '<tr><td>' + esc(c.cuando.replace('T', ' ')) + '</td><td>' + esc(c.usuario) + '</td><td><b>' + esc(c.campo) + '</b></td><td class="sec">' + esc(c.antes || '—') + '</td><td class="sec">' + esc(c.despues || '—') + '</td></tr>';
    }).join('') + '</tbody></table>' + (CFG.historial.length ? '' : '<div class="vacio">Sin cambios registrados.</div>') + '</div>';

  var nombres = [['agencias', 'Agencias y correos (' + AGS.agencias.length + ')'], ['perfil', 'Mi perfil y firma'],
                 ['general', 'Jefatura y envío'], ['rutas', 'Rutas'], ['auto', 'Automático'], ['cambios', 'Cambios'], ['soporte', 'Soporte']];
  $('cfg-tabs').innerHTML = nombres.map(function(t){
    return '<button class="' + (CFG_TAB === t[0] ? 'on' : '') + '" onclick="cfgTab(\'' + t[0] + '\')">' + t[1] + '</button>';
  }).join('');
  $('cfg-guardar').style.display = (CFG_TAB === 'general' || CFG_TAB === 'rutas') ? '' : 'none';
  $('cfg').innerHTML = S[CFG_TAB];
  if (CFG_TAB === 'auto') pintarEstadoAuto();
  if (CFG_TAB === 'perfil'){
    ['p-nombre','p-cargo','p-dep','p-tel','p-anexo','p-dir','p-email','p-mail','p-conf','p-modo'].forEach(function(id){
      $(id).addEventListener('input', previaFirma); $(id).addEventListener('change', previaFirma);
    });
    previaFirma();
  }
}
function campo(id, rotulo, valor){return '<label for="' + id + '">' + rotulo + '</label><input class="campo" id="' + id + '" value="' + esc(valor) + '">'}
function perfilForm(){
  return {nombre:$('p-nombre').value, cargo:$('p-cargo').value, dependencia:$('p-dep').value, telefono:$('p-tel').value,
          anexo:$('p-anexo').value, direccion:$('p-dir').value, email:$('p-email').value,
          mostrar_email:$('p-mail').checked, aviso_confidencial:$('p-conf').checked, modo_firma:$('p-modo').value, logo_path: PERFIL.logo || ''};
}
var tPrev;
var AYUDA_FIRMA = {
  app: 'Se arma con los datos de este perfil y el logo de su firma de Outlook. Se ve igual en la vista previa y en cualquier PC.',
  outlook: 'Solo funciona si su Outlook ya tiene una firma predeterminada para mensajes nuevos. Si no la tiene, el correo sale sin firma.',
  ninguna: 'El correo sale sin firma.'
};
function previaFirma(){
  var modo = $('p-modo').value;
  $('p-modo-ayuda').textContent = AYUDA_FIRMA[modo] || '';
  clearTimeout(tPrev);
  if (modo !== 'app'){
    $('p-prev').innerHTML = '<span class="sec">' + (modo === 'outlook' ? 'La firma la agrega Outlook al crear cada correo.' : 'Sin firma.') + '</span>';
    return;
  }
  tPrev = setTimeout(function(){
    api('firma_vista_previa', perfilForm()).then(function(r){$('p-prev').innerHTML = r.html}).catch(function(){});
  }, 250);
}
function guardarPerfil(){
  api('perfil_guardar', perfilForm()).then(function(){toast('Perfil guardado'); return api('iniciar')})
    .then(function(s){mostrarSesion(s)}).catch(falla);
}
function configForm(){
  var valores = Object.assign({}, CFG.valores);
  var campos = {'c-jefe':'por_encargo_nombre', 'c-cargo':'por_encargo_cargo', 'c-dom':'dominio_interno'};
  Object.keys(campos).forEach(function(id){if ($(id)) valores[campos[id]] = $(id).value.trim()});
  if ($('c-min')) valores.minutos_anulacion = parseInt($('c-min').value || '0', 10);
  if ($('c-lec')) valores.confirmacion_lectura = $('c-lec').checked;
  if ($('c-fer')) valores.feriados = $('c-fer').value.split('\n').map(function(x){return x.trim()}).filter(Boolean);
  document.querySelectorAll('[data-ruta]').forEach(function(el){valores[el.dataset.ruta] = el.value.trim()});
  return valores;
}
function cfgTab(t){CFG.valores = configForm(); CFG_TAB = t; pintarCfg()}
function guardarCfg(){
  api('config_guardar', configForm()).then(function(r){
    toast(r.reiniciar ? 'Guardado. La carpeta compartida nueva se usará al volver a abrir el programa.'
                      : r.cambios ? plural(r.cambios, 'cambio guardado', 'cambios guardados') : 'Sin cambios');
    return Promise.all([api('iniciar'), recargarCampana(true)]);
  }).then(function(x){mostrarSesion(x[0]); cargarConfig()}).catch(falla);
}
// Saca las direcciones de un texto pegado: acepta varias a la vez, separadas por «;», comas o saltos de línea,
// y también el formato de Outlook «Nombre <correo@bn.com.pe>».
function correosDe(texto){
  return (String(texto).toLowerCase().match(/[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}/g) || []);
}
function agregarALista(campoLista, idEntrada){
  var nuevos = correosDe($(idEntrada).value);
  if (!nuevos.length) return falla(new Error('Escriba o pegue al menos un correo.'));
  var dom = '@' + $('c-dom').value.trim().toLowerCase();
  var ajenos = nuevos.filter(function(c){return c.slice(-dom.length) !== dom});
  if (ajenos.length) return falla(new Error('Deben pertenecer a ' + dom + ': ' + ajenos.join(', ')));
  CFG.valores = Object.assign(CFG.valores, configForm());
  CFG.valores[campoLista] = CFG.valores[campoLista] || [];
  nuevos.forEach(function(c){if (CFG.valores[campoLista].indexOf(c) < 0) CFG.valores[campoLista].push(c)});
  pintarCfg();
}
function agregarExcl(){agregarALista('correos_excluidos', 'c-nuevo')}
function agregarCopia(){agregarALista('copia_fija', 'c-nuevo-copia')}
function quitarCopia(j){CFG.valores = Object.assign(CFG.valores, configForm()); CFG.valores.copia_fija.splice(j, 1); pintarCfg()}
function quitarExcl(j){CFG.valores = Object.assign(CFG.valores, configForm()); CFG.valores.correos_excluidos.splice(j, 1); pintarCfg()}
function cambiarRuta(campo){
  api('config_elegir_ruta', campo).then(function(r){
    if (r.cancelado) return;
    document.querySelector('[data-ruta="' + campo + '"]').value = r.ruta;
    toast('Ruta elegida. Pulse «Guardar cambios» para aplicarla.');
  }).catch(falla);
}

// ---- agencias ----
function editarAgencia(nombre){
  var a = nombre ? AGS.agencias.filter(function(x){return x.nombre === nombre})[0] : {nombre:'', para:[], cc:[], nota:''};
  modal(nombre ? 'Editar ' + nombre : 'Agregar agencia',
    (nombre ? '' : '<label for="ag-nombre">Nombre de la agencia</label><input class="campo" id="ag-nombre" placeholder="Como figura en el cronograma">') +
    '<label for="ag-para">Para (uno por línea o separados por «;»)</label><textarea class="campo" rows="3" id="ag-para">' + esc(a.para.join('\n')) + '</textarea>' +
    '<label for="ag-cc">CC</label><textarea class="campo" rows="2" id="ag-cc">' + esc(a.cc.join('\n')) + '</textarea>' +
    '<label for="ag-nota">Nota (opcional)</label><input class="campo" id="ag-nota" value="' + esc(a.nota) + '"><div class="err" id="ag-err"></div>',
    [{t:'Cancelar', f:cerrarModal}, {t:'Guardar', pri:true, f:function(){
      var lista = function(id){return $(id).value.split(/[\n;,]+/).map(function(x){return x.trim()}).filter(Boolean)};
      var p = nombre ? api('agencia_actualizar', nombre, lista('ag-para'), lista('ag-cc'), $('ag-nota').value)
                     : api('agencia_agregar', $('ag-nombre').value, lista('ag-para'), lista('ag-cc'), $('ag-nota').value);
      p.then(function(){cerrarModal(); toast('Agencia guardada'); cargarConfig(); recargarCampana(true)})
       .catch(function(e){$('ag-err').textContent = e.message});
    }}]);
}
function eliminarAgencia(nombre){
  modal('Eliminar agencia',
    '<p style="margin:0">¿Eliminar <b>' + esc(nombre) + '</b> de la lista?</p>' +
    '<p class="sec">Dejará de recibir avisos. El historial conserva quién la eliminó y con qué correos estaba. ' +
    'Si solo quiere pausarla, use «Desactivar».</p>',
    [{t:'Cancelar', f:cerrarModal}, {t:'Eliminar', pri:true, f:function(){
      api('agencia_eliminar', nombre).then(function(){cerrarModal(); toast('Agencia eliminada'); cargarConfig(); recargarCampana(true)}).catch(falla);
    }}]);
}
function alternarAgencia(nombre, activa){
  api('agencia_estado', nombre, activa).then(function(){toast(activa ? 'Agencia activada' : 'Agencia desactivada'); cargarConfig(); recargarCampana(true)}).catch(falla);
}
function importarAgencias(){
  api('agencias_importar').then(function(r){
    toast(plural(r.agregadas.length, 'agencia importada', 'agencias importadas') + (Object.keys(r.rechazadas).length ? ' · ' + Object.keys(r.rechazadas).length + ' rechazadas' : ''));
    cargarConfig(); recargarCampana(true);
  }).catch(falla);
}
function verHistorialAgencias(nombre){
  api('agencias_historial', nombre).then(function(d){
    modal('Historial de agencias',
      '<table class="tb"><thead><tr><th>Cuándo</th><th>Quién</th><th>Agencia</th><th>Campo</th><th>Antes</th><th>Después</th></tr></thead><tbody>' +
      d.cambios.slice(0, 80).map(function(c){return '<tr><td>' + esc(c.cuando.replace('T', ' ')) + '</td><td>' + esc(c.usuario) + '</td><td><b>' + esc(c.agencia) + '</b></td><td>' +
        esc(c.campo) + '</td><td class="sec">' + esc(c.antes || '—') + '</td><td class="sec">' + esc(c.despues || '—') + '</td></tr>'}).join('') + '</tbody></table>' +
      (d.cambios.length ? '' : '<div class="vacio">Sin cambios registrados.</div>'), [{t:'Cerrar', f:cerrarModal}], 860);
  }).catch(falla);
}

// =====================================================================
// Segundo plano: revisar Enviados y envío automático
// =====================================================================
var VIG = null, SYNC_TOTAL = 0, BANNER_FIRMA = '', BANNER_OCULTO = '', SALE_EN = null, ANUL_HASTA = null;
function mmss(s){return Math.floor(s / 60) + ':' + ('0' + s % 60).slice(-2)}
function vigilar(){
  api('vigilancia_estado').then(function(v){
    VIG = v;
    var s = v.sync;
    if (s.nuevos_total > SYNC_TOTAL){
      toast(plural(s.nuevos_total - SYNC_TOTAL, 'aviso enviado por fuera del programa se anotó', 'avisos enviados por fuera del programa se anotaron'));
      if (vista === 'control') recargarCampana(true);
    }
    SYNC_TOTAL = s.nuevos_total;
    var partes = [];
    if (s.activa) partes.push(s.error ? 'Enviados: no se pudo revisar' : s.ultima ? 'Enviados revisados a las ' + s.ultima.slice(11, 16) : 'Revisando Enviados…');
    if (v.auto.activo) partes.push('Envío automático a las ' + v.auto.hora);
    $('u-vig').innerHTML = partes.map(esc).join('<br>');
    if (vista === 'config' && CFG_TAB === 'auto') pintarEstadoAuto();
    pintarBanner();
  }).catch(function(){});
}
function relojBanner(){
  var c = document.querySelector('#auto-banner .cuenta-auto');
  if (c && SALE_EN !== null) c.textContent = mmss(Math.max(0, Math.round((SALE_EN - Date.now()) / 1000)));
  var u = document.querySelector('#auto-banner .cuenta-anul');
  if (u && ANUL_HASTA !== null){
    var s = Math.max(0, Math.round((ANUL_HASTA - Date.now()) / 1000));
    u.textContent = mmss(s);
    if (!s){var b = document.querySelector('#auto-banner .anul-fila'); if (b) b.style.display = 'none'}
  }
}
function pintarBanner(){
  var a = VIG.auto, el = $('auto-banner'), h = '', suave = false;
  SALE_EN = a.sale_en !== null && a.sale_en !== undefined ? Date.now() + a.sale_en * 1000 : null;
  ANUL_HASTA = a.anulable_hasta ? new Date(a.anulable_hasta).getTime() : null;
  var prueba = a.prueba ? '<span class="chip-prueba">PRUEBA</span>' : '';
  var borr = a.accion === 'borrador';
  var detalle = function(){
    return a.descartados.length ? '<details><summary>' + plural(a.descartados.length, 'aviso queda', 'avisos quedan') + ' para revisar a mano</summary><ul>' +
      a.descartados.map(function(d){return '<li><b>' + esc(d.agencia) + '</b> (' + corta(d.fecha) + '): ' + esc(d.motivo) + '</li>'}).join('') + '</ul></details>' : '';
  };
  if (a.fase === 'cuenta'){
    var n = a.listos.length;
    h = '<div class="rot">' + prueba + 'Envío automático</div>' +
      '<h2>' + (borr ? 'Se crearán ' + plural(n, 'borrador', 'borradores') : 'Se enviarán ' + plural(n, 'recordatorio', 'recordatorios')) +
      ' en <span class="cuenta cuenta-auto">' + mmss(a.sale_en) + '</span></h2>' +
      '<p class="sec">' + a.listos.map(function(x){return esc(x.agencia)}).join(' · ') + '</p>' + detalle() +
      '<div class="fila"><span class="ayuda grow">' + (borr ? 'Quedarán en Borradores de su Outlook.' : 'Después podrá anularlos durante ' + SESION.minutos + ' min.') + '</span>' +
      '<button class="btn" onclick="autoCancelar()">Cancelar</button><button class="btn pri" onclick="autoEnviarYa()">' + (borr ? 'Crear ya' : 'Enviar ahora') + '</button></div>';
  } else if (a.fase === 'preparando'){
    h = '<div class="rot">' + prueba + 'Envío automático</div><h2>Preparando los recordatorios de hoy…</h2><p class="sec">' + esc(a.mensaje) + '</p>';
  } else if (a.fase === 'enviando'){
    var av = a.avance || {hechos:0, total:0};
    h = '<div class="rot">' + prueba + 'Envío automático</div><h2>' + (borr ? 'Creando borradores…' : 'Enviando…') + ' ' + av.hechos + ' de ' + av.total + '</h2>' +
      '<div class="barra-prog"><i style="width:' + (av.total ? Math.round(av.hechos / av.total * 100) : 0) + '%"></i></div>';
  } else if (a.fase === 'hecho'){
    var r = a.resumen || {}, prob = r.problemas || 0;
    h = '<div class="rot">' + prueba + 'Envío automático</div><h2>' + esc(a.mensaje || 'Terminado') + '</h2>' +
      (prob ? '<p class="sec"><b>' + plural(prob, 'aviso con problema', 'avisos con problema') + '.</b> El detalle está en el Historial.</p>' : '') + detalle() +
      (ANUL_HASTA && ANUL_HASTA > Date.now() && a.lote ? '<div class="fila anul-fila"><span class="ayuda grow">Salen en <b class="cuenta cuenta-anul">' + mmss(Math.round((ANUL_HASTA - Date.now()) / 1000)) +
        '</b>. Hasta entonces puede anularlos.</span><button class="btn" onclick="autoAnular(\'' + a.lote + '\')">Anular envío</button></div>' : '') +
      '<div class="fila"><span class="grow"></span><button class="btn" onclick="autoCerrar()">Cerrar</button></div>';
  } else if (a.fase === 'sin_nada' || a.fase === 'cancelado'){
    h = '<div class="rot">' + prueba + 'Envío automático</div><h2>' + (a.fase === 'cancelado' ? 'Cancelado' : 'Nada que enviar') + '</h2><p class="sec">' + esc(a.mensaje) + '</p>' + detalle() +
      '<div class="fila"><span class="grow"></span><button class="btn" onclick="autoCerrar()">Cerrar</button></div>';
  } else if (a.fase === 'esperando_outlook'){
    suave = true;
    h = '<div class="rot">Envío automático en pausa</div><p>' + esc(a.mensaje) + '</p><div class="fila"><span class="grow"></span><button class="btn" onclick="ocultarPausa()">Entendido</button></div>';
    if (BANNER_OCULTO === a.fase + a.mensaje) h = '';
  }
  // Solo se vuelve a dibujar si cambió lo que se muestra; el reloj se actualiza aparte (así «ver cuáles» no se cierra solo)
  var firma = a.fase + '|' + h.replace(/<span class="cuenta cuenta-auto">[^<]*<\/span>/, '').replace(/<b class="cuenta cuenta-anul">[^<]*<\/b>/, '')
    .replace(/<i style="width:[^"]*"><\/i>/, '') + '|' + (a.avance ? a.avance.hechos : '');
  el.classList.toggle('on', !!h);
  el.classList.toggle('suave', suave);
  if (firma !== BANNER_FIRMA){BANNER_FIRMA = firma; el.innerHTML = h}
  else if (a.fase === 'enviando'){var barra = el.querySelector('.barra-prog i'); if (barra) barra.style.width = (a.avance && a.avance.total ? Math.round(a.avance.hechos / a.avance.total * 100) : 0) + '%'}
}
function ocultarPausa(){BANNER_OCULTO = VIG.auto.fase + VIG.auto.mensaje; pintarBanner()}
function autoCancelar(){api('auto_cancelar').then(function(){toast('Envío automático cancelado: no se envió nada'); vigilar()}).catch(falla)}
function autoEnviarYa(){api('auto_enviar_ya').then(function(){vigilar()}).catch(falla)}
function autoCerrar(){api('auto_descartar').then(function(){BANNER_FIRMA = ''; vigilar()}).catch(falla)}
function autoAnular(lote){
  api('anular_envio', lote).then(function(r){
    toast(plural(r.anulados, 'correo retirado', 'correos retirados') + ' de la Bandeja de salida');
    recargarCampana(true); autoCerrar();
  }).catch(falla);
}

// ---- Configuración › Automático ----
function htmlAuto(){
  var a = AUTO || {};
  return '<div class="card ancho"><h2>Revisar mi carpeta Enviados</h2>' +
    '<p class="sec">Mientras el programa está abierto, cada 3 minutos lee su carpeta <b>Enviados</b> (solo lectura) y anota en el registro los avisos de esta campaña ' +
    'que salieron por fuera del programa: a mano desde Outlook o con la versión anterior. Así el tablero no los muestra como pendientes y el programa no los repite. ' +
    'Solo mira correos cuyo asunto es el de un aviso de la campaña; no lee ningún otro.</p>' +
    '<div class="fila-chk"><input type="checkbox" id="a-ver"' + (a.verificar_enviados !== false ? ' checked' : '') + '><label for="a-ver" style="margin:0">Revisar mis Enviados cada 3 minutos</label></div>' +
    '<p class="sec" id="a-sync" style="margin:8px 0"></p>' +
    '<div class="fila"><span class="grow"></span><button class="btn" onclick="revisarEnviados()">Revisar ahora</button></div></div>' +
    '<div class="card ancho"><h2>Envío automático de recordatorios</h2>' +
    '<p class="sec">Apagado de fábrica. A la hora elegida, el programa prepara los recordatorios del día y, tras una cuenta regresiva que usted puede cancelar, los envía desde su cuenta. ' +
    '<b>Solo salen solos</b> los avisos sin advertencias y con el correo de inicio de la campaña a mano; los demás quedan para revisarlos usted. ' +
    'Los correos de inicio nunca se envían solos. Los envíos conservan los minutos para anular.</p>' +
    '<div class="fila-chk"><input type="checkbox" id="a-act"' + (a.activo ? ' checked' : '') + '><label for="a-act" style="margin:0">Enviar automáticamente los recordatorios del día</label></div>' +
    '<div class="fila" style="gap:12px;margin-top:8px"><div><label for="a-hora">Hora</label><input class="campo" type="time" id="a-hora" value="' + esc(a.hora || '08:00') + '" style="width:120px"></div>' +
    '<div class="grow"><label for="a-acc">Qué hace a esa hora</label><select class="campo" id="a-acc">' +
      '<option value="enviar"' + (a.accion !== 'borrador' ? ' selected' : '') + '>Enviar los recordatorios</option>' +
      '<option value="borrador"' + (a.accion === 'borrador' ? ' selected' : '') + '>Solo dejar borradores (ensayo)</option></select></div>' +
    '<div><label for="a-cta">Cuenta regresiva (segundos)</label><input class="campo" type="number" min="15" max="600" id="a-cta" value="' + esc(a.cuenta_s || 60) + '" style="width:120px"></div></div>' +
    '<div class="aviso dec" style="margin-top:12px">' + ico('alerta') + '<div><b>Condiciones</b>El programa y Outlook deben estar abiertos y el equipo sin bloquear a esa hora. ' +
      'Si abre el programa pasadas 3 horas de la hora elegida, ese día no se envía solo. Al empezar la cuenta regresiva la ventana pasa al frente y suena un aviso. ' +
      'Esta configuración es de este equipo; no afecta a otras personas.</div></div>' +
    '<p class="sec" id="a-estado" style="margin:10px 0 0"></p>' +
    '<div class="fila" style="margin-top:12px"><span class="grow"></span><button class="btn" onclick="probarAuto()">Probar ahora…</button><button class="btn pri" onclick="guardarAuto()">Guardar</button></div></div>';
}
function pintarEstadoAuto(){
  if (!VIG || !$('a-sync')) return;
  var s = VIG.sync, a = VIG.auto;
  $('a-sync').textContent = !s.activa ? 'La revisión automática está apagada.' :
    s.error ? 'No se pudo revisar: ' + s.error :
    s.ultima ? 'Última revisión a las ' + s.ultima.slice(11, 16) + (s.resumen ? ' · ' + s.resumen : '') : 'Aún no se ha revisado en esta sesión.';
  var estado = {inactivo:'El envío automático está apagado.', espera:a.mensaje, esperando_outlook:a.mensaje, cuenta:'Cuenta regresiva en curso.',
    preparando:'Preparando…', enviando:'Enviando…', hecho:'Hoy: ' + (a.mensaje || 'terminado'), sin_nada:'Hoy: ' + a.mensaje, cancelado:'Hoy: cancelado.'}[a.fase];
  $('a-estado').textContent = estado || '';
}
function formAuto(){
  return {activo:$('a-act').checked, hora:$('a-hora').value, accion:$('a-acc').value, cuenta_s:parseInt($('a-cta').value || '60', 10), verificar_enviados:$('a-ver').checked};
}
function guardarAuto(){
  api('auto_ajustes_guardar', formAuto()).then(function(v){AUTO = v; toast('Guardado'); vigilar()}).catch(falla);
}
function revisarEnviados(){
  toast('Revisando su carpeta Enviados…');
  api('enviados_revisar').then(function(r){toast(r.resumen || 'Revisado'); vigilar()}).catch(falla);
}
function probarAuto(){
  var f = formAuto(), borr = f.accion === 'borrador';
  modal('Probar el envío automático',
    '<p style="margin:0">Se hará ahora lo mismo que a la hora programada: el programa revisa sus Enviados, prepara los recordatorios de hoy y empieza una cuenta regresiva de <b>' + f.cuenta_s + ' segundos</b> que podrá cancelar.</p>' +
    '<p style="margin:10px 0 0">Al terminar la cuenta regresiva ' + (borr ? '<b>dejará borradores</b> en su Outlook, sin enviar.' : '<b>enviará los correos</b> desde su cuenta (podrá anularlos durante ' + SESION.minutos + ' min).') + '</p>' +
    (borr ? '' : '<p class="sec" style="margin:10px 0 0">Si solo quiere ensayar, elija antes «Solo dejar borradores».</p>'),
    [{t:'Cancelar', f:cerrarModal}, {t:'Empezar la prueba', pri:true, f:function(){
      cerrarModal();
      api('auto_ajustes_guardar', f).then(function(v){AUTO = v; toast('Preparando…'); return api('auto_probar')}).then(function(){vigilar()}).catch(falla);
    }}]);
}

// =====================================================================
// Arranque
// =====================================================================
function mostrarSesion(s){
  SESION = {nombre:s.nombre, hoy_largo:s.hoy_largo, minutos:s.minutos_anulacion, version:s.version, usuario:s.usuario, equipo:s.equipo};
  var partes = s.nombre.split(/[\s,]+/).filter(Boolean);
  $('u-ini').textContent = ((partes[0] || '?')[0] + (partes[1] ? partes[1][0] : '')).toUpperCase();
  $('u-nom').textContent = s.nombre;
  $('u-fecha').textContent = s.hoy_largo;
  $('u-pto').style.background = s.outlook ? 'var(--ok)' : 'var(--at)';
  $('u-con').textContent = s.outlook ? 'Outlook conectado' : s.outlook_lento ? 'Outlook no responde' : 'Outlook no disponible';
}
function iniciar(){
  $('ico-busca').innerHTML = $('ico-busca2').innerHTML = $('ico-busca3').innerHTML = ico('buscar');
  $('rev-volver').innerHTML = ico('atras');
  $('ico-subir').innerHTML = ico('subir');
  var drop = $('drop');
  ['dragenter','dragover'].forEach(function(n){drop.addEventListener(n, function(e){e.preventDefault(); drop.classList.add('sobre')})});
  ['dragleave','drop'].forEach(function(n){drop.addEventListener(n, function(e){e.preventDefault(); drop.classList.remove('sobre')})});
  drop.addEventListener('drop', function(e){
    var a = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
    if (a) leerArchivo(a);
  });
  // soltar fuera de la zona no debe abrir el archivo en la ventana
  ['dragover','drop'].forEach(function(n){window.addEventListener(n, function(e){e.preventDefault()})});

  api('iniciar').then(function(s){
    mostrarSesion(s);
    setInterval(vigilar, 2000); setInterval(relojBanner, 1000); vigilar();
    if (!s.compartida_ok) toast('Sin acceso a la carpeta compartida: solo podrá crear borradores.');
    else if (s.aviso) toast(s.aviso);
    return s.hay_entrega ? recargarCampana(false) : recargarCampana(false);
  }).then(function(){
    pintarNav();
  }).catch(falla);
}
if (window.__apiFalsa || (window.pywebview && window.pywebview.api)) iniciar();
else window.addEventListener('pywebviewready', iniciar);
setTimeout(function(){if (!E && !window.__arrancado && !(window.pywebview && window.pywebview.api) && !window.__apiFalsa)
  $('u-con').textContent = 'Abra la aplicación desde main.py'}, 3000);
