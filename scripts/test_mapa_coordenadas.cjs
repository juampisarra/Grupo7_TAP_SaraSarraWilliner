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
    const tipos = ['Casa','Campo','Nave Industrial'].map(tipo => { const b = new Elemento('button'); b.dataset.filterTipo = tipo; return b; });
    const comodidades = ['Cochera','Patio'].map(tipo => { const b = new Elemento('button'); b.dataset.filterCaracteristica = tipo; return b; });
    const mapa = {
        eventos: {}, zoom: 19, on(nombre, fn) { this.eventos[nombre] = fn; },
        latLngToContainerPoint: punto => ({ x: punto[1] * 100000, y: punto[0] * 100000 }),
        project: punto => ({ x: punto[0] * 100000, y: punto[1] * 100000 }),
        panTo(p) { this.centro = p; }, easeTo(p) { this.centro = p.center; },
        getZoom() { return this.zoom; }, fitBounds(bounds) { this.bounds = bounds; },
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
        document: { readyState: 'loading', addEventListener() {}, getElementById: porId,
            createElement: tag => new Elemento(tag),
            querySelectorAll(selector) { return selector === '[data-filter-tipo]' ? tipos : selector === '[data-filter-caracteristica]' ? comodidades : []; } },
        window: { location: { origin: 'http://localhost' } }, URL, URLSearchParams, AbortController,
        setTimeout, clearTimeout, console,
        L: { map: () => mapa, control: { zoom: () => ({ addTo() {} }) },
            tileLayer: () => ({ addTo() {} }),
            featureGroup: () => ({ addTo() { return this; }, clearLayers() {}, addLayer() {} }),
            divIcon: o => o, marker: marcador, popup, latLngBounds: puntos => puntos },
    };
    contexto.window.maplibregl = {
        Map: function(opciones) { mapa.opciones = opciones; return mapa; }, NavigationControl: function() {},
        Marker: function(o) { return marcador([], o); }, Popup: popup,
        LngLatBounds: function() { this.extend = () => this; },
    };
    let codigo = fs.readFileSync('propiedades/static/propiedades/mapa.js', 'utf8');
    codigo = codigo.replace(/\}\)\(\);\s*$/, 'globalThis.prueba = { state, MapManager, CardManager, PropertyApiClient, UI, crearParametros, agruparMarcadores, formatearPrecio, iconoTipo }; })();');
    vm.runInNewContext(codigo, contexto);
    return { ...contexto.prueba, contexto, elementos, marcadores, tipos, comodidades, mapa, porId };
}
const base = {
    latitud: -31.25, longitud: -61.49, tipo: 'Casa', direccion: 'Necochea 142', fuente: 'Gaggiotti',
    fotos: [], caracteristicas: '', dormitorios: null, ambientes: null, banos: null,
    alquiler: { disponible: true, precio: '500000.00', moneda: 'ARS' }, ubicacion_aproximada: null,
};
const respuesta = data => ({ ok: true, status: 200, json: async () => data });

async function main() {
    const e = entorno();
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
    const botones = e.MapManager.popup.contenido.children.filter(b => b.type === 'button');
    assert.equal(botones.length, 3);
    assert.ok(botones[1].textContent.includes('<img'), 'Texto del aviso no se interpreta como HTML');
    botones[1].eventos.click();
    assert.ok(e.porId('card-location-precision').textContent.includes('desconocida'));
    e.CardManager.mostrar({ ...base, id: 5, caracteristicas: '<img src=x onerror=alert(1)>',
        ubicacion_info: { precision: 'geocodificada_direccion' } });
    assert.ok(e.porId('card-location-precision').textContent.includes('no garantiza'));
    assert.equal(e.porId('card-features').children[0].innerHTML, '');
    assert.equal(e.formatearPrecio({ ...base, alquiler: { disponible: true, precio: '0.00', moneda: 'ARS' } }, 'alquiler'), '$ 0');

    const iconos = ['Casa','Chacra','Cochera','Consultorio','Departamento','Depósito','Galpón','Local','Nave Industrial','Oficina','PH','Quinta','Terreno','Campo'].map(e.iconoTipo);
    assert.equal(new Set(iconos).size, 14, 'Los tipos tienen dibujos diferentes');
    assert.ok(e.MapManager.marcadores[1].opciones.icon.html.includes('<svg'));
    assert.ok(e.MapManager.marcadores[1].opciones.icon.html.includes('$ 500 k'));

    e.UI.init();
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
    assert.equal(gl.mapa.opciones.style, 'https://tiles.openfreemap.org/styles/bright');
    assert.equal(gl.mapa.source.url, 'https://tiles.openfreemap.org/planet');
    assert.equal(gl.mapa.capa.type, 'fill-extrusion');
    gl.state.propiedades = [{ ...base, id: 10 }];
    gl.MapManager.renderizarMarcadores(gl.state.propiedades);
    assert.deepEqual(Array.from(gl.MapManager.marcadores[0].coordenadas), [-61.49, -31.25], 'MapLibre recibe longitud antes de latitud');
    assert.ok(gl.MapManager.marcadores[0].getElement().textContent.includes('$ 500 k'));

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
    console.log('OK: coordenadas, agrupación, búsqueda y MapLibre con OpenFreeMap/MapTiler y edificios sin fuentes duplicadas.');
}
main().catch(error => { console.error(error); process.exitCode = 1; });
