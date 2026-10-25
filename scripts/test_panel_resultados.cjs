// Panel lateral aislado: no consulta servicios ni modifica datos.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

class Elemento {
    constructor(tag = 'div') {
        this.tag = tag; this.children = []; this.eventos = {}; this.attributes = {};
        this.value = ''; this.hidden = false; this.disabled = false; this._text = ''; this._html = '';
        this.className = ''; this.type = ''; this.src = '';
        const clases = () => new Set(this.className.split(' ').filter(Boolean));
        this.classList = {
            add: (...nombres) => { const c = clases(); nombres.forEach(n => c.add(n)); this.className = [...c].join(' '); },
            remove: (...nombres) => { const c = clases(); nombres.forEach(n => c.delete(n)); this.className = [...c].join(' '); },
            contains: nombre => clases().has(nombre),
        };
    }
    set textContent(valor) { this._text = String(valor); this.children = []; }
    get textContent() { return this._text + this.children.map(h => h.textContent).join(''); }
    get innerHTML() { return this._html; }
    append(...hijos) { this.children.push(...hijos); }
    replaceChildren(...hijos) { this._text = ''; this._html = ''; this.children = hijos; }
    addEventListener(nombre, fn) { this.eventos[nombre] = fn; }
    setAttribute(nombre, valor) { this.attributes[nombre] = String(valor); }
    focus() { this.enfocado = true; }
    remove() { this.removido = true; }
    querySelector(selector) {
        if (selector === 'option[value="relevancia"]') return this.opcionRelevancia;
        return null;
    }
}

function entorno() {
    const elementos = new Map(), eventosDocumento = {}, eventosVentana = {};
    const porId = id => { if (!elementos.has(id)) elementos.set(id, new Elemento()); return elementos.get(id); };
    const opcion = new Elemento('option'); porId('panel-orden').opcionRelevancia = opcion;
    porId('resultados-panel').hidden = true;
    const body = new Elemento('body');
    const documento = {
        readyState: 'loading', body,
        getElementById: porId, createElement: tag => new Elemento(tag),
        addEventListener(nombre, fn) { eventosDocumento[nombre] = fn; },
    };
    const mapa = { abiertas: [], redimensiones: 0,
        abrirPropiedad(id) { this.abiertas.push(id); }, redimensionar() { this.redimensiones++; } };
    const ventana = {
        ObservatorioMapa: mapa,
        addEventListener(nombre, fn) { eventosVentana[nombre] = fn; },
        matchMedia() { return { matches: false }; },
    };
    const contexto = { document: documento, window: ventana, console };
    let codigo = fs.readFileSync('propiedades/static/propiedades/explorador.js', 'utf8');
    codigo = codigo.replace(/\}\)\(\);\s*$/, 'globalThis.prueba = { estado, PanelResultados, precio, propiedadesOrdenadas }; })();');
    vm.runInNewContext(codigo, contexto);
    eventosDocumento.DOMContentLoaded();
    return { ...contexto.prueba, porId, body, mapa, eventosDocumento, eventosVentana };
}

const base = {
    tipo: 'Casa', direccion: 'Belgrano 100', ciudad: 'Rafaela', fuente: 'Brega',
    titulo: 'Casa céntrica', caracteristicas: 'Patio', foto_portada: null,
    dormitorios: 2, ambientes: 3, banos: 1, relevancia: null,
    alquiler: { disponible: true, precio: '500000.00', moneda: 'ARS' },
};

const e = entorno();
e.eventosVentana['observatorio:resultados']({ detail: {
    propiedades: [
        { ...base, id: 1, actualizada_en: '2026-10-20T00:00:00Z' },
        { ...base, id: 2, titulo: '<img src=x onerror=alert(1)>', direccion: 'Mitre 20', actualizada_en: '2026-10-22T00:00:00Z', alquiler: { disponible: true, precio: '300000.00', moneda: 'ARS' } },
        { ...base, id: 3, tipo: 'Departamento', actualizada_en: '2026-10-21T00:00:00Z', alquiler: { disponible: true, precio: null, moneda: 'ARS' } },
    ], total: 5, operacion: 'alquiler', hayTexto: false,
} });
assert.equal(e.estado.orden, 'recientes');
assert.equal(e.porId('resultados-lista').children.length, 3);
assert.match(e.porId('resultados-panel-resumen').textContent, /3 con ubicación de 5/);
const tarjetaInsegura = e.porId('resultados-lista').children[0];
assert.ok(tarjetaInsegura.textContent.includes('<img'));
assert.equal(tarjetaInsegura.innerHTML, '', 'El título del aviso nunca se interpreta como HTML');

e.porId('panel-orden').eventos.change({ target: { value: 'precio-asc' } });
assert.ok(e.porId('resultados-lista').children[0].textContent.includes('$ 300.000'));
e.porId('panel-filtro-local').eventos.input({ target: { value: 'departamento' } });
assert.equal(e.porId('resultados-lista').children.length, 1);
assert.match(e.porId('resultados-panel-resumen').textContent, /1 visibles/);

e.porId('btn-resultados-panel').eventos.click();
assert.equal(e.porId('resultados-panel').hidden, false);
assert.equal(e.body.classList.contains('results-panel-open'), true);
assert.equal(e.mapa.redimensiones, 1);
e.porId('resultados-lista').children[0].children[0].eventos.click();
assert.deepEqual(e.mapa.abiertas, [3]);
e.eventosDocumento.keydown({ key: 'Escape' });
assert.equal(e.porId('resultados-panel').hidden, true);
assert.equal(e.mapa.redimensiones, 2);

console.log('OK panel de resultados: lista, filtro, orden, apertura y texto seguro');
