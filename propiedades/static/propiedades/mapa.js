/**
 * Interfaz del Observatorio: consultas en Django y presentación del mapa.
 * MapLibre dibuja el mapa con cartografía de MapTiler, que requiere su clave.
 * La agrupación en pantalla es visual; todas las distancias se filtran en PostGIS.
 */
(() => {
    'use strict';

    const state = {
        operacion: 'alquiler', tipo: null, texto: '', caracteristicas: new Set(),
        dormitorios: '', precioMin: '', precioMax: '',
        punto: null, radio: 1000, incluirAproximadas: false, seleccionandoPunto: false,
        propiedades: [], total: 0, propiedadSeleccionada: null, fotoIndex: 0,
        abortController: null,
        estiloMapa: 'calles',
    };
    const RAFAELA = [-31.253, -61.491];
    const RADIOS = [500, 1000, 2000];
    const ZOOM_MAXIMO_GRUPOS = 18;
    const ORIGEN = window.location.origin;
    const MAPLIBRE = () => window.maplibregl;
    const normalizar = (texto) => String(texto || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
    function emitir(nombre, detalle) {
        if (typeof window.dispatchEvent === 'function' && typeof CustomEvent !== 'undefined') {
            window.dispatchEvent(new CustomEvent(nombre, { detail: detalle }));
        }
    }
    function leerCookie(nombre) {
        const prefijo = nombre + '=';
        const partes = String(document.cookie || '').split(';');
        for (const parte of partes) {
            const limpia = parte.trim();
            if (limpia.startsWith(prefijo)) {
                try { return decodeURIComponent(limpia.slice(prefijo.length)); }
                catch { return limpia.slice(prefijo.length); }
            }
        }
        return '';
    }
    function formatearFechaComentario(iso) {
        if (!iso) return '';
        const fecha = new Date(iso);
        if (Number.isNaN(fecha.getTime())) return '';
        return fecha.toLocaleString('es-AR', {
            day: '2-digit', month: '2-digit', year: 'numeric',
            hour: '2-digit', minute: '2-digit',
        });
    }

    const iconosTipo = {
        casa: '🏠', departamento: '🏢', ph: '🏘️', terreno: '📐', campo: '🌾',
        chacra: '🚜', quinta: '🌳', cochera: '🚗', consultorio: '🩺', oficina: '💼',
        local: '🏪', deposito: '📦', galpon: '🏭', 'nave industrial': '🏗️',
    };
    function iconoTipo(tipo) {
        return iconosTipo[normalizar(tipo)] || '📍';
    }
    function datosPrecio(propiedad, operacion) {
        const dato = propiedad[operacion];
        if (!dato?.disponible || dato.precio === null || dato.precio === undefined || dato.precio === '') return null;
        const monto = Number(dato.precio);
        return Number.isFinite(monto) ? { monto, moneda: dato.moneda } : null;
    }
    function formatearPrecio(propiedad, operacion, breve = false) {
        const dato = datosPrecio(propiedad, operacion);
        if (!dato) return 'Consultar';
        let valor = dato.monto.toLocaleString('es-AR', { maximumFractionDigits: 2 });
        if (breve && dato.monto >= 1000000) valor = (dato.monto / 1000000).toFixed(1).replace('.0', '') + ' M';
        else if (breve && dato.monto >= 1000) valor = (dato.monto / 1000).toLocaleString('es-AR', { maximumFractionDigits: 1 }) + ' k';
        const moneda = dato.moneda === 'ARS' ? '$' : dato.moneda;
        return moneda ? moneda + ' ' + valor : valor + ' · s/m';
    }
    function textoConsulta() {
        const comodidades = [...state.caracteristicas].map((texto) => texto.toLowerCase());
        return [state.texto.trim(), comodidades.length ? 'con ' + comodidades.join(' y ') : ''].filter(Boolean).join(' ');
    }
    function crearParametros() {
        const params = new URLSearchParams({ operacion: state.operacion, por_pagina: '100' });
        if (state.tipo) params.set('tipo', state.tipo);
        if (state.dormitorios !== '') params.set('dormitorios', state.dormitorios);
        if (state.precioMin !== '' || state.precioMax !== '') {
            params.set('moneda', state.operacion === 'alquiler' ? 'ARS' : 'USD');
            if (state.precioMin !== '') params.set('precio_min', state.precioMin);
            if (state.precioMax !== '') params.set('precio_max', state.precioMax);
        }
        const texto = textoConsulta();
        if (texto.length > 300) throw new Error('La búsqueda y las comodidades juntas admiten hasta 300 caracteres.');
        if (texto) params.set('q', texto);
        if (state.punto) {
            if (!RADIOS.includes(state.radio)) throw new Error('Elegí una distancia de 500 m, 1 km o 2 km.');
            params.set('latitud', state.punto.lat);
            params.set('longitud', state.punto.lng);
            params.set('radio_m', state.radio);
            params.set('incluir_aproximadas', state.incluirAproximadas ? '1' : '0');
        }
        return params;
    }
    function tieneCoordenadas(p) {
        return typeof p.latitud === 'number' && Number.isFinite(p.latitud) && Math.abs(p.latitud) <= 90
            && typeof p.longitud === 'number' && Number.isFinite(p.longitud) && Math.abs(p.longitud) <= 180;
    }

    class PropertyApiClient {
        static async buscarPropiedades() {
            state.abortController?.abort();
            const controller = new AbortController();
            state.abortController = controller;
            UI.mostrarError('');
            UI.mostrarCargando(true);
            try {
                let siguiente = '/api/propiedades/?' + crearParametros().toString();
                const paginas = new Set(), resultados = new Map(), avisos = new Set();
                let total = 0;
                while (siguiente) {
                    const url = new URL(siguiente, ORIGEN);
                    if (url.origin !== ORIGEN || url.pathname !== '/api/propiedades/' || paginas.has(url.href)) {
                        throw new Error('No se pudo completar la carga de resultados.');
                    }
                    paginas.add(url.href);
                    const response = await fetch(url.href, {
                        headers: { Accept: 'application/json' }, signal: controller.signal,
                    });
                    if (controller.signal.aborted || state.abortController !== controller) return;
                    let data;
                    try { data = await response.json(); }
                    catch { throw new Error('El servidor no pudo responder. Esperá unos segundos y reintentá.'); }
                    if (!response.ok) throw new Error(data.error || 'No pudimos realizar la búsqueda.');
                    if (!Array.isArray(data.resultados)) throw new Error('La respuesta del buscador no es válida.');
                    data.resultados.forEach((p) => resultados.set(p.id, p));
                    (data.advertencias || []).forEach((aviso) => avisos.add(aviso));
                    total = data.total;
                    siguiente = data.siguiente;
                    UI.progreso(resultados.size, total);
                }
                if (controller.signal.aborted || state.abortController !== controller) return;
                state.propiedades = [...resultados.values()].filter(tieneCoordenadas);
                state.total = total;
                MapManager.renderizarMarcadores(state.propiedades);
                emitir('observatorio:resultados', {
                    propiedades: state.propiedades,
                    total,
                    operacion: state.operacion,
                    hayTexto: Boolean(textoConsulta()),
                });
                UI.actualizarContador(total, state.propiedades.length);
                UI.mostrarAviso([...avisos].join(' '));
                UI.mostrarMensajeVacio(state.propiedades.length === 0, total);
            } catch (error) {
                if (controller.signal.aborted || state.abortController !== controller || error.name === 'AbortError') return;
                state.propiedades = [];
                MapManager.renderizarMarcadores([]);
                emitir('observatorio:resultados', { propiedades: [], total: 0, operacion: state.operacion, hayTexto: false });
                document.getElementById('results-count').textContent = 'Búsqueda no disponible';
                UI.mostrarMensajeVacio(false);
                UI.mostrarAviso('');
                UI.mostrarError(error.message || 'No pudimos actualizar el mapa. Volvé a intentar.');
            } finally {
                if (state.abortController === controller) UI.mostrarCargando(false);
            }
        }
    }

    // Agrupa por solapamiento de etiquetas en píxeles, no por distancia geográfica.
    // El ancla siempre es un punto original de un aviso; no se promedian coordenadas.
    function agruparMarcadores(propiedades, proyectar) {
        const exactos = new Map();
        propiedades.forEach((p) => {
            const clave = p.latitud + ',' + p.longitud;
            if (!exactos.has(clave)) exactos.set(clave, []);
            exactos.get(clave).push(p);
        });
        const grupos = [];
        exactos.forEach((grupo) => {
            const pixel = proyectar(grupo[0]);
            const cercano = grupos.find((otro) => Math.abs(pixel.x - otro.pixel.x) < 120 && Math.abs(pixel.y - otro.pixel.y) < 48);
            if (cercano) cercano.avisos.push(...grupo);
            else grupos.push({ pixel, avisos: [...grupo] });
        });
        return grupos.map((grupo) => grupo.avisos);
    }

    class MapManager {
        static map = null;
        static esMapLibre = false;
        static markersLayer = null;
        static markerMap = new Map();
        static marcadores = [];
        static puntoMarker = null;
        static popup = null;
        static grupoExpandido = null;
        static estiloInicial = null;
        static fuenteEdificiosMapTiler = null;
        static solicitudEstilo = null;

        static init() {
            this.esMapLibre = document.getElementById('map').dataset.engine === 'maplibre';
            if (this.esMapLibre) {
                const gl = MAPLIBRE();
                if (!gl) throw new Error('Falta cargar MapLibre. Seguí los pasos de la guía del mapa.');
                const config = JSON.parse(document.getElementById('map-config')?.textContent || '{}');
                const clave = String(config.maptilerApiKey || '').trim();
                if (!clave) throw new Error('Falta configurar MAPTILER_API_KEY en .env o en Render para mostrar el mapa.');
                const estilo = `https://api.maptiler.com/maps/streets-v4/style.json?key=${encodeURIComponent(clave)}`;
                this.estiloInicial = estilo;
                this.map = new gl.Map({
                    container: 'map', style: estilo,
                    center: [RAFAELA[1], RAFAELA[0]], zoom: 15.3, pitch: 45, bearing: -17,
                    canvasContextAttributes: { antialias: true },
                });
                this.map.addControl(new gl.NavigationControl(), 'bottom-right');
                this.map.on('style.load', () => this.agregarEdificios());
                this.agregarLogoMapTiler();
            } else {
                this.map = L.map('map', { center: RAFAELA, zoom: 14, zoomControl: false });
                L.control.zoom({ position: 'bottomright' }).addTo(this.map);
                L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}', {
                    attribution: 'Tiles © Esri · OpenStreetMap contributors', maxZoom: 19,
                }).addTo(this.map);
                this.markersLayer = L.featureGroup().addTo(this.map);
            }
            this.map.on('click', (evento) => {
                if (evento.originalEvent?.target?.closest('.property-marker, .search-point, .shared-location-stack-popup')) return;
                if (state.seleccionandoPunto) this.elegirPunto(this.esMapLibre ? evento.lngLat : evento.latlng);
                else { this.cerrarPopup(); CardManager.cerrar(); }
            });
            this.map.on('moveend', () => this.renderizarMarcadores(state.propiedades));
            this.map.on('movestart', () => this.cerrarPopup());
            if (!this.esMapLibre) this.map.on('zoomend', () => this.renderizarMarcadores(state.propiedades));
        }
        static async cambiarEstilo(nombre) {
            const mapas = { calles: 'streets-v4', oscuro: 'streets-v4-dark', satelite: 'hybrid-v4' };
            if (!this.esMapLibre || !this.estiloInicial || !Object.hasOwn(mapas, nombre)) return false;
            if (nombre === state.estiloMapa) return true;
            this.solicitudEstilo?.abort();
            const controller = new AbortController();
            this.solicitudEstilo = controller;
            UI.estilosCargando(true);
            UI.errorEstilo('');
            try {
                // Validar el estilo antes de reemplazar el fondo que está funcionando.
                const url = new URL(this.estiloInicial);
                url.pathname = '/maps/' + mapas[nombre] + '/style.json';
                const cargar = async (direccion) => {
                    const respuesta = await fetch(direccion, { signal: controller.signal });
                    if (!respuesta.ok) throw new Error('No pudimos cargar esa vista. Volvé a intentar.');
                    const estilo = await respuesta.json();
                    if (estilo.version !== 8 || !Array.isArray(estilo.layers) || !estilo.sources) {
                        throw new Error('No pudimos cargar esa vista. Volvé a intentar.');
                    }
                    return estilo;
                };
                const estilo = await cargar(url.href);
                if (controller.signal.aborted || this.solicitudEstilo !== controller) return false;
                this.recordarFuenteEdificios(this.map.getStyle());
                if (nombre === 'satelite' && !this.fuenteEdificiosMapTiler) {
                    this.recordarFuenteEdificios(await cargar(this.estiloInicial));
                }
                if (controller.signal.aborted || this.solicitudEstilo !== controller) return false;
                const camara = { center: this.map.getCenter(), zoom: this.map.getZoom(),
                    pitch: this.map.getPitch(), bearing: this.map.getBearing() };
                this.cerrarPopup();
                this.map.setStyle(estilo, { diff: false });
                this.map.jumpTo(camara);
                state.estiloMapa = nombre;
                UI.actualizarEstilo();
                return true;
            } catch (error) {
                if (!controller.signal.aborted && this.solicitudEstilo === controller) {
                    UI.errorEstilo('No pudimos cargar esa vista. Volvé a intentar.');
                }
                return false;
            } finally {
                if (this.solicitudEstilo === controller) UI.estilosCargando(false);
            }
        }
        static recordarFuenteEdificios(estilo) {
            const capa = estilo?.layers?.find(c => c['source-layer'] === 'building' && c.source);
            const fuente = estilo?.sources?.[capa?.source];
            if (fuente?.type === 'vector') this.fuenteEdificiosMapTiler = { ...fuente };
        }
        static agregarLogoMapTiler() {
            // El plan Free exige mostrar el logo además de la atribución del mapa.
            let contenedor;
            this.map.addControl({
                onAdd() {
                    contenedor = document.createElement('div');
                    contenedor.className = 'maplibregl-ctrl maptiler-logo';
                    const enlace = document.createElement('a');
                    enlace.href = 'https://www.maptiler.com/';
                    enlace.target = '_blank';
                    enlace.rel = 'noopener noreferrer';
                    const logo = document.createElement('img');
                    logo.src = 'https://api.maptiler.com/resources/logo.svg';
                    logo.alt = 'MapTiler';
                    logo.width = 110;
                    enlace.append(logo);
                    contenedor.append(enlace);
                    return contenedor;
                },
                onRemove() { contenedor.remove(); },
            }, 'bottom-left');
        }
        static agregarEdificios() {
            if (this.map.getLayer('observatorio-edificios')) return;
            const estilo = this.map.getStyle();
            const capas = estilo.layers;
            this.recordarFuenteEdificios(estilo);
            const existente = capas.find((capa) => capa.type === 'fill-extrusion' && capa['source-layer'] === 'building');
            if (existente) {
                this.map.setLayoutProperty(existente.id, 'visibility', 'visible');
                return;
            }
            const edificios = capas.find(c => c['source-layer'] === 'building' && c.source);
            let fuente = edificios?.source;
            if (!fuente) {
                // Satélite trae imágenes y etiquetas, sin polígonos de edificios.
                // Reutilizar Planet v4 de Calles, del mismo proveedor y con su clave.
                if (!this.fuenteEdificiosMapTiler) return;
                fuente = 'observatorio-planet-v4';
                if (!this.map.getSource(fuente)) this.map.addSource(fuente, this.fuenteEdificiosMapTiler);
            }
            const etiqueta = capas.find((capa) => capa.type === 'symbol' && capa.layout?.['text-field']);
            this.map.addLayer({
                id: 'observatorio-edificios', source: fuente, 'source-layer': 'building',
                type: 'fill-extrusion', minzoom: 15, filter: ['!=', ['get', 'hide_3d'], true],
                paint: {
                    'fill-extrusion-color': '#c4c6b9',
                    // Planet v4 usa height/height_min. El respaldo de 6 m es ilustrativo.
                    'fill-extrusion-height': ['coalesce', ['get', 'height'], 6],
                    'fill-extrusion-base': ['coalesce', ['get', 'height_min'], 0],
                    'fill-extrusion-opacity': 0.65,
                },
            }, etiqueta?.id);
        }
        static proyectar(p) {
            return this.esMapLibre ? this.map.project([p.longitud, p.latitud])
                : this.map.latLngToContainerPoint([p.latitud, p.longitud]);
        }
        static crearMarcador(punto, elemento, evento, etiqueta, puntoBusqueda = false) {
            if (this.esMapLibre) {
                elemento.setAttribute('role', 'button');
                elemento.setAttribute('aria-label', etiqueta);
                elemento.tabIndex = 0;
                elemento.addEventListener('click', (e) => { e.stopPropagation(); evento(); });
                elemento.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); evento(); }
                });
                return new (MAPLIBRE().Marker)({ element: elemento, anchor: 'bottom' })
                    .setLngLat([punto.lng, punto.lat]).addTo(this.map);
            }
            const marker = L.marker([punto.lat, punto.lng], {
                icon: L.divIcon({
                    className: 'custom-leaflet-marker-wrapper', html: elemento.outerHTML,
                    iconSize: puntoBusqueda ? [28, 36] : [112, 40],
                    iconAnchor: puntoBusqueda ? [14, 36] : [56, 40],
                }), title: etiqueta, alt: etiqueta, riseOnHover: true,
            });
            marker.on('click', evento);
            if (puntoBusqueda) marker.addTo(this.map);
            else this.markersLayer.addLayer(marker);
            return marker;
        }
        static renderizarMarcadores(propiedades) {
            if (!this.map) return;
            this.cerrarPopup();
            this.marcadores.forEach((marker) => marker.remove());
            this.marcadores = [];
            this.markersLayer?.clearLayers();
            this.markerMap.clear();
            agruparMarcadores(propiedades, (p) => this.proyectar(p)).forEach((grupo) => {
                const p = grupo.find((dato) => dato.id === state.propiedadSeleccionada?.id) || grupo[0];
                const elemento = document.createElement('div');
                elemento.className = 'property-marker' + (grupo.length > 1 ? ' marker-cluster' : '');
                if (grupo.some((dato) => dato.id === state.propiedadSeleccionada?.id)) elemento.classList.add('active');
                const dibujo = document.createElement('span');
                dibujo.className = 'marker-icon';
                dibujo.textContent = grupo.length > 1 ? '🏘️' : iconoTipo(p.tipo);
                dibujo.setAttribute('aria-hidden', 'true');
                const texto = document.createElement('span');
                texto.className = 'marker-text';
                texto.textContent = grupo.length > 1 ? grupo.length + ' avisos' : formatearPrecio(p, state.operacion, true);
                elemento.append(dibujo, texto);
                const mismoPunto = grupo.every((dato) => dato.latitud === p.latitud && dato.longitud === p.longitud);
                const etiqueta = grupo.length > 1
                    ? (this.puedeAbrirColumna(grupo)
                        ? 'Elegir entre ' + grupo.length + (mismoPunto ? ' avisos en este punto' : ' avisos cercanos')
                        : 'Acercar para explorar ' + grupo.length + ' avisos')
                    : (p.tipo || 'Inmueble') + ': ' + formatearPrecio(p, state.operacion);
                const marker = this.crearMarcador({ lat: p.latitud, lng: p.longitud }, elemento,
                    () => this.abrirGrupo(grupo), etiqueta);
                this.marcadores.push(marker);
                grupo.forEach((dato) => this.markerMap.set(dato.id, marker));
            });
        }
        static puedeAbrirColumna(grupo) {
            if (grupo.every(p => p.latitud === grupo[0].latitud && p.longitud === grupo[0].longitud)) return true;
            if (this.map.getZoom() >= Math.min(ZOOM_MAXIMO_GRUPOS, this.map.getMaxZoom?.() || 22)) return true;
            const pixeles = grupo.map(p => this.proyectar(p));
            // Puntos casi superpuestos en pantalla, sin deducir identidad ni distancia.
            return Math.max(...pixeles.map(p => p.x)) - Math.min(...pixeles.map(p => p.x)) <= 12
                && Math.max(...pixeles.map(p => p.y)) - Math.min(...pixeles.map(p => p.y)) <= 12;
        }
        static abrirGrupo(grupo) {
            if (grupo.length === 1) { CardManager.mostrar(grupo[0]); this.seleccionarMarcador(grupo[0].id); return; }
            if (this.puedeAbrirColumna(grupo)) {
                const clave = grupo.map(p => p.id).join(',');
                if (this.grupoExpandido === clave) this.cerrarPopup();
                else this.abrirColumna(grupo, clave);
                return;
            }
            const maxZoom = Math.min(ZOOM_MAXIMO_GRUPOS, this.map.getMaxZoom?.() || 22);
            if (this.map.getZoom() < maxZoom) {
                const posiciones = grupo.map((p) => this.esMapLibre ? [p.longitud, p.latitud] : [p.latitud, p.longitud]);
                const bounds = this.esMapLibre ? posiciones.reduce((b, punto) => b.extend(punto), new (MAPLIBRE().LngLatBounds)()) : L.latLngBounds(posiciones);
                this.map.fitBounds(bounds, { padding: this.esMapLibre ? 100 : [100, 100], maxZoom: Math.min(maxZoom, this.map.getZoom() + 2) });
                return;
            }
        }
        static abrirColumna(grupo, clave) {
            const contenido = document.createElement('div');
            contenido.className = 'shared-location-stack';
            const mismoPunto = grupo.every(p => p.latitud === grupo[0].latitud && p.longitud === grupo[0].longitud);
            contenido.title = (mismoPunto ? 'Comparten un punto publicado.' : 'Están cerca en esta vista.')
                + ' Revisá la precisión de cada aviso.';
            contenido.setAttribute('role', 'group');
            contenido.setAttribute('aria-label', grupo.length + (mismoPunto ? ' avisos en el mismo punto' : ' avisos cercanos en esta vista'));
            const cerrar = document.createElement('button');
            cerrar.type = 'button'; cerrar.className = 'shared-location-close';
            cerrar.textContent = '×';
            cerrar.setAttribute('aria-label', 'Cerrar avisos del grupo');
            cerrar.addEventListener('click', (e) => { e.stopPropagation(); this.cerrarPopup(); });
            const ventana = document.createElement('div');
            ventana.className = 'shared-location-viewport';
            ventana.addEventListener('wheel', (e) => e.stopPropagation());
            grupo.forEach((p) => {
                const boton = document.createElement('button');
                boton.type = 'button';
                boton.className = 'property-marker shared-location-marker';
                boton.textContent = iconoTipo(p.tipo) + ' ' + formatearPrecio(p, state.operacion, true);
                const descripcion = (p.tipo || 'Inmueble') + ' · ' + (p.direccion || p.titulo || 'Sin dirección')
                    + ' · ' + formatearPrecio(p, state.operacion) + ' · ' + (p.fuente || 'Fuente no informada');
                boton.title = descripcion;
                boton.setAttribute('aria-label', descripcion);
                boton.addEventListener('click', (e) => {
                    e.stopPropagation(); this.cerrarPopup(); CardManager.mostrar(p); this.seleccionarMarcador(p.id);
                });
                ventana.append(boton);
            });
            contenido.append(cerrar, ventana);
            this.mostrarPopup(grupo[0], contenido, true);
            this.grupoExpandido = clave;
        }
        static mostrarPopup(p, contenido, columna = false) {
            this.cerrarPopup();
            const opciones = { maxWidth: columna ? '128px' : '320px', className: columna ? 'shared-location-stack-popup' : '' };
            if (columna) {
                Object.assign(opciones, this.ajustarColumna(p, contenido));
                opciones.closeButton = false;
                opciones.closeOnClick = false;
            }
            if (this.esMapLibre) {
                this.popup = new (MAPLIBRE().Popup)(opciones)
                    .setLngLat([p.longitud, p.latitud]).setDOMContent(contenido).addTo(this.map);
            } else this.popup = L.popup({ ...opciones, maxHeight: columna ? undefined : 260 })
                .setLatLng([p.latitud, p.longitud]).setContent(contenido).openOn(this.map);
        }
        static ajustarColumna(p, contenido) {
            const mapa = document.getElementById('map').getBoundingClientRect();
            const cabecera = document.querySelector('.floating-header')?.getBoundingClientRect();
            const filtros = document.getElementById('filter-dock').getBoundingClientRect();
            const anchoMapa = mapa.width || window.innerWidth || 1280;
            const arriba = (cabecera?.bottom || 100) - (mapa.top || 0) + 24;
            const abajo = (filtros.top || (window.innerHeight || 800) - 150) - (mapa.top || 0) - 16;
            const punto = this.proyectar(p);
            const ventana = contenido.children[1];
            const alto = Math.min(ventana.children.length * 38 + Math.max(0, ventana.children.length - 1) * 8 + 8,
                Math.max(46, abajo - arriba));
            ventana.style.maxHeight = alto + 'px';
            // Columna preferentemente a la izquierda del pin. Son offsets de UI.
            const ancho = 128, separacion = 68;
            const izquierda = punto.x - separacion - ancho;
            const abrirIzquierda = izquierda >= 8 || anchoMapa - punto.x - separacion - ancho < 8;
            const inicio = Math.max(8, Math.min(abrirIzquierda ? izquierda : punto.x + separacion, anchoMapa - ancho - 8));
            const centroY = Math.max(arriba + alto / 2, Math.min(punto.y - 18, abajo - alto / 2));
            return {
                anchor: abrirIzquierda ? 'right' : 'left',
                offset: [inicio + (abrirIzquierda ? ancho : 0) - punto.x, centroY - punto.y],
            };
        }
        static cerrarPopup() { this.popup?.remove(); this.popup = null; this.grupoExpandido = null; }
        static seleccionarMarcador(id) {
            this.deseleccionarTodos();
            const marker = this.markerMap.get(id);
            marker?.getElement()?.classList.add('active');
            const p = state.propiedades.find((dato) => dato.id === id);
            if (!p) return;
            if (this.esMapLibre) this.map.easeTo({ center: [p.longitud, p.latitud], duration: 350 });
            else this.map.panTo([p.latitud, p.longitud], { animate: true });
        }
        static deseleccionarTodos() {
            document.querySelectorAll('.property-marker').forEach((el) => el.classList.remove('active'));
        }
        static elegirPunto(punto) {
            state.punto = { lat: punto.lat, lng: punto.lng };
            state.seleccionandoPunto = false;
            CardManager.cerrar();
            this.actualizarPunto();
            UI.actualizarPunto();
            PropertyApiClient.buscarPropiedades();
        }
        static actualizarPunto() {
            this.puntoMarker?.remove(); this.puntoMarker = null;
            if (!state.punto) return;
            const pin = document.createElement('div'); pin.className = 'search-point';
            pin.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 22s8-7 8-13a8 8 0 0 0-16 0c0 6 8 13 8 13Z"/><circle cx="12" cy="9" r="2"/></svg>';
            this.puntoMarker = this.crearMarcador(state.punto, pin, () => {}, 'Punto elegido para buscar alrededor', true);
        }
    }

    class CardManager {
        static comentariosController = null;
        static comentariosActuales = [];
        static totalComentarios = 0;
        static enviandoComentario = false;

        static init() {
            document.getElementById('carousel-btn-prev').addEventListener('click', () => this.cambiarFoto(-1));
            document.getElementById('carousel-btn-next').addEventListener('click', () => this.cambiarFoto(1));
            document.getElementById('card-close-btn').addEventListener('click', () => this.cerrar());
            document.getElementById('comentario-texto')?.addEventListener('input', (e) => {
                const largo = (e.target.value || '').length;
                document.getElementById('comentario-contador').textContent = largo + ' / 500';
                this.mostrarErrorComentario('');
            });
            document.getElementById('form-comentario')?.addEventListener('submit', (e) => this.enviarComentario(e));
        }
        static mostrar(p) {
            state.propiedadSeleccionada = p; state.fotoIndex = 0;
            document.getElementById('card-price').textContent = formatearPrecio(p, state.operacion);
            document.getElementById('card-operation-tag').textContent = state.operacion === 'venta' ? 'En venta' : 'En alquiler';
            document.getElementById('card-title').textContent = p.titulo || (p.tipo || 'Inmueble') + ' en ' + state.operacion;
            document.getElementById('card-location').textContent = [p.direccion, p.zona, p.ciudad].filter(Boolean).join(' · ') || 'Dirección no informada';
            document.getElementById('card-location-precision').textContent = p.ubicacion_info?.precision === 'geocodificada_direccion'
                ? 'Ubicación estimada por dirección; no garantiza la puerta exacta. © OpenStreetMap contributors'
                : p.ubicacion_aproximada === false ? 'Punto tratado como exacto según la política de la fuente.'
                : p.ubicacion_aproximada === true ? 'Ubicación aproximada: el pin representa el centro del área publicada.'
                : 'Precisión de ubicación desconocida: el pin puede ser una referencia de zona.';
            const specs = document.getElementById('card-specs'); specs.replaceChildren();
            [['dormitorios', '🛏️ dorm.'], ['ambientes', '📐 amb.'], ['banos', '🚿 baños']].forEach(([campo, nombre]) => {
                if (p[campo] === null || p[campo] === undefined) return;
                const etiqueta = document.createElement('span'); etiqueta.className = 'spec-item';
                etiqueta.textContent = p[campo] + ' ' + nombre; specs.appendChild(etiqueta);
            });
            const features = document.getElementById('card-features'); features.replaceChildren();
            const tags = [...new Set((p.caracteristicas || '')
                .split(/[\r\n;]+/)
                .map((t) => t.trim())
                .filter(Boolean))].slice(0, 4);
            tags.forEach((texto) => {
                const etiqueta = document.createElement('span'); etiqueta.className = 'feature-pill';
                etiqueta.textContent = texto; features.appendChild(etiqueta);
            });
            document.getElementById('card-cta-btn').href = p.url_original || '#';
            document.getElementById('card-agency-source').textContent = 'Inmobiliaria: ' + (p.fuente || 'No informada');
            this.actualizarFoto();
            const seccionComentarios = document.getElementById('card-comments-section');
            if (seccionComentarios) {
                seccionComentarios.open = false;
                document.getElementById('comentario-texto').value = '';
                document.getElementById('comentario-contador').textContent = '0 / 500';
                this.mostrarErrorComentario('');
                this.cargarComentarios(p.id);
            }
            document.getElementById('property-card').hidden = false;
            emitir('observatorio:ficha', { propiedad: p });
        }
        static crearElementoComentario(c) {
            const item = document.createElement('div');
            item.className = 'comment-item';
            const meta = document.createElement('div');
            meta.className = 'comment-meta';
            const autor = document.createElement('span');
            autor.className = 'comment-author';
            autor.textContent = c.autor || 'Anónimo';
            const fecha = document.createElement('span');
            fecha.className = 'comment-date';
            fecha.textContent = formatearFechaComentario(c.creado_en);
            meta.append(autor, fecha);
            const texto = document.createElement('p');
            texto.className = 'comment-text';
            texto.textContent = c.texto || '';
            item.append(meta, texto);
            return item;
        }
        static renderizarComentarios(comentarios, total = comentarios.length) {
            this.comentariosActuales = Array.isArray(comentarios) ? comentarios : [];
            this.totalComentarios = Number.isFinite(Number(total)) ? Number(total) : this.comentariosActuales.length;
            const badge = document.getElementById('card-comments-badge');
            const lista = document.getElementById('card-comments-list');
            const estadoTexto = document.getElementById('card-comments-status');
            if (!badge || !lista || !estadoTexto) return;
            badge.textContent = String(this.totalComentarios);
            lista.replaceChildren();
            this.comentariosActuales.forEach((c) => lista.append(this.crearElementoComentario(c)));
            estadoTexto.hidden = this.comentariosActuales.length > 0;
            if (!estadoTexto.hidden) {
                estadoTexto.textContent = 'Todavía no hay comentarios en esta publicación.';
            }
        }
        static mostrarErrorComentario(texto) {
            const errorEl = document.getElementById('comentario-error');
            if (!errorEl) return;
            errorEl.textContent = texto;
            errorEl.hidden = !texto;
        }
        static async cargarComentarios(propiedadId) {
            this.comentariosController?.abort();
            const controller = new AbortController();
            this.comentariosController = controller;
            const badge = document.getElementById('card-comments-badge');
            const lista = document.getElementById('card-comments-list');
            const estadoTexto = document.getElementById('card-comments-status');
            if (!badge || !lista || !estadoTexto) return;
            this.comentariosActuales = [];
            this.totalComentarios = 0;
            badge.textContent = '…';
            lista.replaceChildren();
            estadoTexto.hidden = false;
            estadoTexto.textContent = 'Cargando comentarios…';
            try {
                const url = new URL('/api/propiedades/' + encodeURIComponent(propiedadId) + '/comentarios/', ORIGEN);
                const respuesta = await fetch(url.href, {
                    headers: { Accept: 'application/json' },
                    signal: controller.signal,
                });
                if (controller.signal.aborted || this.comentariosController !== controller) return;
                if (state.propiedadSeleccionada?.id !== propiedadId) return;
                const datos = await respuesta.json();
                if (!respuesta.ok || !Array.isArray(datos.comentarios)) {
                    throw new Error(datos.error || 'No pudimos cargar los comentarios.');
                }
                this.renderizarComentarios(datos.comentarios, datos.total);
            } catch (error) {
                if (controller.signal.aborted || this.comentariosController !== controller || error.name === 'AbortError') return;
                badge.textContent = '0';
                estadoTexto.hidden = false;
                estadoTexto.textContent = 'No pudimos cargar los comentarios en este momento.';
            }
        }
        static async enviarComentario(evento) {
            evento.preventDefault();
            const propiedad = state.propiedadSeleccionada;
            if (!propiedad || this.enviandoComentario) return;
            const inputAutor = document.getElementById('comentario-autor');
            const inputTexto = document.getElementById('comentario-texto');
            const boton = document.getElementById('btn-enviar-comentario');
            const autor = (inputAutor?.value || '').trim();
            const texto = (inputTexto?.value || '').trim();
            if (autor.length > 60) {
                this.mostrarErrorComentario('El alias puede tener hasta 60 caracteres.');
                return;
            }
            if (texto.length < 3) {
                this.mostrarErrorComentario('El comentario debe tener al menos 3 caracteres.');
                return;
            }
            if (texto.length > 500) {
                this.mostrarErrorComentario('El comentario puede tener hasta 500 caracteres.');
                return;
            }
            this.enviandoComentario = true;
            this.mostrarErrorComentario('');
            if (boton) {
                boton.disabled = true;
                boton.textContent = 'Publicando…';
            }
            try {
                const url = new URL('/api/propiedades/' + encodeURIComponent(propiedad.id) + '/comentarios/', ORIGEN);
                const headers = {
                    Accept: 'application/json',
                    'Content-Type': 'application/json',
                };
                const tokenCsrf = leerCookie('csrftoken');
                if (tokenCsrf) headers['X-CSRFToken'] = tokenCsrf;
                const respuesta = await fetch(url.href, {
                    method: 'POST',
                    headers,
                    credentials: 'same-origin',
                    body: JSON.stringify({ autor, texto }),
                });
                let datos = {};
                try { datos = await respuesta.json(); }
                catch { throw new Error('El servidor no pudo procesar el comentario. Reintentá en unos segundos.'); }
                if (!respuesta.ok || !datos.comentario) {
                    throw new Error(datos.error || 'No pudimos publicar el comentario.');
                }
                if (state.propiedadSeleccionada?.id === propiedad.id) {
                    inputTexto.value = '';
                    document.getElementById('comentario-contador').textContent = '0 / 500';
                    document.getElementById('card-comments-section').open = true;
                    this.renderizarComentarios(
                        [datos.comentario, ...this.comentariosActuales],
                        this.totalComentarios + 1,
                    );
                }
            } catch (error) {
                this.mostrarErrorComentario(error.message || 'No pudimos publicar el comentario.');
            } finally {
                this.enviandoComentario = false;
                if (boton) {
                    boton.disabled = false;
                    boton.textContent = 'Publicar';
                }
            }
        }
        static actualizarFoto() {
            const fotos = state.propiedadSeleccionada?.fotos || [], imagen = document.getElementById('card-image');
            const placeholder = document.getElementById('card-image-placeholder');
            imagen.hidden = !fotos.length; placeholder.hidden = !!fotos.length;
            if (fotos.length) {
                imagen.src = fotos[state.fotoIndex];
                imagen.onerror = () => { imagen.hidden = true; placeholder.hidden = false; };
            } else { imagen.removeAttribute('src'); imagen.onerror = null; }
            const contador = document.getElementById('card-carousel-counter');
            contador.hidden = !fotos.length; contador.textContent = (state.fotoIndex + 1) + ' / ' + fotos.length;
            document.getElementById('carousel-btn-prev').hidden = fotos.length < 2;
            document.getElementById('carousel-btn-next').hidden = fotos.length < 2;
        }
        static cambiarFoto(paso) {
            const fotos = state.propiedadSeleccionada?.fotos || [];
            if (fotos.length < 2) return;
            state.fotoIndex = (state.fotoIndex + paso + fotos.length) % fotos.length; this.actualizarFoto();
        }
        static cerrar() {
            this.comentariosController?.abort();
            this.comentariosController = null;
            document.getElementById('property-card').hidden = true;
            state.propiedadSeleccionada = null; MapManager.deseleccionarTodos();
            emitir('observatorio:ficha', { propiedad: null });
        }
    }

    class UI {
        static debounce = null;
        static init() {
            document.querySelectorAll('[data-estilo-mapa]').forEach((btn) => {
                btn.addEventListener('click', async () => {
                    if (btn.disabled || btn.classList.contains('active')) return;
                    if (await MapManager.cambiarEstilo(btn.dataset.estiloMapa)) {
                        document.getElementById('estilos-menu').open = false;
                    }
                });
            });
            this.actualizarEstilo();
            this.estilosCargando(false);
            ['alquiler', 'venta'].forEach((operacion) => document.getElementById('btn-op-' + operacion).addEventListener('click', () => {
                if (state.operacion === operacion) return;
                state.operacion = operacion; state.precioMin = ''; state.precioMax = '';
                emitir('observatorio:operacion', { operacion });
                document.getElementById('precio-min').value = ''; document.getElementById('precio-max').value = '';
                document.getElementById('moneda-precio').textContent = operacion === 'alquiler' ? 'ARS' : 'USD';
                ['alquiler', 'venta'].forEach((op) => this.activar(document.getElementById('btn-op-' + op), op === operacion));
                this.actualizarTipos();
                document.getElementById('tipos-menu').open = false;
                this.buscar();
            }));
            document.querySelectorAll('[data-filter-tipo]').forEach((btn) => {
                btn.textContent = iconoTipo(btn.dataset.filterTipo) + ' ' + btn.dataset.filterTipo;
                btn.addEventListener('click', () => {
                    if (!btn.disabled && !btn.hidden) this.seleccionarTipo(state.tipo === btn.dataset.filterTipo ? null : btn.dataset.filterTipo);
                });
            });
            this.actualizarTipos();
            document.getElementById('btn-todos-tipos').addEventListener('click', () => this.seleccionarTipo(null));
            document.querySelectorAll('[data-filter-caracteristica]').forEach((btn) => btn.addEventListener('click', () => {
                const valor = btn.dataset.filterCaracteristica;
                if (state.caracteristicas.has(valor)) state.caracteristicas.delete(valor); else state.caracteristicas.add(valor);
                this.activar(btn, state.caracteristicas.has(valor)); this.buscar();
            }));
            document.getElementById('form-busqueda').addEventListener('submit', (e) => { e.preventDefault(); this.buscar(); });
            document.getElementById('busqueda').addEventListener('input', (e) => {
                state.texto = e.target.value; clearTimeout(this.debounce);
                this.debounce = setTimeout(() => this.buscar(), 450);
            });
            [['dormitorios', 'dormitorios'], ['precio-min', 'precioMin'], ['precio-max', 'precioMax']].forEach(([id, campo]) => {
                document.getElementById(id).addEventListener('change', (e) => { state[campo] = e.target.value; this.buscar(); });
            });
            document.getElementById('btn-elegir-punto').addEventListener('click', () => {
                state.seleccionandoPunto = !state.seleccionandoPunto; this.actualizarPunto();
            });
            document.getElementById('btn-usar-centro').addEventListener('click', () => MapManager.elegirPunto(MapManager.map.getCenter()));
            document.getElementById('btn-quitar-punto').addEventListener('click', () => {
                state.punto = null; state.seleccionandoPunto = false; MapManager.actualizarPunto(); this.actualizarPunto(); this.buscar();
            });
            document.getElementById('distancia').addEventListener('change', (e) => {
                state.radio = Number(e.target.value); if (state.punto) this.buscar();
            });
            document.getElementById('incluir-aproximadas').addEventListener('change', (e) => {
                state.incluirAproximadas = e.target.checked; if (state.punto) this.buscar();
            });
            ['btn-limpiar-filtros', 'btn-reset-empty'].forEach((id) => document.getElementById(id).addEventListener('click', () => this.limpiarFiltros()));
            document.getElementById('btn-reintentar').addEventListener('click', () => this.buscar());
            document.addEventListener('keydown', (e) => {
                if (e.key !== 'Escape' || document.getElementById('comparador')?.open) return;
                ['tipos-menu', 'mas-filtros', 'estilos-menu'].forEach(id => {
                    document.getElementById(id).open = false;
                });
                state.seleccionandoPunto = false;
                this.actualizarPunto(); CardManager.cerrar(); MapManager.cerrarPopup();
            });
            document.addEventListener('click', (e) => {
                const clicEnFiltrosPanel = document.getElementById('panel-filter-slot')?.contains(e.target);
                ['tipos-menu', 'mas-filtros', 'estilos-menu'].forEach((id) => {
                    const menu = document.getElementById(id);
                    // Los desplegables del lateral comparten un área de interacción.
                    const conservarAbierto = id !== 'estilos-menu' && clicEnFiltrosPanel;
                    if (!menu.contains(e.target) && !conservarAbierto) menu.open = false;
                });
            });
            if (typeof ResizeObserver !== 'undefined') {
                new ResizeObserver(([entrada]) => {
                    document.documentElement.style.setProperty('--dock-height', entrada.target.getBoundingClientRect().height + 'px');
                }).observe(document.getElementById('filter-dock'));
            }
        }
        static actualizarEstilo() {
            const nombres = { calles: 'Calles', oscuro: 'Oscuro', satelite: 'Satélite' };
            document.getElementById('estilo-seleccionado').textContent = nombres[state.estiloMapa];
            document.querySelector('#estilos-menu summary')?.setAttribute('aria-label', 'Estilo del mapa: ' + nombres[state.estiloMapa]);
            document.querySelectorAll('[data-estilo-mapa]').forEach(btn => this.activar(btn, btn.dataset.estiloMapa === state.estiloMapa));
        }
        static estilosCargando(cargando) {
            document.getElementById('estilos-menu').setAttribute('aria-busy', String(cargando));
            document.querySelectorAll('[data-estilo-mapa]').forEach(btn => {
                const disponible = MapManager.esMapLibre && Boolean(MapManager.estiloInicial);
                btn.disabled = cargando || !disponible;
                btn.title = disponible ? '' : 'Vista no disponible en este momento';
            });
        }
        static errorEstilo(texto) {
            const aviso = document.getElementById('estilo-error');
            aviso.textContent = texto; aviso.hidden = !texto;
        }
        static actualizarTipos() {
            const botones = [...document.querySelectorAll('[data-filter-tipo]')];
            const campo = state.operacion === 'alquiler' ? 'disponibleAlquiler' : 'disponibleVenta';
            botones.forEach((btn) => {
                const disponible = btn.dataset[campo] === 'true';
                btn.hidden = !disponible;
                btn.disabled = !disponible;
            });
            if (state.tipo !== null && !botones.some(btn => !btn.hidden && btn.dataset.filterTipo === state.tipo)) {
                state.tipo = null;
            }
            botones.forEach(btn => this.activar(btn, btn.dataset.filterTipo === state.tipo));
            this.activar(document.getElementById('btn-todos-tipos'), state.tipo === null);
            document.getElementById('tipo-seleccionado').textContent = state.tipo ? iconoTipo(state.tipo) + ' ' + state.tipo : 'Todos los tipos';
            const vacios = document.getElementById('tipos-vacios');
            vacios.hidden = botones.some(btn => !btn.hidden);
            vacios.textContent = 'Sin tipos disponibles para ' + (state.operacion === 'alquiler' ? 'alquilar.' : 'comprar.');
        }
        static seleccionarTipo(tipo) {
            state.tipo = tipo;
            this.actualizarTipos();
            document.getElementById('tipos-menu').open = false;
            this.buscar();
        }
        static buscar() {
            clearTimeout(this.debounce); CardManager.cerrar(); MapManager.cerrarPopup();
            PropertyApiClient.buscarPropiedades();
        }
        static activar(btn, activo) { btn.classList.toggle('active', activo); btn.setAttribute('aria-pressed', String(activo)); }
        static limpiarFiltros() {
            state.tipo = null; state.texto = ''; state.caracteristicas.clear();
            state.dormitorios = ''; state.precioMin = ''; state.precioMax = '';
            state.punto = null; state.radio = 1000; state.incluirAproximadas = false; state.seleccionandoPunto = false;
            ['busqueda', 'dormitorios', 'precio-min', 'precio-max'].forEach((id) => { document.getElementById(id).value = ''; });
            document.getElementById('distancia').value = '1000'; document.getElementById('incluir-aproximadas').checked = false;
            this.actualizarTipos();
            document.querySelectorAll('[data-filter-caracteristica]').forEach((btn) => this.activar(btn, false));
            document.getElementById('tipos-menu').open = false; document.getElementById('mas-filtros').open = false;
            MapManager.actualizarPunto(); this.actualizarPunto(); this.buscar();
        }
        static actualizarPunto() {
            const btn = document.getElementById('btn-elegir-punto');
            this.activar(btn, state.seleccionandoPunto);
            btn.textContent = state.seleccionandoPunto ? '✕ Cancelar selección' : state.punto ? '📍 Cambiar punto' : '📍 Elegir punto';
            document.getElementById('map').classList.toggle('eligiendo-punto', state.seleccionandoPunto);
            document.getElementById('punto-detalles').hidden = !(state.punto || state.seleccionandoPunto);
            document.getElementById('btn-quitar-punto').hidden = !state.punto;
            document.getElementById('btn-usar-centro').hidden = !state.seleccionandoPunto;
            document.getElementById('punto-ayuda').textContent = state.seleccionandoPunto
                ? 'Hacé clic en el mapa o usá su centro.' : state.punto
                ? 'Punto: ' + state.punto.lat.toFixed(5) + ', ' + state.punto.lng.toFixed(5) : '';
        }
        static actualizarContador(total, ubicadas) {
            document.getElementById('results-count').textContent = total + ' avisos · ' + ubicadas + ' con ubicación';
        }
        static progreso(cargados, total) { document.getElementById('loading-text').textContent = 'Cargando ' + cargados + ' de ' + total + ' avisos…'; }
        static mostrarCargando(cargando) {
            document.getElementById('loading-toast').hidden = !cargando;
            document.getElementById('map').setAttribute('aria-busy', String(cargando));
            if (cargando) document.getElementById('loading-text').textContent = 'Buscando propiedades…';
        }
        static mostrarAviso(texto) {
            const aviso = document.getElementById('aviso-precision'); aviso.textContent = texto; aviso.hidden = !texto;
        }
        static mostrarError(texto) {
            document.getElementById('error-text').textContent = texto;
            document.getElementById('search-error').hidden = !texto;
        }
        static mostrarMensajeVacio(mostrar, total = 0) {
            document.getElementById('empty-results-banner').hidden = !mostrar;
            document.getElementById('empty-text').textContent = total
                ? 'Hay ' + total + ' avisos, pero no tienen coordenadas para mostrarlos en el mapa.'
                : 'No encontramos inmuebles con esa combinación.';
        }
    }

    function iniciar() {
        try { MapManager.init(); CardManager.init(); UI.init(); PropertyApiClient.buscarPropiedades(); }
        catch (error) {
            UI.mostrarError(error.message); UI.mostrarCargando(false); UI.estilosCargando(false);
            document.getElementById('results-count').textContent = 'Mapa no disponible';
        }
    }
    window.ObservatorioMapa = {
        abrirPropiedad(id) {
            const propiedad = state.propiedades.find((dato) => dato.id === Number(id));
            if (!propiedad) return false;
            MapManager.cerrarPopup();
            CardManager.mostrar(propiedad);
            MapManager.seleccionarMarcador(propiedad.id);
            return true;
        },
        operacion() { return state.operacion; },
        filtros() {
            return {
                tipo: state.tipo,
                dormitorios: state.dormitorios,
                caracteristicas: [...state.caracteristicas],
            };
        },
        resultados() {
            return {
                propiedades: state.propiedades,
                total: state.total,
                operacion: state.operacion,
                hayTexto: Boolean(textoConsulta()),
            };
        },
        redimensionar() {
            window.setTimeout(() => {
                MapManager.map?.resize?.();
                MapManager.renderizarMarcadores(state.propiedades);
            }, 230);
        },
    };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar);
    else iniciar();
})();
