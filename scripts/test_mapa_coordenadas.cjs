// Prueba de interacción con Leaflet/DOM simulados. Ejecutar: node scripts/test_mapa_coordenadas.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function elemento() {
    return { children: [], eventos: {}, classList: { add() {}, remove() {} },
        appendChild(hijo) { this.children.push(hijo); },
        addEventListener(nombre, fn) { this.eventos[nombre] = fn; } };
}
const elementos = new Map();
const marcadores = [];
const contexto = {
    document: { addEventListener() {}, querySelectorAll() { return []; },
        createElement: elemento,
        getElementById(id) { if (!elementos.has(id)) elementos.set(id, elemento()); return elementos.get(id); } },
    L: { divIcon: (opciones) => opciones, marker(coordenadas, opciones) {
        const marcador = { coordenadas, opciones, eventos: {},
            on(nombre, fn) { this.eventos[nombre] = fn; },
            bindPopup(contenido) { this.popup = contenido; return this; },
            openPopup() { return this; }, getElement() { return null; },
            getLatLng() { return this.coordenadas; } };
        marcadores.push(marcador); return marcador;
    } }, console,
};
let codigo = fs.readFileSync('propiedades/static/propiedades/mapa.js', 'utf8');
codigo = codigo.replace(/\}\)\(\);\s*$/, 'globalThis.prueba = { MapManager, CardManager }; })();');
vm.runInNewContext(codigo, contexto);
const { MapManager, CardManager } = contexto.prueba;
MapManager.markersLayer = { clearLayers() { marcadores.length = 0; }, addLayer() {} };
MapManager.map = { setView() {}, panTo() {}, closePopup() {} };
const base = { latitud: -31.25, longitud: -61.49, direccion: 'Necochea 142', fuente: 'Gaggiotti',
    fotos: [], caracteristicas: '', dormitorios: null, ambientes: null, banos: null,
    alquiler: { disponible: true, precio: '500000.00', moneda: 'ARS' }, ubicacion_aproximada: null };
const avisos = [{ ...base, id: 1 }, { ...base, id: 2, direccion: '<img src=x onerror=alert(1)>' },
    { ...base, id: 3, latitud: -31.250001 }];
MapManager.renderizarMarcadores(avisos);
assert.equal(marcadores.length, 2, 'Agrupa solo puntos idénticos; no redondea ni desplaza');
assert.equal(JSON.stringify(marcadores[0].coordenadas), JSON.stringify([-31.25, -61.49]));
assert.equal(MapManager.markerMap.get(1), MapManager.markerMap.get(2));
marcadores[0].eventos.click();
const botones = marcadores[0].popup.children.filter(e => e.type === 'button');
assert.equal(botones.length, 2);
assert.ok(botones[1].textContent.includes('<img'), 'Direcciones se insertan como texto');
botones[1].eventos.click();
assert.ok(elementos.get('card-location-precision').textContent.includes('desconocida'));
CardManager.mostrar({ ...base, id: 4, ubicacion_info: { precision: 'geocodificada_direccion' } });
assert.ok(elementos.get('card-location-precision').textContent.includes('no garantiza'));
assert.ok(elementos.get('card-location-precision').textContent.includes('OpenStreetMap'));
console.log('OK: puntos originales, agrupación, selección y advertencias de precisión.');
