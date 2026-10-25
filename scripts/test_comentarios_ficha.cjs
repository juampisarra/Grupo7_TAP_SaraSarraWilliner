// Prueba aislada de comentarios en la ficha del mapa: carga, envío, CSRF y texto seguro.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

class Elemento {
    constructor(tag = 'div') {
        this.tag = tag; this.children = []; this.eventos = {}; this.attributes = {};
        this.value = ''; this.hidden = false; this.disabled = false; this.open = false;
        this._text = ''; this._html = ''; this.className = ''; this.dataset = {};
        const clases = () => new Set(this.className.split(' ').filter(Boolean));
        this.classList = {
            add: (...nombres) => { const c = clases(); nombres.forEach(n => c.add(n)); this.className = [...c].join(' '); },
            remove: (...nombres) => { const c = clases(); nombres.forEach(n => c.delete(n)); this.className = [...c].join(' '); },
            toggle: (nombre, forzar) => {
                const c = clases();
                const activo = forzar === undefined ? !c.has(nombre) : Boolean(forzar);
                if (activo) c.add(nombre); else c.delete(nombre);
                this.className = [...c].join(' ');
            },
            contains: nombre => clases().has(nombre),
        };
    }
    set textContent(valor) { this._text = String(valor); this.children = []; }
    get textContent() { return this._text + this.children.map(h => h.textContent).join(''); }
    get innerHTML() { return this._html; }
    append(...hijos) { hijos.forEach(h => this.children.push(h)); }
    appendChild(hijo) { this.children.push(hijo); return hijo; }
    replaceChildren(...hijos) { this._text = ''; this._html = ''; this.children = [...hijos]; }
    addEventListener(nombre, fn) { this.eventos[nombre] = fn; }
    setAttribute(nombre, valor) { this.attributes[nombre] = String(valor); }
    removeAttribute(nombre) { delete this.attributes[nombre]; }
}

async function probar() {
    const elementos = new Map();
    const porId = (id) => {
        if (!elementos.has(id)) elementos.set(id, new Elemento());
        return elementos.get(id);
    };
    const solicitudes = [];
    const fetchMock = async (url, opciones = {}) => {
        solicitudes.push({ url, opciones });
        if ((opciones.method || 'GET') === 'GET') {
            return {
                ok: true,
                async json() {
                    return {
                        propiedad_id: 42,
                        total: 1,
                        comentarios: [{
                            id: 10,
                            propiedad_id: 42,
                            autor: '<b>Lucía</b>',
                            texto: '<script>alert(1)</script> Excelente ubicación',
                            creado_en: '2026-10-25T14:30:00Z',
                        }],
                    };
                },
            };
        }
        const cuerpo = JSON.parse(opciones.body || '{}');
        return {
            ok: true,
            status: 201,
            async json() {
                return {
                    comentario: {
                        id: 11,
                        propiedad_id: 42,
                        autor: cuerpo.autor || 'Anónimo',
                        texto: cuerpo.texto,
                        creado_en: '2026-10-25T15:00:00Z',
                    },
                };
            },
        };
    };

    const documento = {
        readyState: 'loading',
        cookie: 'otra=1; csrftoken=token-csrf-prueba-123',
        getElementById: porId,
        createElement: (tag) => new Elemento(tag),
        querySelector: () => null,
        querySelectorAll: () => [],
        addEventListener() {},
    };
    const ventana = {
        location: { origin: 'http://127.0.0.1:8000' },
        dispatchEvent() {},
    };
    const contexto = {
        document: documento,
        window: ventana,
        fetch: fetchMock,
        URL,
        URLSearchParams,
        AbortController,
        console,
    };

    let codigo = fs.readFileSync('propiedades/static/propiedades/mapa.js', 'utf8');
    codigo = codigo.replace(
        /if \(document\.readyState === 'loading'\)[\s\S]*$/,
        'globalThis.prueba = { state, CardManager }; })();',
    );
    vm.runInNewContext(codigo, contexto);

    const { CardManager } = contexto.prueba;
    CardManager.init();

    await CardManager.mostrar({
        id: 42,
        tipo: 'Casa',
        titulo: 'Casa en centro',
        direccion: 'Belgrano 250',
        ciudad: 'Rafaela',
        fuente: 'Brega',
        caracteristicas: 'Patio; Cochera',
        fotos: [],
        alquiler: { disponible: true, precio: '420000.00', moneda: 'ARS' },
    });
    // Esperar a que resuelva la promesa asíncrona de cargarComentarios
    await new Promise((r) => setTimeout(r, 10));

    assert.equal(porId('card-comments-badge').textContent, '1');
    assert.equal(porId('card-comments-status').hidden, true);
    assert.equal(porId('card-comments-list').children.length, 1);
    const primerComentario = porId('card-comments-list').children[0];
    assert.ok(primerComentario.textContent.includes('<script>alert(1)</script>'));
    assert.equal(primerComentario.innerHTML, '', 'Nunca se inserta HTML sin escapar');

    // Validación local de comentario demasiado corto
    porId('comentario-texto').value = 'ab';
    await porId('form-comentario').eventos.submit({ preventDefault() {} });
    assert.equal(porId('comentario-error').hidden, false);
    assert.match(porId('comentario-error').textContent, /al menos 3 caracteres/);

    // Envío válido con token CSRF y actualización reactiva de la lista
    porId('comentario-autor').value = 'Martín';
    porId('comentario-texto').value = 'Consulté por horarios de visita.';
    porId('comentario-texto').eventos.input({ target: porId('comentario-texto') });
    assert.equal(porId('comentario-contador').textContent, '32 / 500');

    await porId('form-comentario').eventos.submit({ preventDefault() {} });
    const postReq = solicitudes.find((s) => s.opciones.method === 'POST');
    assert.ok(postReq, 'Debe enviar solicitud POST');
    assert.equal(postReq.opciones.headers['X-CSRFToken'], 'token-csrf-prueba-123');
    assert.equal(porId('card-comments-badge').textContent, '2');
    assert.equal(porId('card-comments-list').children.length, 2);
    assert.ok(porId('card-comments-list').children[0].textContent.includes('Martín'));
    assert.equal(porId('comentario-texto').value, '');
    assert.equal(porId('comentario-contador').textContent, '0 / 500');
    assert.equal(porId('card-comments-section').open, true);

    console.log('OK ficha de comentarios: carga, validación, envío con CSRF y texto seguro');
}

probar().catch((err) => { console.error(err); process.exit(1); });
