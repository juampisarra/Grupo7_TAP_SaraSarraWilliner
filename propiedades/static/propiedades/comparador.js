/** Selección de publicaciones y comparación. Django es la fuente de los datos. */
(() => {
    'use strict';
    const porId = id => document.getElementById(id);
    const estado = {
        seleccion: new Map(), operacion: 'alquiler', ficha: null, tabla: null,
        controller: null, revision: 0, generando: false, mensaje: '',
    };
    const crear = (tag, clase, texto) => {
        const e = document.createElement(tag);
        if (clase) e.className = clase;
        if (texto !== undefined) e.textContent = texto;
        return e;
    };
    function urlPublica(valor) {
        try {
            const url = new URL(valor);
            return ['https:', 'http:'].includes(url.protocol) ? url.href : null;
        } catch { return null; }
    }
    function precio(p, campo = 'precio') {
        if (p[campo] === null || p[campo] === undefined) return 'No informado';
        return `${p.moneda || 'Moneda no informada'} ${Number(p[campo]).toLocaleString('es-AR', { maximumFractionDigits: 2 })}`;
    }
    function precision(p) {
        return ({
            sin_coordenadas: 'Ubicación sin coordenadas.',
            exacta_segun_fuente: 'Punto tratado como exacto según la política de la fuente.',
            aproximada: 'Ubicación aproximada; el punto representa el centro del área publicada.',
            geocodificada_direccion: 'Estimada por dirección; no garantiza la puerta exacta. © OpenStreetMap contributors',
        })[p.precision] || 'Precisión de ubicación desconocida.';
    }
    function fecha(iso) {
        const fecha = new Date(iso);
        return Number.isNaN(fecha.getTime()) ? 'No informada' : fecha.toLocaleString('es-AR');
    }
    function invalidar() {
        estado.revision++;
        estado.controller?.abort(); estado.controller = null;
        estado.tabla = null; estado.generando = false;
        porId('comparacion-tabla').replaceChildren();
        porId('comparacion-analisis').replaceChildren();
        porId('btn-generar-analisis').disabled = true;
        porId('btn-generar-analisis').textContent = 'Generar análisis con IA';
    }
    function sincronizarBotones() {
        document.querySelectorAll('[data-comparar-id]').forEach(boton => {
            const activo = estado.seleccion.has(Number(boton.dataset.compararId));
            boton.textContent = activo ? '✓ En comparación' : '+ Agregar a comparación';
            boton.setAttribute('aria-pressed', String(activo));
        });
    }
    function renderizarSeleccion() {
        const lista = porId('comparacion-seleccion'); lista.replaceChildren();
        estado.seleccion.forEach(p => {
            const item = crear('li');
            item.append(crear('span', '', p.direccion || p.titulo || `${p.tipo || 'Publicación'} #${p.id}`));
            const quitar = crear('button', '', '×'); quitar.type = 'button';
            quitar.setAttribute('aria-label', `Quitar publicación #${p.id} de la comparación`);
            quitar.addEventListener('click', () => alternar(p)); item.append(quitar); lista.append(item);
        });
        porId('comparacion-cantidad').textContent = `${estado.seleccion.size}/4 seleccionadas`;
        porId('comparacion-aviso').textContent = estado.mensaje;
        porId('btn-ocultar-aviso-comparacion').hidden = !estado.mensaje;
        porId('comparacion-barra').hidden = !estado.seleccion.size && !estado.mensaje;
        porId('btn-comparar').disabled = estado.seleccion.size < 2;
        porId('btn-limpiar-comparacion').hidden = !estado.seleccion.size;
        document.body.classList.toggle('comparison-active', Boolean(estado.seleccion.size || estado.mensaje));
        sincronizarBotones();
    }
    function alternar(p) {
        if (estado.seleccion.has(p.id)) estado.seleccion.delete(p.id);
        else if (estado.seleccion.size >= 4) {
            estado.mensaje = 'Podés comparar hasta 4 publicaciones. Quitá alguna para agregar otra.';
            renderizarSeleccion(); return;
        } else estado.seleccion.set(p.id, p);
        estado.mensaje = '';
        invalidar(); renderizarSeleccion();
        if (porId('comparador').open) {
            if (estado.seleccion.size < 2) porId('comparador').close();
            else cargarTabla();
        }
    }
    function cambiarOperacion(operacion) {
        if (!['alquiler', 'venta'].includes(operacion) || operacion === estado.operacion) return;
        const habiaSeleccion = estado.seleccion.size > 0;
        estado.operacion = operacion; estado.seleccion.clear(); estado.ficha = null;
        invalidar();
        if (porId('comparador').open) porId('comparador').close();
        porId('card-comparar').hidden = true;
        estado.mensaje = habiaSeleccion ? 'Se limpió la comparación al cambiar entre alquiler y venta.' : '';
        renderizarSeleccion();
    }
    function crearBoton(p) {
        const boton = crear('button', 'comparison-select'); boton.type = 'button';
        boton.dataset.compararId = String(p.id);
        const activo = estado.seleccion.has(p.id);
        boton.textContent = activo ? '✓ En comparación' : '+ Agregar a comparación';
        boton.setAttribute('aria-pressed', String(activo));
        boton.setAttribute('aria-label', `Comparar publicación #${p.id}: ${p.direccion || p.tipo || 'Propiedad'}`);
        boton.addEventListener('click', () => alternar(p));
        return boton;
    }
    function renderizarTabla(datos) {
        const tabla = crear('table', 'comparison-table');
        tabla.style.setProperty('--comparison-table-width', `${165 + datos.propiedades.length * 225}px`);
        tabla.append(crear('caption', 'sr-only', `Comparación de propiedades en ${datos.operacion}`));
        const cabeza = crear('thead'), fila = crear('tr');
        const primera = crear('th', '', 'Características'); primera.scope = 'col'; fila.append(primera);
        datos.propiedades.forEach(p => {
            const celda = crear('th'); celda.scope = 'col';
            const foto = urlPublica(p.foto_portada);
            if (foto) {
                const img = crear('img'); img.src = foto; img.alt = `Foto de la publicación #${p.id}`;
                img.loading = 'lazy'; img.referrerPolicy = 'no-referrer';
                img.addEventListener('error', () => { img.hidden = true; }); celda.append(img);
            }
            celda.append(crear('span', 'comparison-id', `Publicación #${p.id}`),
                crear('h3', '', p.titulo || p.tipo || 'Propiedad'));
            const quitar = crear('button', 'text-btn', 'Quitar'); quitar.type = 'button';
            quitar.setAttribute('aria-label', `Quitar publicación #${p.id}`);
            quitar.addEventListener('click', () => alternar(p)); celda.append(quitar); fila.append(celda);
        });
        cabeza.append(fila); tabla.append(cabeza);
        const cuerpo = crear('tbody');
        const filas = [
            ['Precio publicado', p => precio(p)],
            ['Diferencia con el menor precio', p => datos.precios_comparables ? precio(p, 'diferencia_con_menor_precio') : 'No comparable'],
            ['Tipo', p => p.tipo], ['Inmobiliaria', p => p.fuente],
            ['Dirección', p => p.direccion], ['Zona', p => p.zona],
            ['Ciudad / provincia', p => [p.ciudad, p.provincia].filter(Boolean).join(', ')],
            ['Dormitorios', p => p.dormitorios == null ? null : `${p.dormitorios}${p.dormitorios_verificados ? '' : ' (sin verificar)'}`],
            ['Ambientes', p => p.ambientes], ['Baños', p => p.banos],
            ['Características publicadas', p => p.caracteristicas],
            ['Precisión de ubicación', precision],
            ['Actualizada en el observatorio', p => fecha(p.actualizada_en)],
        ];
        filas.forEach(([nombre, obtener]) => {
            const fila = crear('tr'), titulo = crear('th', '', nombre); titulo.scope = 'row'; fila.append(titulo);
            datos.propiedades.forEach(p => {
                const valor = obtener(p); fila.append(crear('td', '', valor === null || valor === undefined || valor === '' ? 'No informado' : String(valor)));
            }); cuerpo.append(fila);
        });
        const enlaces = crear('tr'), titulo = crear('th', '', 'Fuente original'); titulo.scope = 'row'; enlaces.append(titulo);
        datos.propiedades.forEach(p => {
            const celda = crear('td'), url = urlPublica(p.url_original);
            if (url) {
                const enlace = crear('a', '', 'Ver aviso original ↗'); enlace.href = url;
                enlace.target = '_blank'; enlace.rel = 'noopener noreferrer'; celda.append(enlace);
            } else celda.textContent = 'Enlace no disponible';
            enlaces.append(celda);
        }); cuerpo.append(enlaces); tabla.append(cuerpo);
        porId('comparacion-tabla').replaceChildren(tabla);
        porId('comparacion-contexto').textContent = `${datos.propiedades.length} publicaciones en ${datos.operacion}. Los datos no informados no equivalen a cero ni a ausencia de una característica.`;
    }
    async function leerRespuesta(response) {
        let datos;
        try { datos = await response.json(); }
        catch { throw new Error('El servidor no pudo responder. Esperá unos segundos y reintentá.'); }
        if (!response.ok) {
            const error = new Error(datos.error || 'No se pudo completar la comparación.');
            error.codigo = datos.codigo; error.ids = datos.ids || []; throw error;
        }
        return datos;
    }
    function mostrarError(error) {
        porId('comparacion-estado').textContent = error.message;
        const acciones = porId('comparacion-recuperacion'); acciones.replaceChildren();
        (error.ids || []).forEach(id => {
            const p = estado.seleccion.get(id); if (!p) return;
            const quitar = crear('button', 'text-btn', `Quitar publicación #${id}`); quitar.type = 'button';
            quitar.addEventListener('click', () => alternar(p)); acciones.append(quitar);
        });
    }
    async function cargarTabla() {
        invalidar();
        const revision = estado.revision, controller = new AbortController(); estado.controller = controller;
        porId('comparacion-estado').textContent = 'Consultando datos actuales…';
        porId('comparacion-contexto').textContent = '';
        porId('comparacion-recuperacion').replaceChildren();
        const params = new URLSearchParams({ ids: [...estado.seleccion.keys()].join(','), operacion: estado.operacion });
        try {
            const response = await fetch(`${porId('comparador').dataset.tablaUrl}?${params}`, {
                signal: controller.signal, headers: { Accept: 'application/json' }, cache: 'no-store',
            });
            const datos = await leerRespuesta(response);
            if (revision !== estado.revision || !porId('comparador').open) return;
            estado.tabla = datos; renderizarTabla(datos);
            porId('btn-generar-analisis').disabled = !datos.ia_disponible;
            porId('comparacion-estado').textContent = datos.ia_disponible ? '' : 'La tabla está disponible. El análisis con IA todavía no está configurado.';
        } catch (error) {
            if (revision === estado.revision && error.name !== 'AbortError') mostrarError(error);
        }
    }
    function agregarLista(destino, titulo, textos) {
        if (!textos.length) return;
        destino.append(crear('h4', '', titulo)); const lista = crear('ul');
        textos.forEach(texto => lista.append(crear('li', '', texto))); destino.append(lista);
    }
    function renderizarAnalisis(datos) {
        const destino = porId('comparacion-analisis'); destino.replaceChildren();
        const a = datos.analisis;
        destino.append(crear('h3', '', 'Análisis de las publicaciones'), crear('p', '', a.resumen));
        agregarLista(destino, 'Diferencias principales', a.diferencias);
        a.por_propiedad.forEach(item => {
            const p = estado.tabla.propiedades.find(p => p.id === item.propiedad_id);
            destino.append(crear('h4', '', `Publicación #${item.propiedad_id} · ${p?.direccion || p?.tipo || 'Propiedad'}`));
            agregarLista(destino, 'Ventajas según tus necesidades', item.ventajas);
            agregarLista(destino, 'Limitaciones', item.limitaciones);
        });
        agregarLista(destino, 'Información para consultar', a.datos_faltantes);
        destino.append(crear('p', 'comparison-conclusion', a.conclusion));
        destino.append(crear('p', 'comparison-footnote', `Generado con Gemini (${datos.modelo}) · ${fecha(datos.generado_en)}${datos.reutilizado ? ' · Análisis reutilizado' : ''}. Puede contener errores; verificá la información con la inmobiliaria.`));
    }
    async function generar() {
        if (!estado.tabla || estado.generando || !estado.tabla.ia_disponible) return;
        const revision = estado.revision, tabla = estado.tabla, controller = new AbortController();
        estado.controller?.abort(); estado.controller = controller; estado.generando = true;
        const boton = porId('btn-generar-analisis'); boton.disabled = true; boton.textContent = 'Generando análisis…';
        porId('comparacion-estado').textContent = 'Comparando con IA. Esto puede tardar unos segundos…';
        porId('comparacion-analisis').replaceChildren();
        let timeout;
        try {
            timeout = window.setTimeout(() => controller.abort(), 30000);
            const token = document.cookie.split(';').map(c => c.trim()).find(c => c.startsWith('csrftoken='))?.slice(10) || '';
            const response = await fetch(porId('comparador').dataset.analisisUrl, {
                method: 'POST', signal: controller.signal,
                headers: { 'Content-Type': 'application/json', Accept: 'application/json', 'X-CSRFToken': decodeURIComponent(token) },
                body: JSON.stringify({ ids: tabla.propiedades.map(p => p.id), operacion: tabla.operacion, firma: tabla.firma }),
            });
            const datos = await leerRespuesta(response);
            if (revision !== estado.revision || !porId('comparador').open) return;
            if (datos.firma !== tabla.firma) throw new Error('La respuesta no corresponde a la tabla actual. Actualizá los datos.');
            renderizarAnalisis(datos); porId('comparacion-estado').textContent = 'Análisis disponible.';
        } catch (error) {
            if (revision !== estado.revision) return;
            if (['datos_cambiaron', 'publicaciones_retiradas', 'publicaciones_ausentes'].includes(error.codigo)) {
                estado.tabla = null;
            }
            mostrarError(error.name === 'AbortError' ? new Error('La IA demoró demasiado. La tabla sigue disponible; podés reintentar.') : error);
        } finally {
            window.clearTimeout(timeout);
            if (revision === estado.revision) {
                estado.generando = false; boton.disabled = !estado.tabla?.ia_disponible;
                boton.textContent = 'Generar análisis con IA';
            }
        }
    }
    function iniciar() {
        estado.operacion = window.ObservatorioMapa?.operacion?.() || 'alquiler';
        porId('btn-comparar').addEventListener('click', () => {
            if (estado.seleccion.size < 2) return;
            porId('comparador').showModal(); cargarTabla();
        });
        porId('btn-cerrar-comparador').addEventListener('click', () => porId('comparador').close());
        porId('comparador').addEventListener('cancel', evento => evento.stopPropagation());
        porId('comparador').addEventListener('keydown', evento => { if (evento.key === 'Escape') evento.stopPropagation(); });
        porId('comparador').addEventListener('close', () => {
            invalidar();
            const destino = estado.seleccion.size >= 2 ? 'btn-comparar'
                : estado.seleccion.size ? 'btn-limpiar-comparacion' : 'btn-resultados-panel';
            porId(destino).focus();
        });
        porId('btn-actualizar-comparacion').addEventListener('click', cargarTabla);
        porId('btn-generar-analisis').addEventListener('click', generar);
        porId('btn-limpiar-comparacion').addEventListener('click', () => {
            estado.seleccion.clear(); estado.mensaje = ''; invalidar(); renderizarSeleccion();
        });
        porId('btn-ocultar-aviso-comparacion').addEventListener('click', () => { estado.mensaje = ''; renderizarSeleccion(); });
        porId('card-comparar').addEventListener('click', () => { if (estado.ficha) alternar(estado.ficha); });
        window.addEventListener('observatorio:ficha', evento => {
            estado.ficha = evento.detail.propiedad;
            const boton = porId('card-comparar'); boton.hidden = !estado.ficha;
            if (estado.ficha) boton.dataset.compararId = String(estado.ficha.id);
            sincronizarBotones();
        });
        window.addEventListener('observatorio:operacion', evento => cambiarOperacion(evento.detail.operacion));
        window.addEventListener('observatorio:resultados', evento => cambiarOperacion(evento.detail.operacion));
        renderizarSeleccion();
    }
    window.ObservatorioComparador = { crearBoton };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar);
    else iniciar();
})();
