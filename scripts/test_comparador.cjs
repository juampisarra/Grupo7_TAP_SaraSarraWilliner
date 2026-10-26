// Transporte y DOM simulados: no utiliza Gemini, mapas ni bases reales.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

class Elemento {
    constructor(tag = 'div') {
        this.tag = tag; this.children = []; this.dataset = {}; this.attributes = {}; this.eventos = {};
        this._text = ''; this.open = false; this.hidden = false; this.disabled = false;
        this.classList = { toggle() {} };
        this.style = { setProperty() {} };
    }
    set textContent(v) { this._text = String(v); this.children = []; }
    get textContent() { return this._text + this.children.map(c => c.textContent).join(''); }
    set innerHTML(_) { throw new Error('No se permite renderizar HTML de avisos o del LLM'); }
    append(...hijos) { this.children.push(...hijos); }
    replaceChildren(...hijos) { this._text = ''; this.children = hijos; }
    setAttribute(k, v) { this.attributes[k] = String(v); }
    addEventListener(k, fn) { this.eventos[k] = fn; }
    focus() { this.enfocado = true; }
    showModal() { this.open = true; }
    close() { this.open = false; this.eventos.close?.(); }
}
function entorno() {
    const elementos = new Map(), creados = [], eventos = {}, llamadas = [];
    const porId = id => {
        if (!elementos.has(id)) elementos.set(id, new Elemento());
        return elementos.get(id);
    };
    porId('comparador').dataset = { tablaUrl: '/api/propiedades/comparacion/', analisisUrl: '/api/propiedades/comparacion/analisis/' };
    const e = {
        document: {
            readyState: 'complete', cookie: 'csrftoken=token-csrf', body: new Elemento('body'),
            getElementById: porId,
            createElement(tag) { const el = new Elemento(tag); creados.push(el); return el; },
            querySelectorAll: () => [...creados, ...elementos.values()].filter(el => el.dataset.compararId),
        },
        window: { addEventListener(k, fn) { eventos[k] = fn; }, setTimeout, clearTimeout },
        URL, URLSearchParams, AbortController, console,
        fetch(url, opciones) { llamadas.push({ url, opciones }); return e.responder(url, opciones); },
    };
    let codigo = fs.readFileSync('propiedades/static/propiedades/comparador.js', 'utf8');
    codigo = codigo.replace(/\}\)\(\);\s*$/, 'globalThis.prueba = { estado, alternar, cambiarOperacion, cargarTabla, generar, renderizarTabla }; })();');
    vm.runInNewContext(codigo, e);
    return Object.assign(e, e.prueba, { porId, eventos, llamadas, creados });
}
const propiedad = id => ({
    id, tipo: 'Casa', titulo: id === 1 ? '<img src=x onerror=alert(1)>' : 'Casa con patio',
    direccion: 'Mitre ' + id, fuente: 'Fuente ' + id, ciudad: 'Rafaela', provincia: 'Santa Fe',
    precio: id === 1 ? '0.00' : null, moneda: 'ARS', dormitorios: id === 1 ? 0 : null,
    dormitorios_verificados: false, ambientes: null, banos: 1, caracteristicas: '<script>malicioso</script>',
    actualizada_en: '2026-10-25T15:00:00Z', url_original: id === 1 ? 'javascript:alert(1)' : 'https://example.com/aviso',
    foto_portada: null, precision: 'aproximada', diferencia_con_menor_precio: null,
});
const tabla = ids => ({ firma: 'firma', operacion: 'alquiler', propiedades: ids.map(propiedad), ia_disponible: true, precios_comparables: false });
const respuesta = (datos, status = 200) => ({ ok: status === 200, json: async () => datos });
const tick = () => new Promise(resolve => setImmediate(resolve));

(async () => {
    const e = entorno();
    const b1 = e.window.ObservatorioComparador.crearBoton(propiedad(1));
    b1.eventos.click();
    assert.equal(b1.attributes['aria-pressed'], 'true');
    assert.equal(e.porId('btn-comparar').disabled, true);
    e.alternar(propiedad(2));
    assert.equal(e.porId('btn-comparar').disabled, false);
    e.eventos['observatorio:resultados']({ detail: { operacion: 'alquiler', propiedades: [] } });
    assert.equal(e.estado.seleccion.size, 2, 'Una búsqueda vacía conserva las seleccionadas');
    e.alternar(propiedad(3)); e.alternar(propiedad(4)); e.alternar(propiedad(5));
    assert.equal(e.estado.seleccion.size, 4);
    assert.match(e.porId('comparacion-aviso').textContent, /hasta 4/);
    e.alternar(propiedad(4)); e.alternar(propiedad(3));
    e.responder = async () => respuesta(tabla([1, 2]));
    e.porId('btn-comparar').eventos.click(); await tick();
    assert.equal(e.porId('comparador').open, true);
    const textoTabla = e.porId('comparacion-tabla').textContent;
    assert.match(textoTabla, /<img src=x/);
    assert.match(textoTabla, /0 \(sin verificar\)/);
    assert.match(textoTabla, /No informado/);
    assert.match(textoTabla, /ARS 0/);
    assert.ok(!e.creados.some(el => el.href?.startsWith('javascript:')));
    assert.match(e.llamadas[0].url, /ids=1%2C2/);

    let resolver;
    e.responder = () => new Promise(r => { resolver = r; });
    const pendiente = e.generar();
    const llamadas = e.llamadas.length;
    await e.generar();
    assert.equal(e.llamadas.length, llamadas, 'No se duplica una generación en curso');
    const post = e.llamadas.at(-1).opciones;
    assert.equal(post.headers['X-CSRFToken'], 'token-csrf');
    assert.deepEqual(JSON.parse(post.body), { ids: [1, 2], operacion: 'alquiler', firma: 'firma' });
    e.porId('comparador').close();
    resolver(respuesta({ firma: 'firma', analisis: { resumen: 'Respuesta tardía que no debe aparecer' } }));
    await pendiente;
    assert.equal(e.porId('comparacion-analisis').textContent, '');
    assert.equal(e.estado.seleccion.size, 2);
    assert.equal(e.porId('btn-comparar').enfocado, true);

    e.responder = async () => respuesta(tabla([1, 2]));
    e.porId('btn-comparar').eventos.click(); await tick();
    e.responder = async () => respuesta({ firma: 'firma', modelo: 'simulado', generado_en: '2026-10-25', analisis: {
        resumen: '<script>texto del LLM</script>', diferencias: ['Diferencia'],
        por_propiedad: [{ propiedad_id: 1, ventajas: ['Patio publicado'], limitaciones: ['Consultar superficie'] }],
        datos_faltantes: ['Superficie'], conclusion: 'Elegir según necesidades',
    } });
    await e.generar();
    assert.match(e.porId('comparacion-analisis').textContent, /<script>texto del LLM/);
    e.responder = async () => respuesta({ error: 'Cuota agotada', codigo: 'cuota_ia_agotada' }, 429);
    await e.generar();
    assert.match(e.porId('comparacion-estado').textContent, /Cuota agotada/);
    assert.ok(e.porId('comparacion-tabla').textContent.length > 0, 'Los fallos de IA conservan la tabla');
    e.responder = async () => respuesta({ error: 'Datos cambiaron', codigo: 'datos_cambiaron' }, 409);
    await e.generar();
    assert.equal(e.porId('btn-generar-analisis').disabled, true);
    e.eventos['observatorio:operacion']({ detail: { operacion: 'venta' } });
    assert.equal(e.estado.seleccion.size, 0);
    assert.equal(e.porId('comparador').open, false);
    assert.match(e.porId('comparacion-aviso').textContent, /cambiar/);

    const ficha = propiedad(7);
    e.eventos['observatorio:ficha']({ detail: { propiedad: ficha } });
    e.porId('card-comparar').eventos.click();
    assert.equal(e.estado.seleccion.has(7), true);
    assert.equal(e.porId('card-comparar').attributes['aria-pressed'], 'true');
    e.porId('btn-limpiar-comparacion').eventos.click();
    assert.equal(e.porId('comparacion-barra').hidden, true);
    console.log('OK comparador: selección, tabla, CSRF, IA, errores, respuestas tardías, ficha y texto seguro');
})().catch(error => { console.error(error); process.exitCode = 1; });
