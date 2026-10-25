/** Panel lateral escondible con las propiedades ubicadas en el mapa. */
(() => {
    'use strict';

    const estado = {
        propiedades: [], total: 0, operacion: 'alquiler', hayTexto: false,
        filtroLocal: '', orden: 'relevancia',
    };
    const porId = (id) => document.getElementById(id);
    const normalizar = (texto) => String(texto || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');

    function datoPrecio(propiedad) {
        const dato = propiedad[estado.operacion];
        const monto = Number(dato?.precio);
        return dato?.disponible && dato.precio !== null && dato.precio !== '' && Number.isFinite(monto)
            ? { monto, moneda: dato.moneda || '' } : null;
    }

    function precio(propiedad) {
        const dato = datoPrecio(propiedad);
        if (!dato) return 'Consultar';
        const monto = dato.monto.toLocaleString('es-AR', { maximumFractionDigits: 2 });
        return (dato.moneda === 'ARS' ? '$' : dato.moneda) + ' ' + monto;
    }

    function textoPropiedad(propiedad) {
        return normalizar([
            propiedad.tipo, propiedad.titulo, propiedad.direccion, propiedad.zona,
            propiedad.ciudad, propiedad.fuente, propiedad.caracteristicas,
        ].filter(Boolean).join(' '));
    }

    function crear(tag, clase, texto) {
        const elemento = document.createElement(tag);
        if (clase) elemento.className = clase;
        if (texto !== undefined) elemento.textContent = texto;
        return elemento;
    }

    function propiedadesOrdenadas() {
        const filtro = normalizar(estado.filtroLocal.trim());
        const datos = estado.propiedades.filter((propiedad) => !filtro || textoPropiedad(propiedad).includes(filtro));
        const compararPrecio = (a, b, sentido) => {
            const pa = datoPrecio(a), pb = datoPrecio(b);
            if (!pa && !pb) return b.id - a.id;
            if (!pa) return 1;
            if (!pb) return -1;
            if (pa.moneda !== pb.moneda) return pa.moneda.localeCompare(pb.moneda);
            return (pa.monto - pb.monto) * sentido || b.id - a.id;
        };
        return datos.sort((a, b) => {
            if (estado.orden === 'precio-asc') return compararPrecio(a, b, 1);
            if (estado.orden === 'precio-desc') return compararPrecio(a, b, -1);
            if (estado.orden === 'recientes') {
                return String(b.actualizada_en).localeCompare(String(a.actualizada_en)) || b.id - a.id;
            }
            return (Number(b.relevancia) || 0) - (Number(a.relevancia) || 0)
                || String(b.actualizada_en).localeCompare(String(a.actualizada_en)) || b.id - a.id;
        });
    }

    class PanelResultados {
        static init() {
            porId('btn-resultados-panel').addEventListener('click', () => this.abrir());
            porId('btn-cerrar-resultados').addEventListener('click', () => this.cerrar());
            porId('panel-filtro-local').addEventListener('input', (evento) => {
                estado.filtroLocal = evento.target.value; this.renderizar();
            });
            porId('panel-orden').addEventListener('change', (evento) => {
                estado.orden = evento.target.value; this.renderizar();
            });
            window.addEventListener('observatorio:resultados', (evento) => this.actualizar(evento.detail || {}));
            document.addEventListener('keydown', (evento) => {
                if (evento.key === 'Escape' && !porId('resultados-panel').hidden) this.cerrar();
            });
        }

        static abrir() {
            porId('resultados-panel').hidden = false;
            document.body.classList.add('results-panel-open');
            porId('btn-resultados-panel').setAttribute('aria-expanded', 'true');
            window.ObservatorioMapa?.redimensionar();
        }

        static cerrar() {
            porId('resultados-panel').hidden = true;
            document.body.classList.remove('results-panel-open');
            porId('btn-resultados-panel').setAttribute('aria-expanded', 'false');
            porId('btn-resultados-panel').focus();
            window.ObservatorioMapa?.redimensionar();
        }

        static actualizar(detalle) {
            estado.propiedades = Array.isArray(detalle.propiedades) ? detalle.propiedades : [];
            estado.total = Number(detalle.total) || 0;
            estado.operacion = detalle.operacion === 'venta' ? 'venta' : 'alquiler';
            estado.hayTexto = Boolean(detalle.hayTexto);
            const opcionRelevancia = porId('panel-orden').querySelector('option[value="relevancia"]');
            opcionRelevancia.disabled = !estado.hayTexto;
            if (!estado.hayTexto && estado.orden === 'relevancia') estado.orden = 'recientes';
            if (estado.hayTexto && estado.orden === 'recientes') estado.orden = 'relevancia';
            porId('panel-orden').value = estado.orden;
            this.renderizar();
        }

        static renderizar() {
            const lista = porId('resultados-lista'); lista.replaceChildren();
            const propiedades = propiedadesOrdenadas();
            propiedades.forEach((propiedad) => lista.append(this.crearTarjeta(propiedad)));
            porId('resultados-panel-vacio').hidden = propiedades.length !== 0;
            porId('resultados-panel-titulo').textContent = estado.operacion === 'venta'
                ? 'Propiedades en venta' : 'Propiedades en alquiler';
            const contexto = estado.propiedades.length === estado.total
                ? `${estado.total} propiedades en el mapa`
                : `${estado.propiedades.length} con ubicación de ${estado.total} resultados`;
            porId('resultados-panel-resumen').textContent = estado.filtroLocal
                ? `${propiedades.length} visibles · ${contexto}` : contexto;
        }

        static crearTarjeta(propiedad) {
            const tarjeta = crear('article', 'result-card');
            const abrir = crear('button', 'result-card-open');
            abrir.type = 'button';
            abrir.setAttribute('aria-label', `Ver ${propiedad.tipo || 'propiedad'} en ${propiedad.direccion || 'ubicación no informada'}`);
            const media = crear('div', 'result-card-media');
            if (propiedad.foto_portada) {
                const imagen = crear('img');
                imagen.src = propiedad.foto_portada;
                imagen.alt = `Foto de ${propiedad.tipo || 'la propiedad'}`;
                imagen.loading = 'lazy'; imagen.decoding = 'async'; imagen.referrerPolicy = 'no-referrer';
                imagen.addEventListener('error', () => {
                    imagen.remove(); media.append(crear('span', 'result-card-placeholder', 'Foto no disponible'));
                }, { once: true });
                media.append(imagen);
            } else media.append(crear('span', 'result-card-placeholder', 'Foto no disponible'));
            const cuerpo = crear('div', 'result-card-body');
            cuerpo.append(
                crear('span', 'result-card-price', precio(propiedad)),
                crear('h3', '', propiedad.titulo || propiedad.tipo || 'Propiedad'),
                crear('p', 'result-card-location', [propiedad.direccion, propiedad.zona, propiedad.ciudad].filter(Boolean).join(' · ') || 'Dirección no informada'),
            );
            const especificaciones = [
                propiedad.dormitorios === null ? null : `${propiedad.dormitorios} dorm.`,
                propiedad.ambientes === null ? null : `${propiedad.ambientes} amb.`,
                propiedad.banos === null ? null : `${propiedad.banos} baños`,
            ].filter(Boolean);
            cuerpo.append(crear('p', 'result-card-specs', especificaciones.join(' · ') || `Inmobiliaria ${propiedad.fuente || 'no informada'}`));
            abrir.append(media, cuerpo);
            abrir.addEventListener('click', () => {
                window.ObservatorioMapa?.abrirPropiedad(propiedad.id);
                if (window.matchMedia('(max-width: 760px)').matches) this.cerrar();
            });
            tarjeta.append(abrir);
            return tarjeta;
        }
    }

    function iniciar() {
        PanelResultados.init();
        PanelResultados.actualizar(window.ObservatorioMapa?.resultados?.() || {});
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar);
    else iniciar();
})();
