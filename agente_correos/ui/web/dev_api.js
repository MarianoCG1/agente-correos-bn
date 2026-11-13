/* Api de ejemplo para revisar la interfaz en un navegador (index.html?dev). No se usa dentro del programa. */
(function(){
  'use strict';
  function ok(d){return Promise.resolve({ok:true, datos:d})}
  function mal(m){return Promise.resolve({ok:false, error:m})}
  var NOMBRES = ['AREQUIPA','CUSCO','JULIACA','HUANCAYO','IQUITOS','AYACUCHO','PUNO','PIURA','TACNA','CAJAMARCA','TRUJILLO','CHICLAYO'];
  var FECHAS = (function(){
    var f = [], d = new Date('2026-09-04T00:00:00Z');
    while (d <= new Date('2026-10-19T00:00:00Z')){ if (d.getUTCDay() !== 0) f.push(d.toISOString().slice(0, 10)); d.setUTCDate(d.getUTCDate() + 1); }
    return f;
  })();
  var DIA = ['DOM','LUN','MAR','MIÉ','JUE','VIE','SÁB'];
  var AVISO = {};
  FECHAS.forEach(function(f){
    var d = new Date(f + 'T00:00:00Z');
    do { d.setUTCDate(d.getUTCDate() - 1); } while (d.getUTCDay() === 0 || d.getUTCDay() === 6);
    AVISO[f] = d.toISOString().slice(0, 10);
  });
  var PAGOS = NOMBRES.map(function(_, i){
    var idx = [], k = FECHAS.indexOf('2026-10-14');
    for (var j = 0; j < FECHAS.length; j++) if ((j * 7 + i * 3) % 9 === 0 || j === k && i % 4 !== 3) idx.push(j);
    return idx;
  });
  var ags = NOMBRES.map(function(n, i){
    return {nombre:n, nombre_ok:true, para:['jpago_' + n.toLowerCase() + '@bn.com.pe'], cc:['admin_' + n.toLowerCase() + '@bn.com.pe'],
            activa:true, nota:'', sin:(n === 'TACNA'), etv:(i % 2 ? 'PROSEGUR' : 'HERMES')};
  });
  var hist = [{fecha:'13/10/2026', hora:'08:42', usuario:'jrojas', agencia:'PIURA', tipo:'Recordatorio · pago 14/10', estado:'borr', detalle:'respuesta'}];
  var cfg = {por_encargo_nombre:'Luis Fernández Rojas', por_encargo_cargo:'Jefe de Caja y Valores', correos_excluidos:['lfernandez@bn.com.pe'], copia_fija:['lfernandez@bn.com.pe', 'analista1@bn.com.pe', 'analista2@bn.com.pe'],
             dominio_interno:'bn.com.pe', feriados:[], minutos_anulacion:2, cronograma_path:'//srv/…/ENTREGA DE FONDOS ETV JA 2026 difusion.xlsx',
             carpeta_original:'', carpeta_entrega:'//srv/…/ENTREGA DE FONDOS', respaldo_path:'//srv/…/BACKUP_CORREOS', carpeta_compartida:'//srv/…/BACKUP_CORREOS/_PROGRAMA', agencias_path:''};
  var perfil = {nombre:'Ana Pérez Quispe', cargo:'Practicante', dependencia:'Sección Caja y Valores en Custodia | Sub Gerencia Caja y Valores | Gerencia de Operaciones | BN',
                telefono:'519-2000', anexo:'12345', direccion:'Oficina Principal del BN – San Borja', email:'pra_aperez@bn.com.pe',
                mostrar_email:true, aviso_confidencial:false, logo_path:'', modo_firma:'app'};
  function firma(p){
    return '<table cellpadding="0" cellspacing="0" style="font-family:Calibri,Arial;font-size:11pt"><tr><td style="padding-right:14px"><div style="width:90px;height:60px;background:#F6D6DA;color:#9A0C23;display:flex;align-items:center;justify-content:center;font-weight:700">60 años</div></td>' +
      '<td style="border-left:1px solid #000;padding-left:14px"><b>' + (p.cargo ? p.cargo + ' - ' : '') + p.nombre + '</b><br>' + p.dependencia + '<br>Telf: ' + p.telefono +
      ' Anexo <b>' + p.anexo + '</b><br>' + p.direccion + (p.mostrar_email ? '<br>E-mail: <b>' + p.email + '</b>' : '') + '</td></tr></table>';
  }
  var lotes = {};
  var ajAuto = {activo:false, hora:'08:00', accion:'enviar', cuenta_s:45, verificar_enviados:true}, autoSale = 0, autoEnvio = 0;
  var vig = {sync:{activa:true, ultima:'2026-10-13T08:12:00', nuevos_total:0, error:'', resumen:'48 correos revisados', revisando:false},
             auto:{activo:false, hora:'08:00', accion:'enviar', fase:'inactivo', mensaje:'', prueba:false, sale_en:null, listos:[], descartados:[],
                   ya_avisados:0, lote:null, avance:null, anulable_hasta:null, resumen:{}, fecha_hecha:null}};

  window.__apiFalsa = {
    iniciar: function(){return ok({usuario:'aperez', nombre:perfil.nombre, hoy:'2026-10-13', hoy_largo:'martes 13 de octubre de 2026',
      outlook:true, compartida:cfg.carpeta_compartida, compartida_ok:true, perfil_completo:true, hay_entrega:true, hay_agencias:true, minutos_anulacion:cfg.minutos_anulacion,
      version:'2.0.0-beta', usuario:'aperez', equipo:'PC-DEMO', agencias_n:ags.length, entrega_archivo:'ENTREGA DE FONDOS ETV JA 2026 difusion.xlsx'})},

    estado_campana: function(){
      var fechas = FECHAS.map(function(f){var d = new Date(f + 'T00:00:00'); return {fecha:f, aviso:AVISO[f], dia:DIA[d.getDay()], d:f.slice(8) + '/' + f.slice(5, 7),
        largo:DIA[d.getDay()].toLowerCase() + ' ' + parseInt(f.slice(8), 10) + ' de octubre de 2026'}});
      return ok({campana:'JULIO – AGOSTO 2026', coherencia:null, archivo:'ENTREGA DE FONDOS ETV JA 2026 difusion.xlsx', hoy:'2026-10-13',
        hoy_largo:'martes 13 de octubre', objetivo:'2026-10-14', objetivo_largo:'miércoles 14 de octubre', aviso_objetivo:'2026-10-13', fechas:fechas,
        hay_respaldos:true, hoja:'CRONOGRAMA ETV', hay_agencias:location.search.indexOf('sinag') < 0,
        agencias: ags.filter(function(a){return a.activa}).map(function(a, i){
          var celdas = {inicio: a.sin ? {estado:'bloq', motivo:'Sin correo registrado'} :
            (a.nombre === 'IQUITOS' || a.nombre === 'PUNO') ? {estado:'hoy', motivo:'Debe prepararse: correo de inicio de la campaña'} :
            {estado:'env', motivo:'Respaldo del inicio del 07/09/2026'}};
          (PAGOS[i] || []).forEach(function(k){
            var f = FECHAS[k], av = AVISO[f], est = a.sin ? 'bloq' : f === '2026-10-14' ? 'hoy' : av < '2026-10-13' ? 'venc' : 'pend';
            if (!a.sin && av < '2026-10-13' && i % 3) est = 'env';
            celdas[f] = {estado:est, motivo: est === 'env' ? 'Enviado por aperez el ' + av.slice(8) + '/10/2026 09:10' :
              est === 'bloq' ? 'Sin correo registrado' : est === 'hoy' ? 'Debe prepararse hoy' : est === 'venc' ? 'La fecha pasó y no hay registro (puede haberse enviado antes de v2)' : 'Se preparará el ' + av};
          });
          if (a.nombre === 'PIURA') celdas['2026-10-14'] = {estado:'borr', motivo:'Borrador en Outlook por jrojas el 13/10/2026 08:42'};
          if (a.nombre === 'JULIACA') celdas['2026-10-14'] = {estado:'omit', motivo:'Enviado por jrojas el 13/10/2026 08:10'};
          return {nombre:a.nombre, etvs:[a.etv], celdas:celdas, para:a.sin ? [] : a.para, cc:a.sin ? [] : a.cc, sin_correo:a.sin,
                  motivo_bloqueo:a.sin ? 'Sin correo registrado' : '', n_filas:5};
        })});
    },

    preparar_revision: function(tipo){
      if (tipo === 'inicio'){
        var fi = ags.filter(function(a){return a.activa}).map(function(a){
          var base = {agencia:a.nombre, veredicto:'lista', motivo:'', advertencias:[], n_filas:5, para:a.para, cc:a.cc, hilo:{estado:'no_aplica', candidatos:[]}};
          if (a.sin){base.veredicto = 'bloqueada'; base.motivo = 'Sin correo registrado en la lista de agencias'; base.para = []}
          else if (a.nombre !== 'IQUITOS' && a.nombre !== 'PUNO'){base.veredicto = 'omitida'; base.motivo = 'Ya hay respaldo del inicio del 07/09/2026 (versión anterior u otra persona)'}
          return base;
        });
        return ok({tipo:'inicio', fecha:null, filas:fi, minutos_anulacion:cfg.minutos_anulacion, confirmacion_lectura:cfg.confirmacion_lectura !== false});
      }
      var filas = ags.filter(function(a){return a.activa}).slice(0, 8).map(function(a, i){
        var base = {agencia:a.nombre, veredicto:'lista', motivo:'', advertencias:[], n_filas:3, para:a.para, cc:a.cc, hilo:{estado:'unico', candidatos:[]}};
        if (a.sin) {base.veredicto = 'bloqueada'; base.motivo = 'Sin correo registrado en la lista de agencias'; base.para = []; base.hilo = {estado:'no_aplica', candidatos:[]}}
        if (a.nombre === 'HUANCAYO'){base.veredicto = 'revisar'; base.motivo = 'Hay 2 hilos posibles: elija uno';
          base.hilo = {estado:'ambiguo', candidatos:[{id:'H1', asunto:'', enviado_en:'28/09/2026 09:14', almacen:'Buzón personal'}, {id:'H2', asunto:'', enviado_en:'29/09/2026 16:02', almacen:'Caja y Valores'}]}}
        if (a.nombre === 'JULIACA'){base.veredicto = 'omitida'; base.motivo = 'Ya se envió el 13/10/2026 08:10 (jrojas)'}
        if (a.nombre === 'IQUITOS'){base.hilo = {estado:'ninguno', candidatos:[]}}
        if (a.nombre === 'CUSCO'){base.advertencias = ['1 fila(s) sin importe de Pensión 65']}
        return base;
      });
      return ok({tipo:'recordatorio', fecha:'2026-10-14', filas:filas, minutos_anulacion:cfg.minutos_anulacion, confirmacion_lectura:cfg.confirmacion_lectura !== false});
    },

    vista_previa: function(agencia, tipo){
      var tabla = '<table style="border-collapse:collapse;font-size:8pt;width:100%"><tr><td style="background:#FF9999;border:1px solid #ccc;padding:2px">Departamento</td><td style="background:#FF9999;border:1px solid #ccc">Distrito</td><td style="background:#FFFF99;border:1px solid #ccc">Importe</td><td style="background:#00B0F0;border:1px solid #ccc">Fecha</td></tr>' +
        '<tr><td style="border:1px solid #ccc">APURIMAC</td><td style="border:1px solid #ccc">EL PORVENIR</td><td style="background:#FFFF00;font-weight:bold;border:1px solid #ccc">67,920.00</td><td style="background:#FFFF00;font-weight:bold;border:1px solid #ccc">14/10/26</td></tr></table>';
      return ok({asunto:(tipo === 'inicio' ? '' : 'RECORDATORIO: ') + 'Programación de Fondos – BN ' + agencia + ' – JULIO – AGOSTO 2026', modo:(tipo === 'inicio' ? 'nuevo' : 'respuesta'), advertencias:[],
        para:(tipo === 'inicio' ? ['jpago_' + agencia.toLowerCase() + '@bn.com.pe'] : []), cc:(tipo === 'inicio' ? ['admin_' + agencia.toLowerCase() + '@bn.com.pe'].concat(cfg.copia_fija || []) : []), adjunto:{nombre:'ENTREGA DE FONDOS ETV JA 2026 difusion.xlsx', filas:5}, firma:'app',
        html:'<html><body style="font-family:Calibri,Arial;font-size:11pt;margin:12px"><div><p>Estimado(a) buenos días,<br><b>BN – ' + agencia + '</b></p>' +
          (tipo === 'inicio' ?
            '<p>Por encargo del Sr. <b>Luis Fernández Rojas - Jefe de Caja y Valores</b>, y por medio de la presente, se solicita programar la entrega de fondos, que inicia el <b style="background:yellow">MARTES 14 DE OCTUBRE DE 2026</b>, con el fin de realizar los pagos a los usuarios de los Programas Sociales <b>PENSIÓN 65</b> y <b>JUNTOS</b>, les recordamos entregar los fondos a las ETV correspondientes a la campaña de pagos JULIO – AGOSTO 2026.</p>' +
            '<p><b style="color:#C00000">Se adjunta archivo en formato Excel con la programación detallada de la presente campaña.</b></p>' :
            '<p>Se le recuerda que para el día de mañana <b style="background:yellow">14 de octubre de 2026</b>, se debe programar la entrega de fondos a la ETV indicada.</p>') + tabla + '<br>' + firma(perfil) + '</div></body></html>'});
    },
    enviarme_prueba: function(){return ok({enviado_a:'pra_aperez@bn.com.pe'})},

    confirmar_envio: function(sel, accion){
      var id = 'L' + Date.now(), t0 = Date.now();
      lotes[id] = {t0:t0, sel:sel, accion:accion};
      return ok({lote:id, total:sel.length});
    },
    progreso: function(id){
      var l = lotes[id], n = l.sel.length, hechos = Math.min(n, Math.floor((Date.now() - l.t0) / 500)), fin = hechos >= n;
      return ok({hechos:hechos, total:n, actual:l.sel[Math.min(hechos, n - 1)].agencia, terminado:fin, error:'', accion:l.accion,
        resultados: fin ? l.sel.map(function(s, i){return {agencia:s.agencia, estado:l.accion === 'enviar' ? 'env' : 'borr', estado_real:'enviado',
          detalle:'', modo:i % 3 === 0 ? 'reconstruido' : 'respuesta', para:'x@bn.com.pe', advertencias:i === 1 ? ['No se pudo guardar el respaldo en la red: sin acceso'] : []}}) : [],
        anulable_hasta: fin && l.accion === 'enviar' ? new Date(l.t0 + n * 500 + 120000).toISOString() : null});
    },
    cancelar_envio: function(){return ok(true)},
    anular_envio: function(){return ok({anulados:3, solicitados:3})},

    historial: function(ag, est, q){
      var f = hist.filter(function(h){return (!ag || h.agencia === ag) && (!est || h.estado === est) && (!q || (h.agencia + h.usuario + h.detalle).toUpperCase().indexOf(q.toUpperCase()) >= 0)});
      return ok({campana:'JULIO – AGOSTO 2026', total:hist.length, filas:f});
    },

    entrega_elegir_original: function(){return ok({cancelado:true})},
    entrega_subir_original: function(nombre){
      var puntos = [];
      for (var i = 0; i < 60; i++) puntos.push({clave:('0000' + (600 + i)).slice(-4) + '|0' + (700 + i), agencia:NOMBRES[i % 12], distrito:'DISTRITO ' + (i + 1),
        punto:'C.P. PUNTO ' + (i + 1), fecha:'2026-10-' + ('0' + (5 + i % 20)).slice(-2), etv:i % 2 ? 'PROSEGUR' : 'HERMES', sugerido:i % 9 === 0});
      return ok({token:'T1', nombre:nombre, campana:'JULIO – AGOSTO 2026', coherencia:null, filas:320, agencias:18, puntos:puntos,
        nombre_sugerido:nombre.replace(/CRONOGRAMA ETV/i, 'ENTREGA DE FONDOS ETV'), carpeta_sugerida:'//srv/…/ENTREGA DE FONDOS',
        campos:['Fecha_Pago', 'Hora_Pago', 'Fecha_Entrega', 'Hora_Entrega']});
    },
    entrega_elegir_destino: function(n){return ok({ruta:'D:/ENTREGA DE FONDOS/' + n, cancelado:false})},
    entrega_generar: function(t, d, sus){return ok({destino:d, filas_original:320, filas_entrega:320 - sus.length, filas_quitadas:sus.length,
      importe_original:17164950, importe_entrega:16921145, columnas_quitadas:['Categoría', 'Cod', 'Días de anticip.'], bitacora:d + '.cambios.json', vigente:true})},

    config_obtener: function(){
      return ok({valores:cfg, compartida:cfg.carpeta_compartida, compartida_ok:true,
        rutas:[['cronograma_path','Entrega vigente (alimenta los correos)','ok'],['carpeta_original','Carpeta del cronograma original','sin_configurar'],
               ['carpeta_entrega','Carpeta donde se guarda la entrega generada','ok'],['respaldo_path','Respaldo de correos (BACKUP_CORREOS)','ok'],
               ['carpeta_compartida','Carpeta compartida del programa (registro, agencias, perfiles)','ok'],['agencias_path','Excel de origen de la lista de agencias','sin_configurar']]
          .map(function(r){return {campo:r[0], etiqueta:r[1], valor:cfg[r[0]] || '', estado:r[2], detalle:'', alcance:(r[0] === 'respaldo_path' ? 'compartida' : 'equipo')}}),
        historial:[{cuando:'2026-10-13T08:40:12', usuario:'aperez', campo:'respaldo_path', antes:'', despues:cfg.respaldo_path}]});
    },
    config_guardar: function(v){Object.keys(v).forEach(function(k){cfg[k] = v[k]}); return ok({cambios:1})},
    config_elegir_ruta: function(){return ok({ruta:'D:/ENTREGAS', cancelado:false})},
    perfil_obtener: function(){return ok({perfil:perfil, detectado_de:'perfil', logo:'', vista_logo:null, firma_html:firma(perfil)})},
    perfil_guardar: function(v){Object.assign(perfil, v); return ok({guardado:true})},
    firma_vista_previa: function(v){return ok({html:firma(v)})},

    agencias_listar: function(){return ok({agencias:ags.map(function(a){return {nombre:a.nombre, para:a.para, cc:a.cc, activa:a.activa, nota:a.nota}}), importable:true})},
    agencia_agregar: function(n, para, cc){
      if (!para.length) return mal('Para: debe tener al menos un correo.');
      if (/gmail/.test(para.join())) return mal('Para: fuera de @bn.com.pe (' + para.join(', ') + ').');
      ags.push({nombre:n, para:para, cc:cc, activa:true, nota:'', sin:false, etv:'HERMES'}); return ok({agencia:n});
    },
    agencia_actualizar: function(n, para, cc){var a = ags.filter(function(x){return x.nombre === n})[0]; a.para = para; a.cc = cc; return ok({agencia:n})},
    entrega_cambiar: function(r){return ok({archivo:'ENTREGA DE FONDOS ETV SO 2026 difusion.xlsx', campana:'SEPTIEMBRE – OCTUBRE 2026'})},
    entrega_usar_existente: function(){return ok({cancelado:false, archivo:'ENTREGA DE FONDOS ETV JA 2026 difusion.xlsx', campana:'JULIO – AGOSTO 2026'})},
    diagnostico_exportar: function(){return ok({cancelado:false, ruta:'C:\Users\demo\Desktop\Diagnostico.zip'})},
    agencia_eliminar: function(n){ags = ags.filter(function(x){return x.nombre !== n}); return ok({agencia:n})},
    agencia_estado: function(n, act){ags.filter(function(x){return x.nombre === n})[0].activa = act; return ok({agencia:n, activa:act})},
    agencias_historial: function(){return ok({cambios:[{cuando:'2026-10-13T09:00:00', usuario:'aperez', agencia:'CUSCO', campo:'para', antes:'a@bn.com.pe', despues:'jpago_cusco@bn.com.pe'}]})},
    agencias_importar: function(){return ok({agregadas:[], actualizadas:[], sin_cambio:NOMBRES, rechazadas:{}, origen:'data/agencias_correos.xlsx'})},

    // ---- segundo plano (simulado: la cuenta regresiva y el envío avanzan con el reloj del navegador)
    vigilancia_estado: function(){
      var a = vig.auto, ahora = Date.now();
      if (a.fase === 'cuenta' && ahora >= autoSale){
        a.fase = 'enviando'; autoEnvio = ahora; a.sale_en = null; a.lote = 'LA1';
      }
      if (a.fase === 'enviando'){
        var h = Math.min(a.listos.length, Math.floor((ahora - autoEnvio) / 600));
        a.avance = {hechos:h, total:a.listos.length};
        if (h >= a.listos.length){
          a.fase = 'hecho'; a.mensaje = a.accion === 'borrador' ? a.listos.length + ' borradores creados' : a.listos.length + ' enviados';
          a.resumen = {enviados:a.listos.length, omitidos:0, problemas:0};
          a.anulable_hasta = a.accion === 'enviar' ? new Date(ahora + 120000).toISOString() : null;
        }
      }
      if (a.fase === 'cuenta') a.sale_en = Math.max(0, Math.round((autoSale - ahora) / 1000));
      return ok(JSON.parse(JSON.stringify(vig)));
    },
    auto_ajustes_obtener: function(){return ok(Object.assign({}, ajAuto))},
    auto_ajustes_guardar: function(v){
      if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(v.hora)) return mal('La hora debe tener el formato HH:MM, por ejemplo 08:00.');
      Object.assign(ajAuto, v); vig.auto.activo = v.activo; vig.auto.hora = v.hora; vig.sync.activa = v.verificar_enviados;
      if (vig.auto.fase === 'inactivo' && v.activo) {vig.auto.fase = 'espera'; vig.auto.mensaje = 'Hoy se prepararán los recordatorios a las ' + v.hora + '.'}
      if (!v.activo && vig.auto.fase === 'espera') {vig.auto.fase = 'inactivo'; vig.auto.mensaje = ''}
      return ok(Object.assign({}, ajAuto));
    },
    auto_probar: function(){
      var a = vig.auto, n = 5;
      a.fase = 'cuenta'; a.prueba = true; a.accion = ajAuto.accion; a.mensaje = '';
      a.listos = NOMBRES.slice(0, n).map(function(x){return {agencia:x, fecha:'2026-10-14'}});
      a.descartados = [{agencia:NOMBRES[6], fecha:'2026-10-14', motivo:'Tiene advertencias: 2 fila(s) sin importe de Pensión 65'},
                       {agencia:NOMBRES[7], fecha:'2026-10-14', motivo:'No se encontró el correo de inicio de la campaña para responderlo'}];
      autoSale = Date.now() + ajAuto.cuenta_s * 1000; a.sale_en = ajAuto.cuenta_s; a.anulable_hasta = null; a.avance = null;
      return ok(a);
    },
    auto_cancelar: function(){var a = vig.auto; a.fase = 'cancelado'; a.mensaje = 'Cancelado por la persona: no se envió nada.'; a.sale_en = null; return ok(a)},
    auto_enviar_ya: function(){autoSale = Date.now(); return ok(vig.auto)},
    auto_descartar: function(){var a = vig.auto; a.fase = ajAuto.activo ? 'espera' : 'inactivo'; a.mensaje = ''; a.listos = a.descartados = []; a.lote = null; a.anulable_hasta = null; return ok(a)},
    enviados_revisar: function(){
      vig.sync.ultima = new Date().toISOString().slice(0, 19); vig.sync.nuevos_total += 2; vig.sync.resumen = '48 correos revisados, 2 avisos nuevos anotados';
      return ok({resumen:vig.sync.resumen, nuevos_total:vig.sync.nuevos_total});
    }
  };
})();
