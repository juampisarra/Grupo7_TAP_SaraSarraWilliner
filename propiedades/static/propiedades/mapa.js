/**
 * Interfaz del Observatorio: consultas en Django y presentación del mapa.
 * MapLibre usa MapTiler al configurar su clave; sin ella utiliza OpenFreeMap.
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
    };
    const RAFAELA = [-31.253, -61.491];
    const RADIOS = [500, 1000, 2000];
    const ORIGEN = window.location.origin;
    const MAPLIBRE = () => window.maplibregl;
    const ESTILO_OPENFREEMAP = 'https://tiles.openfreemap.org/styles/bright';
    const normalizar = (texto) => String(texto || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');

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
                UI.actualizarContador(total, state.propiedades.length);
                UI.mostrarAviso([...avisos].join(' '));
                UI.mostrarMensajeVacio(state.propiedades.length === 0, total);
            } catch (error) {
                if (controller.signal.aborted || state.abortController !== controller || error.name === 'AbortError') return;
                state.propiedades = [];
                MapManager.renderizarMarcadores([]);
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

    // Distribución de botones en píxeles dentro de un selector, no coordenadas.
    function posicionesCirculares(cantidad, ancho = 112) {
        const separacion = Math.hypot(ancho + 12, 38 + 12);
        const radio = Math.max(76, Math.ceil(separacion / (2 * Math.sin(Math.PI / cantidad))));
        const centro = radio + ancho / 2 + 12;
        const posiciones = Array.from({ length: cantidad }, (_, i) => {
            const angulo = -Math.PI / 2 + i * 2 * Math.PI / cantidad;
            return { x: centro + radio * Math.cos(angulo), y: centro + radio * Math.sin(angulo), angulo };
        });
        return { centro, radio, ancho, tamano: centro * 2, posiciones };
    }

    class MapManager {
        static map = null;
        static esMapLibre = false;
        static markersLayer = null;
        static markerMap = new Map();
        static marcadores = [];
        static puntoMarker = null;
        static popup = null;
        static usaMapTiler = false;

        static init() {
            this.esMapLibre = document.getElementById('map').dataset.engine === 'maplibre';
            if (this.esMapLibre) {
                const gl = MAPLIBRE();
                if (!gl) throw new Error('Falta cargar MapLibre. Seguí los pasos de la guía del mapa.');
                const config = JSON.parse(document.getElementById('map-config')?.textContent || '{}');
                this.usaMapTiler = Boolean(config.maptilerApiKey);
                const estilo = this.usaMapTiler
                    ? `https://api.maptiler.com/maps/streets-v4/style.json?key=${encodeURIComponent(config.maptilerApiKey)}`
                    : ESTILO_OPENFREEMAP;
                this.map = new gl.Map({
                    container: 'map', style: estilo,
                    center: [RAFAELA[1], RAFAELA[0]], zoom: 15.3, pitch: 45, bearing: -17,
                    canvasContextAttributes: { antialias: true },
                });
                this.map.addControl(new gl.NavigationControl(), 'bottom-right');
                this.map.on('load', () => this.agregarEdificios());
                if (this.usaMapTiler) this.agregarLogoMapTiler();
            } else {
                this.map = L.map('map', { center: RAFAELA, zoom: 14, zoomControl: false });
                L.control.zoom({ position: 'bottomright' }).addTo(this.map);
                L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}', {
                    attribution: 'Tiles © Esri · OpenStreetMap contributors', maxZoom: 19,
                }).addTo(this.map);
                this.markersLayer = L.featureGroup().addTo(this.map);
            }
            this.map.on('click', (evento) => {
                if (evento.originalEvent?.target?.closest('.property-marker, .search-point, .shared-location-popup')) return;
                if (state.seleccionandoPunto) this.elegirPunto(this.esMapLibre ? evento.lngLat : evento.latlng);
                else CardManager.cerrar();
            });
            this.map.on('moveend', () => this.renderizarMarcadores(state.propiedades));
            this.map.on('movestart', () => this.cerrarPopup());
            if (!this.esMapLibre) this.map.on('zoomend', () => this.renderizarMarcadores(state.propiedades));
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
            const capas = this.map.getStyle().layers;
            const existente = capas.find((capa) => capa.type === 'fill-extrusion' && capa['source-layer'] === 'building');
            if (existente) {
                this.map.setLayoutProperty(existente.id, 'visibility', 'visible');
                return;
            }
            let fuente = 'observatorio-edificios';
            if (this.usaMapTiler) {
                // Reutilizar el origen del estilo: no cargar edificios de OpenFreeMap
                // sobre MapTiler ni duplicar las solicitudes de sus teselas.
                const edificios = capas.find((capa) => capa['source-layer'] === 'building' && capa.source);
                if (!edificios) return;
                fuente = edificios.source;
            } else {
                this.map.addSource(fuente, { type: 'vector', url: 'https://tiles.openfreemap.org/planet' });
            }
            const etiqueta = capas.find((capa) => capa.type === 'symbol' && capa.layout?.['text-field']);
            this.map.addLayer({
                id: 'observatorio-edificios', source: fuente, 'source-layer': 'building',
                type: 'fill-extrusion', minzoom: 15, filter: ['!=', ['get', 'hide_3d'], true],
                paint: {
                    'fill-extrusion-color': '#c4c6b9',
                    // Planet v4 usa height/height_min; OpenMapTiles usa render_*.
                    // Los 6 m de respaldo en MapTiler son ilustrativos, no medidos.
                    'fill-extrusion-height': ['coalesce', ['get', 'height'], ['get', 'render_height'], this.usaMapTiler ? 6 : 0],
                    'fill-extrusion-base': ['coalesce', ['get', 'height_min'], ['get', 'render_min_height'], 0],
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
                    ? (mismoPunto ? 'Elegir entre ' + grupo.length + ' avisos en este punto' : 'Acercar para explorar ' + grupo.length + ' avisos')
                    : (p.tipo || 'Inmueble') + ': ' + formatearPrecio(p, state.operacion);
                const marker = this.crearMarcador({ lat: p.latitud, lng: p.longitud }, elemento,
                    () => this.abrirGrupo(grupo), etiqueta);
                this.marcadores.push(marker);
                grupo.forEach((dato) => this.markerMap.set(dato.id, marker));
            });
        }
        static abrirGrupo(grupo) {
            if (grupo.length === 1) { CardManager.mostrar(grupo[0]); this.seleccionarMarcador(grupo[0].id); return; }
            const mismoPunto = grupo.every((p) => p.latitud === grupo[0].latitud && p.longitud === grupo[0].longitud);
            if (mismoPunto) { this.abrirCirculo(grupo); return; }
            const maxZoom = this.map.getMaxZoom?.() || 22;
            if (this.map.getZoom() < maxZoom) {
                const posiciones = grupo.map((p) => this.esMapLibre ? [p.longitud, p.latitud] : [p.latitud, p.longitud]);
                const bounds = this.esMapLibre ? posiciones.reduce((b, punto) => b.extend(punto), new (MAPLIBRE().LngLatBounds)()) : L.latLngBounds(posiciones);
                this.map.fitBounds(bounds, { padding: this.esMapLibre ? 100 : [100, 100], maxZoom: Math.min(maxZoom, this.map.getZoom() + 2) });
                return;
            }
            const lista = document.createElement('div');
            const descripcion = document.createElement('p');
            descripcion.textContent = 'Avisos cercanos en esta vista. Seleccioná uno para ver sus datos.';
            lista.appendChild(descripcion);
            grupo.forEach((p) => {
                const boton = document.createElement('button');
                boton.type = 'button'; boton.className = 'shared-location-option';
                boton.textContent = (p.tipo || 'Inmueble') + ' · ' + (p.direccion || p.titulo || 'Sin dirección') + ' · ' + formatearPrecio(p, state.operacion) + ' · ' + p.fuente;
                boton.addEventListener('click', () => { this.cerrarPopup(); CardManager.mostrar(p); this.seleccionarMarcador(p.id); });
                lista.appendChild(boton);
            });
            this.mostrarPopup(grupo[0], lista);
        }
        static abrirCirculo(grupo) {
            const anchoMapa = document.getElementById('map').getBoundingClientRect().width || window.innerWidth || 1280;
            const distribucion = posicionesCirculares(grupo.length, anchoMapa < 480 ? 92 : 112);
            const contenido = document.createElement('div');
            const titulo = document.createElement('p');
            titulo.className = 'shared-location-heading';
            titulo.textContent = '🏘️ Elegí uno de los ' + grupo.length + ' avisos';
            const ayuda = document.createElement('p');
            ayuda.className = 'shared-location-help';
            ayuda.textContent = 'Comparten un punto publicado. Revisá su precisión.';
            const ventana = document.createElement('div');
            ventana.className = 'shared-location-viewport';
            const circulo = document.createElement('div');
            circulo.className = 'shared-location-circle';
            circulo.style.width = circulo.style.height = distribucion.tamano + 'px';
            circulo.setAttribute('role', 'group');
            circulo.setAttribute('aria-label', grupo.length + ' avisos en el mismo punto');
            grupo.forEach((p, i) => {
                const posicion = distribucion.posiciones[i];
                const linea = document.createElement('span');
                linea.className = 'shared-location-leg';
                linea.setAttribute('aria-hidden', 'true');
                linea.style.left = linea.style.top = distribucion.centro + 'px';
                linea.style.width = distribucion.radio + 'px';
                linea.style.transform = 'rotate(' + posicion.angulo + 'rad)';
                const boton = document.createElement('button');
                boton.type = 'button';
                boton.className = 'property-marker shared-location-marker';
                boton.style.width = distribucion.ancho + 'px';
                boton.style.left = posicion.x + 'px';
                boton.style.top = posicion.y + 'px';
                boton.textContent = iconoTipo(p.tipo) + ' ' + formatearPrecio(p, state.operacion, true);
                const descripcion = (p.tipo || 'Inmueble') + ' · ' + (p.direccion || p.titulo || 'Sin dirección')
                    + ' · ' + formatearPrecio(p, state.operacion) + ' · ' + (p.fuente || 'Fuente no informada');
                boton.title = descripcion;
                boton.setAttribute('aria-label', descripcion);
                boton.addEventListener('click', (e) => {
                    e.stopPropagation(); this.cerrarPopup(); CardManager.mostrar(p); this.seleccionarMarcador(p.id);
                });
                circulo.append(linea, boton);
            });
            const centro = document.createElement('span');
            centro.className = 'shared-location-center';
            centro.style.left = centro.style.top = distribucion.centro + 'px';
            centro.textContent = '📍 ' + grupo.length + ' avisos';
            circulo.append(centro);
            ventana.append(circulo);
            contenido.append(titulo, ayuda, ventana);
            this.mostrarPopup(grupo[0], contenido, true);
        }
        static mostrarPopup(p, contenido, circular = false) {
            this.cerrarPopup();
            const opciones = { maxWidth: circular ? '640px' : '320px', className: circular ? 'shared-location-popup' : '' };
            if (circular) Object.assign(opciones, this.ajustarCirculo(p, contenido));
            if (this.esMapLibre) {
                this.popup = new (MAPLIBRE().Popup)(opciones)
                    .setLngLat([p.longitud, p.latitud]).setDOMContent(contenido).addTo(this.map);
            } else this.popup = L.popup({ maxHeight: circular ? 440 : 260, maxWidth: circular ? 640 : 320, className: circular ? 'shared-location-popup' : '' })
                .setLatLng([p.latitud, p.longitud]).setContent(contenido).openOn(this.map);
        }
        static ajustarCirculo(p, contenido) {
            const mapa = document.getElementById('map').getBoundingClientRect();
            const cabecera = document.querySelector('.floating-header')?.getBoundingClientRect();
            const filtros = document.getElementById('filter-dock').getBoundingClientRect();
            const anchoMapa = mapa.width || window.innerWidth || 1280;
            const arriba = (cabecera?.bottom || 100) - (mapa.top || 0) + 12;
            const abajo = (filtros.top || (window.innerHeight || 800) - 150) - (mapa.top || 0) - 16;
            const punto = this.proyectar(p);
            const ventana = contenido.children[2];
            const tamano = parseFloat(ventana.children[0].style.width);
            const ancho = Math.min(tamano, 580, anchoMapa - 64);
            ventana.style.width = ancho + 'px';
            const anchoPopup = ancho + 32;
            const alturaDeseada = Math.min(tamano, 420) + 100;
            const espacioCentrado = 2 * Math.min(punto.y - arriba, abajo - punto.y) - 20;
            let anchor, espacio, flotante = false, offset = [0, 0];
            if (espacioCentrado >= Math.min(alturaDeseada, 340) && punto.x > anchoPopup + 16) {
                anchor = 'right'; espacio = espacioCentrado;
            } else if (espacioCentrado >= Math.min(alturaDeseada, 340) && anchoMapa - punto.x > anchoPopup + 16) {
                anchor = 'left'; espacio = espacioCentrado;
            } else if (espacioCentrado >= alturaDeseada) {
                // Centrar el selector en una pantalla angosta, sin mover el punto.
                anchor = 'right'; espacio = espacioCentrado; flotante = true;
                const centroX = Math.max(anchoPopup / 2 + 12, Math.min(punto.x, anchoMapa - anchoPopup / 2 - 12));
                offset = [centroX + anchoPopup / 2 - punto.x, 0];
            } else {
                const espacioArriba = punto.y - arriba - 16;
                const espacioAbajo = abajo - punto.y - 16;
                anchor = espacioArriba > espacioAbajo ? 'bottom' : 'top';
                espacio = Math.max(espacioArriba, espacioAbajo);
                const centroX = Math.max(anchoPopup / 2 + 12, Math.min(punto.x, anchoMapa - anchoPopup / 2 - 12));
                offset = [centroX - punto.x, 0];
            }
            const alto = Math.max(90, Math.min(420, espacio - 100));
            ventana.style.maxHeight = alto + 'px';
            if (tamano > ancho || tamano > alto) contenido.children[1].textContent += ' Deslizá para ver todos los globitos.';
            return { anchor, offset, className: 'shared-location-popup' + (flotante ? ' shared-location-floating' : '') };
        }
        static cerrarPopup() { this.popup?.remove(); this.popup = null; }
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
        static init() {
            document.getElementById('carousel-btn-prev').addEventListener('click', () => this.cambiarFoto(-1));
            document.getElementById('carousel-btn-next').addEventListener('click', () => this.cambiarFoto(1));
            document.getElementById('card-close-btn').addEventListener('click', () => this.cerrar());
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
            (p.caracteristicas || '').split('\n').map((t) => t.trim()).filter(Boolean).slice(0, 4).forEach((texto) => {
                const etiqueta = document.createElement('span'); etiqueta.className = 'feature-pill';
                etiqueta.textContent = texto; features.appendChild(etiqueta);
            });
            document.getElementById('card-cta-btn').href = p.url_original || '#';
            document.getElementById('card-agency-source').textContent = 'Inmobiliaria: ' + (p.fuente || 'No informada');
            this.actualizarFoto();
            document.getElementById('property-card').hidden = false;
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
            document.getElementById('property-card').hidden = true;
            state.propiedadSeleccionada = null; MapManager.deseleccionarTodos();
        }
    }

    class UI {
        static debounce = null;
        static init() {
            ['alquiler', 'venta'].forEach((operacion) => document.getElementById('btn-op-' + operacion).addEventListener('click', () => {
                if (state.operacion === operacion) return;
                state.operacion = operacion; state.precioMin = ''; state.precioMax = '';
                document.getElementById('precio-min').value = ''; document.getElementById('precio-max').value = '';
                document.getElementById('moneda-precio').textContent = operacion === 'alquiler' ? 'ARS' : 'USD';
                ['alquiler', 'venta'].forEach((op) => this.activar(document.getElementById('btn-op-' + op), op === operacion));
                this.buscar();
            }));
            document.querySelectorAll('[data-filter-tipo]').forEach((btn) => {
                btn.textContent = iconoTipo(btn.dataset.filterTipo) + ' ' + btn.dataset.filterTipo;
                btn.addEventListener('click', () => this.seleccionarTipo(state.tipo === btn.dataset.filterTipo ? null : btn.dataset.filterTipo));
            });
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
                if (e.key !== 'Escape') return;
                document.getElementById('tipos-menu').open = false;
                document.getElementById('mas-filtros').open = false;
                state.seleccionandoPunto = false; this.actualizarPunto(); CardManager.cerrar(); MapManager.cerrarPopup();
            });
            document.addEventListener('click', (e) => {
                ['tipos-menu', 'mas-filtros'].forEach((id) => {
                    const menu = document.getElementById(id); if (!menu.contains(e.target)) menu.open = false;
                });
            });
            if (typeof ResizeObserver !== 'undefined') {
                new ResizeObserver(([entrada]) => {
                    document.documentElement.style.setProperty('--dock-height', entrada.target.getBoundingClientRect().height + 'px');
                }).observe(document.getElementById('filter-dock'));
            }
        }
        static seleccionarTipo(tipo) {
            state.tipo = tipo;
            document.querySelectorAll('[data-filter-tipo]').forEach((btn) => this.activar(btn, btn.dataset.filterTipo === tipo));
            this.activar(document.getElementById('btn-todos-tipos'), tipo === null);
            document.getElementById('tipo-seleccionado').textContent = tipo ? iconoTipo(tipo) + ' ' + tipo : 'Todos los tipos';
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
            document.getElementById('tipo-seleccionado').textContent = 'Todos los tipos';
            document.querySelectorAll('[data-filter-tipo]').forEach((btn) => this.activar(btn, false));
            this.activar(document.getElementById('btn-todos-tipos'), true);
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
        catch (error) { UI.mostrarError(error.message); UI.mostrarCargando(false); }
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar);
    else iniciar();
})();
