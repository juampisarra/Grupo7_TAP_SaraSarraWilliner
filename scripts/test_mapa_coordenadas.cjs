// Interacciones y transporte simulados. No consulta ni escribe servicios reales.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

class Elemento {
    constructor(tag = 'div') {
        this.tag = tag; this.children = []; this.eventos = {}; this.attributes = {};
        this.dataset = {}; this.style = {}; this.value = ''; this.hidden = false;
        this.checked = false; this._text = ''; this._html = ''; this.className = '';
        const clases = () => new Set(this.className.split(' ').filter(Boolean));
        this.classList = {
            add: (...valores) => { const c = clases(); valores.forEach(v => c.add(v)); this.className = [...c].join(' '); },
            remove: (...valores) => { const c = clases(); valores.forEach(v => c.delete(v)); this.className = [...c].join(' '); },
            contains: v => clases().has(v),
            toggle: (v, activo) => { const c = clases(); (activo ?? !c.has(v)) ? c.add(v) : c.delete(v); this.className = [...c].join(' '); },
        };
    }
    set textContent(valor) { this._text = String(valor); this.children = []; }
    get textContent() { return this._text + this.children.map(h => h.textContent).join(''); }
    set innerHTML(valor) { this._html = valor; this.children = []; }
    get innerHTML() { return this._html; }
    get outerHTML() {
        const escapar = t => String(t).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');
        return '<' + this.tag + ' class="' + escapar(this.className) + '">' + this._html + escapar(this._text) + this.children.map(h => h.outerHTML).join('') + '</' + this.tag + '>';
    }
    append(...hijos) { this.children.push(...hijos); }
    appendChild(hijo) { this.children.push(hijo); return hijo; }
    replaceChildren(...hijos) { this._text = ''; this._html = ''; this.children = hijos; }
    addEventListener(nombre, fn) { this.eventos[nombre] = fn; }
    setAttribute(nombre, valor) { this.attributes[nombre] = String(valor); }
    getAttribute(nombre) { return this.attributes[nombre]; }
    removeAttribute(nombre) { delete this.attributes[nombre]; }
    contains(target) { return this === target || this.children.some(h => h.contains(target)); }
    getBoundingClientRect() { return { height: 118 }; }
}
function entorno() {
    const elementos = new Map(), marcadores = [];
    const porId = id => { if (!elementos.has(id)) elementos.set(id, new Elemento()); return elementos.get(id); };
    porId('map-config').textContent = JSON.stringify({ maptilerApiKey: 'prueba' });
    const tipos = ['Casa','Campo','Nave Industrial'].map(tipo => {
        const b = new Elemento('button'); b.dataset.filterTipo = tipo;
        b.dataset.disponibleAlquiler = 'true'; b.dataset.disponibleVenta = 'true'; return b;
    });
    const comodidades = ['Cochera','Patio'].map(tipo => { const b = new Elemento('button'); b.dataset.filterCaracteristica = tipo; return b; });
    const estilos = ['calles', 'oscuro', 'satelite'].map(nombre => {
        const b = new Elemento('button'); b.dataset.estiloMapa = nombre; return b;
    });
    const eventosDocumento = {};
    const mapa = {
        eventos: {}, zoom: 19, on(nombre, fn) { this.eventos[nombre] = fn; },
        latLngToContainerPoint: punto => ({ x: punto[1] * 100000, y: punto[0] * 100000 }),
        project: punto => ({ x: punto[0] * 100000, y: punto[1] * 100000 }),
        panTo(p) { this.centro = p; }, easeTo(p) { this.centro = p.center; },
        getZoom() { return this.zoom; }, fitBounds(bounds, opciones) { this.bounds = bounds; this.opcionesBounds = opciones; },
        getCenter() { return { lat: -31.25, lng: -61.49 }; },
        controles: [], addControl(control, posicion) { this.controles.push({ control, posicion }); },
        getLayer() { return false; }, addSource(id, dato) { this.source = dato; },
        getStyle() { return { layers: [{ id: 'etiquetas', type: 'symbol', layout: { 'text-field': 'name' } }] }; },
        addLayer(capa) { this.capa = capa; },
    };
    const marcador = (coordenadas, opciones = {}) => {
        const m = { coordenadas, opciones, eventos: {}, eliminado: false,
            on(nombre, fn) { this.eventos[nombre] = fn; return this; },
            addTo() { return this; }, remove() { this.eliminado = true; },
            getElement() { return this.opciones.element || null; },
            setLngLat(p) { this.coordenadas = p; return this; },
        };
        marcadores.push(m); return m;
    };
    const popup = () => ({
        setLatLng(p) { this.punto = p; return this; }, setLngLat(p) { this.punto = p; return this; },
        setContent(e) { this.contenido = e; return this; }, setDOMContent(e) { this.contenido = e; return this; },
        openOn() { return this; }, addTo() { return this; }, remove() { this.eliminado = true; },
    });
    const contexto = {
        document: { readyState: 'loading', addEventListener(nombre, fn) { eventosDocumento[nombre] = fn; }, getElementById: porId,
            createElement: tag => new Elemento(tag),
            querySelector(selector) { return selector === '#estilos-menu summary' ? porId('estilos-summary') : null; },
            querySelectorAll(selector) { return selector === '[data-filter-tipo]' ? tipos : selector === '[data-filter-caracteristica]' ? comodidades : selector === '[data-estilo-mapa]' ? estilos : []; } },
        window: { location: { origin: 'http://localhost' } }, URL, URLSearchParams, AbortController,
        setTimeout, clearTimeout, console,
        L: { map: () => mapa, control: { zoom: () => ({ addTo() {} }) },
            tileLayer: () => ({ addTo() {} }),
            featureGroup: () => ({ addTo() { return this; }, clearLayers() {}, addLayer() {} }),
            divIcon: o => o, marker: marcador, popup, latLngBounds: puntos => puntos },
    };
    contexto.window.maplibregl = {
        Map: function(opciones) { mapa.opciones = opciones; return mapa; }, NavigationControl: function() {},
        Marker: function(o) { return marcador([], o); }, Popup: function() { return popup(); },
        LngLatBounds: function() { this.extend = () => this; },
    };
    let codigo = fs.readFileSync('propiedades/static/propiedades/mapa.js', 'utf8');
    codigo = codigo.replace(/\}\)\(\);\s*$/, 'globalThis.prueba = { state, MapManager, CardManager, PropertyApiClient, UI, crearParametros, agruparMarcadores, formatearPrecio, iconoTipo }; })();');
    vm.runInNewContext(codigo, contexto);
    return { ...contexto.prueba, contexto, elementos, marcadores, tipos, comodidades, estilos, eventosDocumento, mapa, porId };
}
const base = {
    latitud: -31.25, longitud: -61.49, tipo: 'Casa', direccion: 'Necochea 142', fuente: 'Gaggiotti',
    fotos: [], caracteristicas: '', dormitorios: null, ambientes: null, banos: null,
    alquiler: { disponible: true, precio: '500000.00', moneda: 'ARS' }, ubicacion_aproximada: null,
};
const respuesta = data => ({ ok: true, status: 200, json: async () => data });

async function main() {
    const e = entorno();
    e.mapa.zoom = 18; // Los grupos que todavía se solapan abren la columna sin más zoom automático.
    const avisos = [{ ...base, id: 1 }, { ...base, id: 2, direccion: '<img src=x onerror=alert(1)>' },
        { ...base, id: 3, latitud: -31.250001 }, { ...base, id: 4, latitud: -31.26 }];
    const original = JSON.stringify(avisos);
    e.MapManager.init(); e.state.propiedades = avisos;
    e.MapManager.renderizarMarcadores(avisos);
    assert.equal(e.MapManager.marcadores.length, 2, 'Agrupa etiquetas próximas y puntos idénticos');
    assert.equal(JSON.stringify(avisos), original, 'No cambia coordenadas ni otros datos');
    assert.equal(e.MapManager.markerMap.get(1), e.MapManager.markerMap.get(3));
    assert.deepEqual(Array.from(e.MapManager.marcadores[0].coordenadas), [-31.25, -61.49], 'El ancla es un punto real');
    e.MapManager.marcadores[0].eventos.click();
    const botones = e.MapManager.popup.contenido.children[1].children;
    assert.equal(botones.length, 3);
    assert.ok(botones[1].title.includes('<img'), 'La dirección se conserva como texto en la descripción del botón');
    assert.equal(botones[1].innerHTML, '', 'Texto del aviso no se interpreta como HTML');
    botones[1].eventos.click({ stopPropagation() {} });
    assert.ok(e.porId('card-location-precision').textContent.includes('desconocida'));
    e.CardManager.mostrar({ ...base, id: 5, caracteristicas: '<img src=x onerror=alert(1)>',
        ubicacion_info: { precision: 'geocodificada_direccion' } });
    assert.ok(e.porId('card-location-precision').textContent.includes('no garantiza'));
    assert.equal(e.porId('card-features').children[0].innerHTML, '');
    assert.equal(e.formatearPrecio({ ...base, alquiler: { disponible: true, precio: '0.00', moneda: 'ARS' } }, 'alquiler'), '$ 0');

    const iconos = ['Casa','Chacra','Cochera','Consultorio','Departamento','Depósito','Galpón','Local','Nave Industrial','Oficina','PH','Quinta','Terreno','Campo'].map(e.iconoTipo);
    assert.equal(new Set(iconos).size, 14, 'Los tipos tienen dibujos diferentes');
    assert.ok(e.MapManager.marcadores[1].opciones.icon.html.includes('🏠'));
    assert.ok(e.MapManager.marcadores[1].opciones.icon.html.includes('$ 500 k'));

    e.UI.init();
    assert.ok(e.tipos[2].textContent.startsWith('🏗️'));
    e.PropertyApiClient.buscarPropiedades = () => { e.llamadas = (e.llamadas || 0) + 1; };
    e.tipos[2].eventos.click();
    e.comodidades[0].eventos.click(); e.comodidades[1].eventos.click();
    e.state.texto = 'luminoso';
    let params = e.crearParametros();
    assert.equal(params.get('tipo'), 'Nave Industrial');
    assert.equal(params.get('q'), 'luminoso con cochera y patio');
    e.MapManager.elegirPunto({ lat: 0, lng: 0 });
    params = e.crearParametros();
    assert.equal(params.get('latitud'), '0'); assert.equal(params.get('radio_m'), '1000');
    e.porId('distancia').eventos.change({ target: { value: '2000' } });
    assert.equal(e.crearParametros().get('radio_m'), '2000');
    e.state.radio = 5000; assert.throws(() => e.crearParametros(), /2 km/); e.state.radio = 2000;
    e.porId('incluir-aproximadas').eventos.change({ target: { checked: true } });
    assert.equal(e.crearParametros().get('incluir_aproximadas'), '1');
    e.state.precioMax = '700000'; assert.equal(e.crearParametros().get('moneda'), 'ARS');
    e.porId('btn-op-venta').eventos.click();
    assert.equal(e.state.precioMax, '', 'Cambiar operación limpia el rango de otra moneda');
    e.state.precioMax = '100000'; assert.equal(e.crearParametros().get('moneda'), 'USD');
    e.UI.limpiarFiltros();
    assert.equal(e.state.punto, null); assert.equal(e.state.radio, 1000); assert.equal(e.state.texto, '');
    assert.equal(e.crearParametros().has('q'), false);

    const tiposOperacion = entorno();
    const [casa, campo, nave] = tiposOperacion.tipos;
    campo.dataset.disponibleVenta = 'false';
    nave.dataset.disponibleAlquiler = 'false';
    const consultasTipos = [];
    tiposOperacion.PropertyApiClient.buscarPropiedades = () => consultasTipos.push(tiposOperacion.crearParametros());
    tiposOperacion.UI.init();
    assert.deepEqual(tiposOperacion.tipos.map(b => b.hidden), [false, false, true], 'Alquilar oculta tipos disponibles solo en venta');
    assert.equal(nave.disabled, true);
    assert.equal(tiposOperacion.porId('tipos-vacios').hidden, true);
    nave.eventos.click();
    assert.equal(consultasTipos.length, 0, 'Un tipo oculto no activa una consulta');
    casa.eventos.click();
    tiposOperacion.state.texto = 'luminoso';
    tiposOperacion.state.caracteristicas.add('Patio');
    tiposOperacion.state.dormitorios = '2';
    tiposOperacion.state.punto = { lat: 0, lng: 0 };
    tiposOperacion.porId('tipos-menu').open = true;
    tiposOperacion.porId('btn-op-venta').eventos.click();
    assert.deepEqual(tiposOperacion.tipos.map(b => b.hidden), [false, true, false], 'Comprar cambia las opciones inmediatamente');
    assert.equal(tiposOperacion.state.tipo, 'Casa', 'Conserva un tipo disponible en ambas operaciones');
    assert.equal(casa.getAttribute('aria-pressed'), 'true');
    assert.equal(tiposOperacion.porId('tipos-menu').open, false);
    nave.eventos.click();
    const antesDeCambiar = consultasTipos.length;
    tiposOperacion.porId('btn-op-alquiler').eventos.click();
    assert.equal(consultasTipos.length, antesDeCambiar + 1, 'Limpiar un tipo incompatible no duplica búsquedas');
    assert.equal(tiposOperacion.state.tipo, null);
    assert.equal(tiposOperacion.porId('tipo-seleccionado').textContent, 'Todos los tipos');
    assert.equal(tiposOperacion.porId('btn-todos-tipos').getAttribute('aria-pressed'), 'true');
    assert.equal(nave.getAttribute('aria-pressed'), 'false');
    const trasCambiar = consultasTipos.at(-1);
    assert.equal(trasCambiar.get('operacion'), 'alquiler');
    assert.equal(trasCambiar.has('tipo'), false);
    assert.equal(trasCambiar.get('q'), 'luminoso con patio');
    assert.equal(trasCambiar.get('dormitorios'), '2');
    assert.equal(trasCambiar.get('latitud'), '0');
    campo.eventos.click();
    tiposOperacion.porId('btn-op-venta').eventos.click();
    assert.equal(tiposOperacion.state.tipo, null, 'También limpia un tipo exclusivo de alquiler al comprar');
    assert.equal(campo.hidden, true);
    assert.equal(nave.hidden, false);
    nave.eventos.click();
    tiposOperacion.UI.limpiarFiltros();
    assert.equal(tiposOperacion.state.tipo, null);
    assert.equal(nave.hidden, false, 'Limpiar mantiene la disponibilidad de la operación actual');
    assert.equal(campo.hidden, true);
    tiposOperacion.tipos.forEach(b => { b.dataset.disponibleAlquiler = 'false'; });
    tiposOperacion.porId('btn-op-alquiler').eventos.click();
    assert.ok(tiposOperacion.tipos.every(b => b.hidden && b.disabled));
    assert.equal(tiposOperacion.porId('tipos-vacios').hidden, false);
    assert.equal(tiposOperacion.porId('tipos-vacios').textContent, 'Sin tipos disponibles para alquilar.');
    tiposOperacion.tipos.forEach(b => { b.dataset.disponibleVenta = 'false'; });
    tiposOperacion.porId('btn-op-venta').eventos.click();
    assert.equal(tiposOperacion.porId('tipos-vacios').textContent, 'Sin tipos disponibles para comprar.');

    const api = entorno();
    const urls = [];
    api.contexto.fetch = async url => {
        urls.push(url);
        return respuesta(urls.length === 1 ? {
            total: 101, resultados: Array.from({ length: 100 }, (_, id) => ({ ...base, id })),
            siguiente: '/api/propiedades/?operacion=alquiler&pagina=2', advertencias: [],
        } : { total: 101, resultados: [{ ...base, id: 100, latitud: null }], siguiente: null, advertencias: [] });
    };
    await api.PropertyApiClient.buscarPropiedades();
    assert.equal(urls.length, 2, 'Sigue la paginación de la API');
    assert.equal(api.state.propiedades.length, 100);
    assert.equal(api.state.total, 101);
    assert.equal(api.porId('results-count').textContent, '101 avisos · 100 con ubicación');

    const error = entorno(); let peticiones = 0;
    error.state.texto = 'cochera';
    error.contexto.fetch = async () => { peticiones++; return { ok: false, status: 503, json: async () => ({ error: 'Elasticsearch no disponible' }) }; };
    await error.PropertyApiClient.buscarPropiedades();
    assert.equal(peticiones, 1, 'No hace búsqueda alternativa en el navegador');
    assert.equal(error.porId('search-error').hidden, false);
    assert.equal(error.porId('empty-results-banner').hidden, true); // No se mostró como cero coincidencias.
    assert.equal(error.porId('error-text').textContent, 'Elasticsearch no disponible');

    const invalida = entorno();
    invalida.contexto.fetch = async () => ({ ok: true, json: async () => { throw new SyntaxError('HTML en lugar de JSON'); } });
    await invalida.PropertyApiClient.buscarPropiedades();
    assert.equal(invalida.porId('error-text').textContent, 'El servidor no pudo responder. Esperá unos segundos y reintentá.');

    const carrera = entorno(); let resolverAnterior, resolverNueva;
    carrera.contexto.fetch = () => new Promise(resolve => {
        if (!resolverAnterior) resolverAnterior = resolve; else resolverNueva = resolve;
    });
    const anterior = carrera.PropertyApiClient.buscarPropiedades();
    carrera.state.texto = 'patio';
    const nueva = carrera.PropertyApiClient.buscarPropiedades();
    resolverAnterior(respuesta({ total: 1, resultados: [{ ...base, id: 7 }], siguiente: null }));
    await anterior;
    assert.equal(carrera.porId('loading-toast').hidden, false, 'La consulta cancelada no oculta la carga vigente');
    resolverNueva(respuesta({ total: 1, resultados: [{ ...base, id: 8 }], siguiente: null }));
    await nueva;
    assert.equal(carrera.state.propiedades[0].id, 8);
    assert.equal(carrera.porId('loading-toast').hidden, true);

    const gl = entorno();
    gl.porId('map').dataset.engine = 'maplibre';
    gl.MapManager.init(); gl.MapManager.agregarEdificios();
    assert.equal(gl.mapa.opciones.style, 'https://api.maptiler.com/maps/streets-v4/style.json?key=prueba');
    assert.equal(gl.mapa.source, undefined, 'Sin edificios en el estilo no carga fuentes de otro proveedor');
    gl.state.propiedades = [{ ...base, id: 10 }];
    gl.MapManager.renderizarMarcadores(gl.state.propiedades);
    assert.deepEqual(Array.from(gl.MapManager.marcadores[0].coordenadas), [-61.49, -31.25], 'MapLibre recibe longitud antes de latitud');
    assert.ok(gl.MapManager.marcadores[0].getElement().textContent.includes('$ 500 k'));

    const lateral = entorno();
    lateral.porId('map').dataset.engine = 'maplibre';
    lateral.MapManager.init();
    const compartidos = [{ ...base, id: 30 }, { ...base, id: 31, direccion: '<img src=x onerror=alert(1)>' }];
    const originales = JSON.stringify(compartidos);
    lateral.state.propiedades = compartidos;
    lateral.MapManager.renderizarMarcadores(compartidos);
    lateral.MapManager.abrirGrupo(compartidos);
    const globitos = lateral.MapManager.popup.contenido.children[1].children;
    assert.equal(globitos.length, 2, 'Cada aviso del punto tiene su globito');
    assert.ok(globitos.every(b => b.textContent.includes('$ 500 k')));
    assert.ok(globitos[1].getAttribute('aria-label').includes('<img'));
    assert.equal(globitos[1].innerHTML, '', 'Los datos del aviso no se interpretan como HTML');
    assert.deepEqual(Array.from(lateral.MapManager.popup.punto), [-61.49, -31.25]);
    globitos[1].eventos.click({ stopPropagation() {} });
    assert.equal(lateral.state.propiedadSeleccionada.id, 31);
    assert.deepEqual(Array.from(lateral.mapa.centro), [-61.49, -31.25]);
    assert.equal(lateral.MapManager.popup, null);
    assert.equal(JSON.stringify(compartidos), originales, 'La columna no desplaza coordenadas');

    [2, 5, 8, 18].forEach(cantidad => {
        lateral.MapManager.abrirColumna(Array.from({ length: cantidad }, (_, id) => ({ ...base, id })), 'prueba');
        assert.equal(lateral.MapManager.popup.contenido.children[1].children.length, cantidad,
            'Los grupos grandes conservan un botón por aviso');
    });
    lateral.mapa.eventos.movestart();
    assert.equal(lateral.MapManager.popup, null, 'Mover la cámara cierra la columna');
    lateral.MapManager.abrirGrupo(compartidos);
    lateral.MapManager.abrirGrupo(compartidos);
    assert.equal(lateral.MapManager.popup, null, 'Volver a pulsar el grupo cierra sus avisos');
    lateral.MapManager.abrirGrupo(compartidos);
    lateral.MapManager.popup.contenido.children[0].eventos.click({ stopPropagation() {} });
    assert.equal(lateral.MapManager.popup, null, 'El botón de cierre funciona');
    lateral.MapManager.abrirGrupo(compartidos);
    lateral.mapa.eventos.click({});
    assert.equal(lateral.MapManager.popup, null, 'Pulsar el fondo del mapa cierra la columna');

    const movil = entorno();
    movil.porId('map').getBoundingClientRect = () => ({ width: 390, top: 0 });
    movil.porId('filter-dock').getBoundingClientRect = () => ({ top: 690 });
    movil.contexto.document.querySelector = () => ({ getBoundingClientRect: () => ({ bottom: 140 }) });
    movil.porId('map').dataset.engine = 'maplibre'; movil.MapManager.init();
    movil.mapa.project = () => ({ x: 350, y: 410 });
    movil.MapManager.abrirColumna(compartidos, 'prueba');
    let posicion = movil.MapManager.ajustarColumna(base, movil.MapManager.popup.contenido);
    assert.equal(posicion.anchor, 'right', 'La columna prefiere la izquierda');
    movil.mapa.project = () => ({ x: 50, y: 410 });
    posicion = movil.MapManager.ajustarColumna(base, movil.MapManager.popup.contenido);
    assert.equal(posicion.anchor, 'left', 'Se abre a la derecha cerca del borde izquierdo');
    movil.mapa.project = () => ({ x: 195, y: 180 });
    movil.MapManager.abrirColumna(Array.from({ length: 18 }, (_, id) => ({ ...base, id })), 'prueba');
    assert.ok(parseFloat(movil.MapManager.popup.contenido.children[1].style.maxHeight) <= 510,
        'Los grupos grandes permiten desplazarse sin tapar cabecera/filtros');

    const zoom = entorno();
    zoom.porId('map').dataset.engine = 'maplibre';
    zoom.MapManager.init();
    zoom.mapa.zoom = 15;
    zoom.mapa.project = p => ({ x: p[0] * 100000 * 2 ** (zoom.mapa.zoom - 15), y: p[1] * 100000 * 2 ** (zoom.mapa.zoom - 15) });
    const distintos = [{ ...base, id: 40 }, { ...base, id: 41, longitud: -61.4895 }];
    zoom.state.propiedades = distintos;
    zoom.MapManager.renderizarMarcadores(distintos);
    assert.equal(zoom.MapManager.marcadores.length, 1);
    zoom.MapManager.abrirGrupo(distintos);
    assert.ok(zoom.mapa.bounds, 'Puntos distintos acercan la cámara');
    assert.equal(zoom.MapManager.popup, null, 'Los puntos distintos acercan el mapa sin expandir una columna');
    zoom.mapa.zoom = 19;
    zoom.mapa.eventos.moveend();
    assert.equal(zoom.MapManager.marcadores.length, 2, 'Se separan al aumentar el zoom');

    // Caso real de dos fuentes: misma dirección publicada con coordenadas distintas.
    const oficinas = entorno();
    oficinas.porId('map').dataset.engine = 'maplibre'; oficinas.MapManager.init();
    oficinas.mapa.zoom = 15.3;
    const bolivar = [
        { ...base, id: 750, tipo: 'Oficina', fuente: 'Gaggiotti', direccion: 'Bolivar 137 Planta Alta',
            latitud: -31.2497925953, longitud: -61.4925329646 },
        { ...base, id: 442, tipo: 'Oficina', fuente: 'Avantix', direccion: 'Bolivar al 137',
            latitud: -31.2497847077, longitud: -61.4925133504 },
    ];
    const datosOficinas = JSON.stringify(bolivar);
    oficinas.state.propiedades = bolivar;
    oficinas.MapManager.renderizarMarcadores(bolivar);
    assert.equal(oficinas.MapManager.marcadores.length, 1);
    assert.equal(oficinas.MapManager.marcadores[0].getElement().getAttribute('aria-label'), 'Elegir entre 2 avisos cercanos');
    oficinas.MapManager.abrirGrupo(bolivar);
    assert.equal(oficinas.mapa.bounds, undefined, 'Los puntos casi superpuestos abren sus avisos sin zoom automático');
    const opcionesOficinas = oficinas.MapManager.popup.contenido.children[1].children;
    assert.equal(opcionesOficinas.length, 2);
    assert.ok(opcionesOficinas[1].title.includes('Avantix'));
    assert.ok(oficinas.MapManager.popup.contenido.title.includes('cerca en esta vista'));
    assert.ok(!oficinas.MapManager.popup.contenido.title.includes('Comparten un punto'));
    opcionesOficinas[1].eventos.click({ stopPropagation() {} });
    assert.equal(oficinas.state.propiedadSeleccionada.id, 442);
    assert.deepEqual(Array.from(oficinas.mapa.centro), [bolivar[1].longitud, bolivar[1].latitud]);
    oficinas.MapManager.abrirGrupo(bolivar);
    oficinas.MapManager.popup.contenido.children[1].children[0].eventos.click({ stopPropagation() {} });
    assert.equal(oficinas.state.propiedadSeleccionada.id, 750);
    assert.deepEqual(Array.from(oficinas.mapa.centro), [bolivar[0].longitud, bolivar[0].latitud]);
    assert.equal(JSON.stringify(bolivar), datosOficinas, 'Se mantienen ambas identidades y coordenadas originales');

    const persistente = entorno();
    persistente.porId('map').dataset.engine = 'maplibre'; persistente.MapManager.init();
    persistente.mapa.zoom = 17;
    persistente.state.propiedades = distintos;
    persistente.MapManager.renderizarMarcadores(distintos);
    persistente.MapManager.abrirGrupo(distintos);
    assert.equal(persistente.mapa.opcionesBounds.maxZoom, 18, 'El zoom automático de grupos tiene un límite legible');
    persistente.mapa.zoom = 18;
    persistente.MapManager.abrirGrupo(distintos);
    assert.equal(persistente.MapManager.popup.contenido.children[1].children.length, 2,
        'Si continúan juntos en zoom 18 se usa la misma columna sin marco');
    persistente.mapa.zoom = 22;
    persistente.MapManager.abrirGrupo(distintos);
    assert.equal(persistente.MapManager.popup, null, 'Volver a tocar también cierra grupos de puntos distintos');

    const mt = entorno();
    mt.porId('map').dataset.engine = 'maplibre';
    mt.porId('map-config').textContent = JSON.stringify({ maptilerApiKey: 'prueba&otro=valor' });
    const capaBase = { id: 'Building', type: 'fill', source: 'maptiler_planet_v4', 'source-layer': 'building' };
    mt.mapa.getStyle = () => ({ layers: [capaBase] });
    mt.MapManager.init(); mt.MapManager.agregarEdificios();
    assert.equal(mt.mapa.opciones.style, 'https://api.maptiler.com/maps/streets-v4/style.json?key=prueba%26otro%3Dvalor');
    assert.equal(mt.mapa.source, undefined, 'Reutiliza las teselas del estilo MapTiler');
    assert.equal(mt.mapa.capa.source, 'maptiler_planet_v4', 'Edificios del mismo proveedor que el fondo');
    assert.ok(mt.mapa.capa.paint['fill-extrusion-height'].some(v => Array.isArray(v) && v[1] === 'height'));
    assert.equal(mt.mapa.capa.paint['fill-extrusion-height'].at(-1), 6, 'Altura de respaldo ilustrativa');
    const logo = mt.mapa.controles.find(c => c.posicion === 'bottom-left').control.onAdd();
    assert.equal(logo.children[0].children[0].alt, 'MapTiler', 'Conserva el logo exigido por el plan');

    const existente = entorno();
    existente.porId('map').dataset.engine = 'maplibre';
    existente.porId('map-config').textContent = JSON.stringify({ maptilerApiKey: 'prueba' });
    existente.mapa.getStyle = () => ({ layers: [capaBase,
        { ...capaBase, id: 'Building 3D', type: 'fill-extrusion', layout: { visibility: 'none' } }] });
    existente.mapa.setLayoutProperty = (id, nombre, valor) => { existente.visibilidad = { id, nombre, valor }; };
    existente.MapManager.init(); existente.MapManager.agregarEdificios();
    assert.equal(existente.visibilidad.valor, 'visible');
    assert.equal(existente.mapa.source, undefined);
    assert.equal(existente.mapa.capa, undefined, 'No duplica el 3D que ya contiene Streets v4');

    const selector = entorno();
    selector.porId('map').dataset.engine = 'maplibre';
    selector.porId('map-config').textContent = JSON.stringify({ maptilerApiKey: 'prueba' });
    const fuentePlanet = { type: 'vector', url: 'https://api.maptiler.com/tiles/planet-v4/tiles.json?key=prueba' };
    const calles = { version: 8, sources: { maptiler_planet_v4: fuentePlanet }, layers: [capaBase,
        { ...capaBase, id: 'Building 3D', type: 'fill-extrusion' }] };
    const oscuro = JSON.parse(JSON.stringify(calles));
    const satelite = { version: 8, sources: { satellite: { type: 'raster', tiles: ['https://api.maptiler.com/tiles/satellite/{z}/{x}/{y}.jpg?key=prueba'] } },
        layers: [{ id: 'satellite', source: 'satellite', type: 'raster' }] };
    selector.mapa.estilo = JSON.parse(JSON.stringify(calles));
    selector.mapa.getStyle = () => selector.mapa.estilo;
    selector.mapa.getLayer = id => selector.mapa.estilo.layers.find(c => c.id === id);
    selector.mapa.getSource = id => selector.mapa.estilo.sources[id];
    selector.mapa.addSource = (id, datos) => { selector.mapa.estilo.sources[id] = datos; };
    selector.mapa.addLayer = capa => selector.mapa.estilo.layers.push(capa);
    selector.mapa.setLayoutProperty = () => {};
    selector.mapa.getPitch = () => 45;
    selector.mapa.getBearing = () => -17;
    selector.mapa.jumpTo = camara => { selector.mapa.camara = camara; };
    selector.mapa.aplicaciones = 0;
    selector.mapa.setStyle = (estilo, opciones) => {
        selector.mapa.aplicaciones++;
        assert.equal(opciones.diff, false);
        selector.mapa.estilo = estilo;
        selector.mapa.eventos['style.load']();
    };
    const consultasEstilo = [];
    selector.contexto.fetch = async (url) => {
        consultasEstilo.push(url);
        const mapa = new URL(url).pathname.split('/')[2];
        assert.equal(new URL(url).hostname, 'api.maptiler.com');
        assert.equal(new URL(url).searchParams.get('key'), 'prueba');
        return respuesta(JSON.parse(JSON.stringify({ 'streets-v4': calles, 'streets-v4-dark': oscuro, 'hybrid-v4': satelite }[mapa])));
    };
    selector.MapManager.init(); selector.UI.init();
    selector.state.propiedades = [{ ...base, id: 800 }];
    selector.state.propiedadSeleccionada = selector.state.propiedades[0];
    selector.state.punto = { lat: 0, lng: 0 }; selector.state.radio = 2000;
    selector.state.tipo = 'Casa'; selector.state.texto = 'con patio';
    const estadoBusqueda = JSON.stringify(selector.crearParametros().toString());
    const datosAntes = JSON.stringify(selector.state.propiedades);
    assert.equal(selector.porId('estilo-seleccionado').textContent, 'Calles');
    selector.porId('estilos-menu').open = true;
    await selector.estilos[1].eventos.click();
    assert.equal(selector.porId('estilo-seleccionado').textContent, 'Oscuro');
    assert.equal(selector.estilos[1].getAttribute('aria-pressed'), 'true');
    assert.equal(selector.porId('estilos-menu').open, false);
    assert.equal(selector.mapa.estilo.layers.filter(c => c.type === 'fill-extrusion').length, 1);
    await selector.estilos[2].eventos.click();
    assert.equal(selector.porId('estilo-seleccionado').textContent, 'Satélite');
    assert.equal(selector.porId('estilos-summary').getAttribute('aria-label'), 'Estilo del mapa: Satélite');
    assert.deepEqual(JSON.parse(JSON.stringify(selector.mapa.getSource('observatorio-planet-v4'))), fuentePlanet,
        'Satélite conserva los polígonos de MapTiler Planet v4');
    const extrusiones = selector.mapa.estilo.layers.filter(c => c.type === 'fill-extrusion');
    assert.equal(extrusiones.length, 1);
    assert.equal(extrusiones[0].source, 'observatorio-planet-v4');
    selector.MapManager.agregarEdificios();
    assert.equal(selector.mapa.estilo.layers.filter(c => c.type === 'fill-extrusion').length, 1, 'No duplica los edificios al repetir style.load');
    await selector.estilos[0].eventos.click();
    assert.equal(selector.porId('estilo-seleccionado').textContent, 'Calles');
    assert.equal(selector.mapa.estilo.layers.filter(c => c.type === 'fill-extrusion').length, 1);
    assert.deepEqual(JSON.parse(JSON.stringify(selector.mapa.camara)), { center: { lat: -31.25, lng: -61.49 }, zoom: 19, pitch: 45, bearing: -17 });
    assert.equal(JSON.stringify(selector.crearParametros().toString()), estadoBusqueda, 'Cambiar de vista no altera filtros ni punto');
    assert.equal(JSON.stringify(selector.state.propiedades), datosAntes, 'Cambiar de vista conserva datos y coordenadas');
    assert.equal(selector.state.propiedadSeleccionada.id, 800);
    assert.equal(consultasEstilo.length, 3, 'Cambiar el fondo no consulta la API de propiedades');
    selector.porId('estilos-menu').open = true;
    selector.eventosDocumento.keydown({ key: 'Escape' });
    assert.equal(selector.porId('estilos-menu').open, false);
    const mapaAntesError = selector.mapa.estilo;
    selector.contexto.fetch = async () => ({ ok: false, status: 403 });
    assert.equal(await selector.MapManager.cambiarEstilo('oscuro'), false);
    assert.equal(selector.mapa.estilo, mapaAntesError, 'Un fallo de MapTiler conserva el fondo anterior');
    assert.equal(selector.porId('estilo-seleccionado').textContent, 'Calles');
    assert.equal(selector.porId('estilo-error').hidden, false);
    assert.equal(selector.estilos[1].disabled, false, 'Permite reintentar después del fallo');

    const sinClave = entorno();
    sinClave.porId('map').dataset.engine = 'maplibre';
    sinClave.porId('map-config').textContent = JSON.stringify({ maptilerApiKey: '   ' });
    sinClave.porId('estilo-seleccionado').textContent = 'Calles'; // Texto inicial de la plantilla.
    let consultasSinClave = 0;
    sinClave.contexto.fetch = async () => { consultasSinClave++; throw new Error('No debe hacer solicitudes sin clave'); };
    assert.throws(() => sinClave.MapManager.init(), /MAPTILER_API_KEY/);
    sinClave.eventosDocumento.DOMContentLoaded();
    assert.equal(sinClave.MapManager.map, null, 'Sin clave no crea un mapa de otro proveedor');
    assert.equal(sinClave.mapa.opciones, undefined);
    assert.equal(sinClave.porId('search-error').hidden, false);
    assert.ok(sinClave.porId('error-text').textContent.includes('MAPTILER_API_KEY'));
    assert.equal(sinClave.porId('loading-toast').hidden, true);
    assert.equal(sinClave.porId('results-count').textContent, 'Mapa no disponible');
    assert.ok(sinClave.estilos.every(btn => btn.disabled), 'Sin clave todas las vistas quedan deshabilitadas');
    assert.equal(consultasSinClave, 0, 'No consulta servicios ni propiedades sin configurar el mapa');
    assert.equal(await sinClave.MapManager.cambiarEstilo('satelite'), false);
    assert.equal(await sinClave.MapManager.cambiarEstilo('calles'), false);
    assert.equal(sinClave.porId('estilo-seleccionado').textContent, 'Calles');
    console.log('OK: coordenadas, agrupación, búsqueda y MapLibre con MapTiler, tres vistas y error sin clave.');
}
main().catch(error => { console.error(error); process.exitCode = 1; });
