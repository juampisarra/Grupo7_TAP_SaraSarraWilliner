/**
 * Observatorio Inmobiliario Rafaela - Controlador de Mapa y Filtros
 * Integración con Elasticsearch y API REST /api/propiedades/
 * Proveedor de Mapas: Esri WorldStreetMap (100% Gratuito, sin marcas de agua ni bloqueos 403)
 * UI/UX: Fluida, Reactiva con micro-interacciones estilo Claude
 */

(() => {
    'use strict';

    // -------------------------------------------------------------------------
    // 1. Estado Global de la Aplicación
    // -------------------------------------------------------------------------
    const state = {
        operacion: 'alquiler',       // 'alquiler' | 'venta'
        tipo: null,                  // Tipo de la base de datos | null (todos)
        caracteristicas: new Set(),  // Set<'Cochera', 'Patio', 'Pileta', 'Balcón', 'Terraza'>
        equipamiento: new Set(),     // Set<'Amoblado', 'Aire Acondicionado'>
        propiedades: [],             // Lista de propiedades devueltas y filtradas
        propiedadSeleccionada: null, // Propiedad activa en la tarjeta
        fotoIndex: 0,                // Índice del carrusel de la propiedad activa
        cargando: false,
        abortController: null,
    };

    // Coordenadas centrales de Rafaela, Santa Fe
    const RAFAELA_COORDS = [-31.253, -61.491];
    const DEFAULT_ZOOM = 14;

    // -------------------------------------------------------------------------
    // 2. Utilidades de Formateo y Normalización
    // -------------------------------------------------------------------------
    function normalizarTexto(texto) {
        return (texto || '')
            .toLowerCase()
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '');
    }

    function formatearPrecio(propiedad, operacion) {
        const datosOp = propiedad[operacion];
        if (!datosOp || !datosOp.disponible || !datosOp.precio) {
            return 'Consultar';
        }
        const numero = parseFloat(datosOp.precio);
        const moneda = datosOp.moneda === 'USD' ? 'USD' : '$';
        const formateado = numero.toLocaleString('es-AR', {
            minimumFractionDigits: 0,
            maximumFractionDigits: 0,
        });
        return `${moneda} ${formateado}`;
    }

    function formatearBadgeMarcador(propiedad, operacion) {
        const datosOp = propiedad[operacion];
        if (!datosOp || !datosOp.disponible || !datosOp.precio) {
            return { texto: 'Consultar', icon: '🏠' };
        }
        const numero = parseFloat(datosOp.precio);
        const moneda = datosOp.moneda === 'USD' ? 'USD' : '$';

        if (numero >= 1000000) {
            const m = (numero / 1000000).toFixed(1).replace('.0', '');
            return { texto: `${moneda} ${m}M`, icon: null };
        }
        if (numero >= 1000) {
            const k = Math.round(numero / 1000);
            return { texto: `${moneda} ${k}k`, icon: null };
        }
        return { texto: `${moneda} ${numero}`, icon: null };
    }

    // -------------------------------------------------------------------------
    // 3. Cliente API (Comunicación con Elasticsearch y Backend Django)
    // -------------------------------------------------------------------------
    class PropertyApiClient {
        static async buscarPropiedades() {
            // Cancelar solicitud previa si el usuario cambia filtros rápidamente
            if (state.abortController) {
                state.abortController.abort();
            }
            state.abortController = new AbortController();

            const params = new URLSearchParams();
            params.set('operacion', state.operacion);
            params.set('por_pagina', '100');

            if (state.tipo) {
                params.set('tipo', state.tipo);
            }

            const terminosBusqueda = [
                ...Array.from(state.caracteristicas),
                ...Array.from(state.equipamiento),
            ];

            if (terminosBusqueda.length > 0) {
                // Al enviar 'q', el backend ejecuta la búsqueda BM25 en Elasticsearch
                params.set('q', terminosBusqueda.join(' '));
            }

            const url = `/api/propiedades/?${params.toString()}`;
            UI.mostrarCargando(true);

            try {
                let resultados = [];
                const response = await fetch(url, {
                    method: 'GET',
                    headers: { 'Accept': 'application/json' },
                    signal: state.abortController.signal,
                });

                if (response.ok) {
                    // Respuesta exitosa (Elasticsearch en Render o consulta sin 'q')
                    const data = await response.json();
                    resultados = data.resultados || [];
                } else if (response.status === 503 && terminosBusqueda.length > 0) {
                    // Manejo robusto para desarrollo local: si Elasticsearch no tiene credenciales en el .env local,
                    // consultamos la base estructurada sin 'q' y aplicamos el filtro por comodidades sobre el corpus recibido.
                    const fallbackParams = new URLSearchParams();
                    fallbackParams.set('operacion', state.operacion);
                    fallbackParams.set('por_pagina', '100');
                    if (state.tipo) {
                        fallbackParams.set('tipo', state.tipo);
                    }

                    const fallbackResp = await fetch(`/api/propiedades/?${fallbackParams.toString()}`, {
                        method: 'GET',
                        headers: { 'Accept': 'application/json' },
                        signal: state.abortController.signal,
                    });

                    if (fallbackResp.ok) {
                        const fallbackData = await fallbackResp.json();
                        const todas = fallbackData.resultados || [];

                        // Filtrar por cada término seleccionado (Cochera, Balcón, etc.)
                        resultados = todas.filter((prop) => {
                            const corpus = normalizarTexto(
                                `${prop.caracteristicas || ''} ${prop.descripcion || ''} ${prop.titulo || ''}`
                            );
                            return terminosBusqueda.every((termino) =>
                                corpus.includes(normalizarTexto(termino))
                            );
                        });
                    } else {
                        throw new Error(`Error en fallback: ${fallbackResp.status}`);
                    }
                } else {
                    throw new Error(`Error en el servidor: ${response.status}`);
                }

                // Filtrar solo las que tienen coordenadas válidas
                state.propiedades = resultados.filter(
                    (p) => p.latitud !== null && p.longitud !== null
                );
                state.totalResultados = state.propiedades.length;

                UI.actualizarContador(state.totalResultados);
                MapManager.renderizarMarcadores(state.propiedades);
                UI.mostrarMensajeVacio(state.propiedades.length === 0);
            } catch (error) {
                if (error.name === 'AbortError') return; // Cancelación normal
                console.error('Error al consultar propiedades:', error);
            } finally {
                UI.mostrarCargando(false);
            }
        }
    }

    // -------------------------------------------------------------------------
    // 4. Gestor del Mapa Interactivo (Esri WorldStreetMap)
    // -------------------------------------------------------------------------
    class MapManager {
        static map = null;
        static markersLayer = null;
        static markerMap = new Map(); // id -> L.Marker

        static init() {
            // Inicializar mapa centrado en Rafaela
            this.map = L.map('map', {
                center: RAFAELA_COORDS,
                zoom: DEFAULT_ZOOM,
                zoomControl: false,
            });

            // Control de Zoom abajo a la derecha
            L.control.zoom({ position: 'bottomright' }).addTo(this.map);

            // Capa Esri WorldStreetMap: 100% gratuita, sin marcas de agua, sin bloqueos 403 y con calles nítidas
            L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}', {
                attribution: 'Tiles &copy; Esri &mdash; OpenStreetMap contributors',
                maxZoom: 19,
            }).addTo(this.map);

            this.markersLayer = L.featureGroup().addTo(this.map);

            // Cerrar tarjeta al hacer clic en el mapa libre
            this.map.on('click', (e) => {
                if (e.originalEvent.target.id === 'map') {
                    CardManager.cerrar();
                }
            });
        }

        static renderizarMarcadores(propiedades) {
            this.markersLayer.clearLayers();
            this.markerMap.clear();

            // Un grupo conserva el punto publicado: no inventar pines alrededor.
            const grupos = new Map();
            propiedades.forEach((propiedad) => {
                const clave = `${propiedad.latitud},${propiedad.longitud}`;
                if (!grupos.has(clave)) grupos.set(clave, []);
                grupos.get(clave).push(propiedad);
            });

            [...grupos.values()].forEach((grupo, index) => {
                const propiedad = grupo[0];
                const lat = propiedad.latitud;
                const lng = propiedad.longitud;

                const badge = formatearBadgeMarcador(propiedad, state.operacion);
                const contenidoHtml = grupo.length > 1
                    ? `<span class="marker-text">${grupo.length} avisos</span>`
                    : badge.icon
                    ? `<span class="marker-icon">${badge.icon}</span> <span class="marker-text">${badge.texto}</span>`
                    : `<span class="marker-text">${badge.texto}</span>`;

                const delay = Math.min(index * 20, 400);

                const customIcon = L.divIcon({
                    className: 'custom-leaflet-marker-wrapper',
                    html: `
                        <div class="property-marker" data-id="${propiedad.id}" style="animation-delay: ${delay}ms;">
                            <div class="marker-inner">
                                ${contenidoHtml}
                            </div>
                            <div class="marker-pin-tip"></div>
                        </div>
                    `,
                    iconSize: [70, 32],
                    iconAnchor: [35, 32],
                });

                const marker = L.marker([lat, lng], {
                    icon: customIcon,
                    riseOnHover: true,
                });

                marker.on('click', () => {
                    if (grupo.length > 1) {
                        const lista = document.createElement('div');
                        const aviso = document.createElement('p');
                        aviso.textContent = 'Estos avisos comparten un punto. Consultá la precisión de cada ubicación.';
                        lista.appendChild(aviso);
                        grupo.forEach((p) => {
                            const boton = document.createElement('button');
                            boton.type = 'button';
                            boton.className = 'shared-location-option';
                            boton.textContent = `${p.direccion || p.titulo || 'Propiedad'} · ${formatearPrecio(p, state.operacion)} · ${p.fuente}`;
                            boton.addEventListener('click', () => {
                                this.map.closePopup();
                                this.seleccionarMarcador(p.id);
                                CardManager.mostrar(p);
                            });
                            lista.appendChild(boton);
                        });
                        marker.bindPopup(lista, { maxHeight: 250 }).openPopup();
                    } else {
                        this.seleccionarMarcador(propiedad.id);
                        CardManager.mostrar(propiedad);
                    }
                });

                this.markersLayer.addLayer(marker);
                grupo.forEach((p) => this.markerMap.set(p.id, marker));
            });

            // Mantener el mapa centrado y enfocado en Rafaela (evita alejarse por propiedades lejanas como San Vicente o Lehmann)
            if (!state.propiedadSeleccionada) {
                this.map.setView(RAFAELA_COORDS, DEFAULT_ZOOM, { animate: true });
            }
        }

        static seleccionarMarcador(id) {
            document.querySelectorAll('.property-marker').forEach((el) => {
                el.classList.remove('active');
            });

            const marker = this.markerMap.get(id);
            if (marker) {
                const markerEl = marker.getElement()?.querySelector('.property-marker');
                if (markerEl) markerEl.classList.add('active');

                const latLng = marker.getLatLng();
                this.map.panTo(latLng, { animate: true, duration: 0.5 });
            }
        }

        static deseleccionarTodos() {
            document.querySelectorAll('.property-marker').forEach((el) => {
                el.classList.remove('active');
            });
        }
    }

    // -------------------------------------------------------------------------
    // 5. Gestor de Tarjeta Flotante y Carrusel de Fotos (Popup Glassmorphic)
    // -------------------------------------------------------------------------
    class CardManager {
        static card = document.getElementById('property-card');
        static imgEl = document.getElementById('card-image');
        static placeholderEl = document.getElementById('card-image-placeholder');
        static counterEl = document.getElementById('card-carousel-counter');
        static btnPrev = document.getElementById('carousel-btn-prev');
        static btnNext = document.getElementById('carousel-btn-next');

        static init() {
            this.btnPrev.addEventListener('click', (e) => {
                e.stopPropagation();
                this.anteriorFoto();
            });

            this.btnNext.addEventListener('click', (e) => {
                e.stopPropagation();
                this.siguienteFoto();
            });

            document.getElementById('card-close-btn').addEventListener('click', () => {
                this.cerrar();
            });
        }

        static mostrar(propiedad) {
            state.propiedadSeleccionada = propiedad;
            state.fotoIndex = 0;

            document.getElementById('card-price').textContent = formatearPrecio(propiedad, state.operacion);
            
            const tagOp = document.getElementById('card-operation-tag');
            tagOp.textContent = state.operacion === 'venta' ? 'En Venta' : 'En Alquiler';
            tagOp.className = `card-operation-tag ${state.operacion}`;

            document.getElementById('card-title').textContent = propiedad.titulo || `${propiedad.tipo || 'Propiedad'} en ${state.operacion}`;
            
            const direccionTxt = propiedad.direccion 
                ? `${propiedad.direccion}${propiedad.zona ? ' · ' + propiedad.zona : ''}`
                : (propiedad.zona || 'Rafaela, Santa Fe');
            document.getElementById('card-location').textContent = `📍 ${direccionTxt}`;
            const precisionEl = document.getElementById('card-location-precision');
            const info = propiedad.ubicacion_info;
            precisionEl.textContent = info?.precision === 'geocodificada_direccion'
                ? 'Ubicación estimada por dirección; no garantiza la puerta exacta. © OpenStreetMap contributors'
                : propiedad.ubicacion_aproximada === false
                    ? 'Punto tratado como exacto según la política de la fuente.'
                    : propiedad.ubicacion_aproximada === true
                        ? 'Ubicación aproximada: el pin representa el centro del área publicada.'
                        : 'Precisión de ubicación desconocida: el pin puede ser una referencia de zona.';

            // Métricas (Dormitorios, Ambientes, Baños)
            const specsEl = document.getElementById('card-specs');
            specsEl.innerHTML = '';

            if (propiedad.dormitorios !== null && propiedad.dormitorios !== undefined) {
                specsEl.innerHTML += `<div class="spec-item">🛏️ <strong>${propiedad.dormitorios}</strong> dorm.</div>`;
            }
            if (propiedad.ambientes !== null && propiedad.ambientes !== undefined) {
                specsEl.innerHTML += `<div class="spec-item">📐 <strong>${propiedad.ambientes}</strong> amb.</div>`;
            }
            if (propiedad.banos !== null && propiedad.banos !== undefined) {
                specsEl.innerHTML += `<div class="spec-item">🚿 <strong>${propiedad.banos}</strong> baño${propiedad.banos > 1 ? 's' : ''}</div>`;
            }

            // Etiquetas de Comodidades
            const featuresEl = document.getElementById('card-features');
            featuresEl.innerHTML = '';
            if (propiedad.caracteristicas) {
                const tags = propiedad.caracteristicas
                    .split('\n')
                    .map((t) => t.trim())
                    .filter(Boolean)
                    .slice(0, 4);
                tags.forEach((tag) => {
                    featuresEl.innerHTML += `<span class="feature-pill">${tag}</span>`;
                });
            }

            // Enlace original
            const ctaBtn = document.getElementById('card-cta-btn');
            ctaBtn.href = propiedad.url_original || '#';

            document.getElementById('card-agency-source').textContent = `Inmobiliaria: ${propiedad.fuente || 'Web'}`;

            this.actualizarFoto();
            this.card.hidden = false;
        }

        static actualizarFoto() {
            const fotos = state.propiedadSeleccionada?.fotos || [];

            if (fotos.length > 0) {
                this.imgEl.hidden = false;
                this.placeholderEl.hidden = true;
                this.imgEl.src = fotos[state.fotoIndex];

                this.imgEl.onerror = () => {
                    this.imgEl.hidden = true;
                    this.placeholderEl.hidden = false;
                };

                this.counterEl.hidden = false;
                this.counterEl.textContent = `${state.fotoIndex + 1} / ${fotos.length}`;
                this.btnPrev.hidden = fotos.length <= 1;
                this.btnNext.hidden = fotos.length <= 1;
            } else {
                this.imgEl.hidden = true;
                this.placeholderEl.hidden = false;
                this.counterEl.hidden = true;
                this.btnPrev.hidden = true;
                this.btnNext.hidden = true;
            }
        }

        static anteriorFoto() {
            const fotos = state.propiedadSeleccionada?.fotos || [];
            if (fotos.length <= 1) return;
            state.fotoIndex = (state.fotoIndex - 1 + fotos.length) % fotos.length;
            this.actualizarFoto();
        }

        static siguienteFoto() {
            const fotos = state.propiedadSeleccionada?.fotos || [];
            if (fotos.length <= 1) return;
            state.fotoIndex = (state.fotoIndex + 1) % fotos.length;
            this.actualizarFoto();
        }

        static cerrar() {
            this.card.hidden = true;
            state.propiedadSeleccionada = null;
            MapManager.deseleccionarTodos();
        }
    }

    // -------------------------------------------------------------------------
    // 6. Controlador de Panel de Filtros y Reactividad
    // -------------------------------------------------------------------------
    class UI {
        static init() {
            // 1. Selector Segmentado Alquilar / Comprar
            const btnAlquiler = document.getElementById('btn-op-alquiler');
            const btnVenta = document.getElementById('btn-op-venta');

            btnAlquiler.addEventListener('click', () => {
                if (state.operacion === 'alquiler') return;
                state.operacion = 'alquiler';
                btnAlquiler.classList.add('active');
                btnVenta.classList.remove('active');
                CardManager.cerrar();
                PropertyApiClient.buscarPropiedades();
            });

            btnVenta.addEventListener('click', () => {
                if (state.operacion === 'venta') return;
                state.operacion = 'venta';
                btnVenta.classList.add('active');
                btnAlquiler.classList.remove('active');
                CardManager.cerrar();
                PropertyApiClient.buscarPropiedades();
            });

            // 2. Filtro Tipo de Propiedad (Selección Única con Toggle)
            document.querySelectorAll('[data-filter-tipo]').forEach((btn) => {
                btn.addEventListener('click', () => {
                    const tipo = btn.getAttribute('data-filter-tipo');
                    if (state.tipo === tipo) {
                        state.tipo = null;
                        btn.classList.remove('active');
                    } else {
                        document.querySelectorAll('[data-filter-tipo]').forEach((b) => b.classList.remove('active'));
                        state.tipo = tipo;
                        btn.classList.add('active');
                    }
                    CardManager.cerrar();
                    PropertyApiClient.buscarPropiedades();
                });
            });

            // 3. Filtro Características (Multi-Select Reactivo)
            document.querySelectorAll('[data-filter-caracteristica]').forEach((btn) => {
                btn.addEventListener('click', () => {
                    const valor = btn.getAttribute('data-filter-caracteristica');
                    if (state.caracteristicas.has(valor)) {
                        state.caracteristicas.delete(valor);
                        btn.classList.remove('active');
                    } else {
                        state.caracteristicas.add(valor);
                        btn.classList.add('active');
                    }
                    CardManager.cerrar();
                    PropertyApiClient.buscarPropiedades();
                });
            });

            // 4. Filtro Equipamiento (Multi-Select Reactivo)
            document.querySelectorAll('[data-filter-equipamiento]').forEach((btn) => {
                btn.addEventListener('click', () => {
                    const valor = btn.getAttribute('data-filter-equipamiento');
                    if (state.equipamiento.has(valor)) {
                        state.equipamiento.delete(valor);
                        btn.classList.remove('active');
                    } else {
                        state.equipamiento.add(valor);
                        btn.classList.add('active');
                    }
                    CardManager.cerrar();
                    PropertyApiClient.buscarPropiedades();
                });
            });

            // 5. Botón Limpiar Filtros
            const btnLimpiar = document.getElementById('btn-limpiar-filtros');
            btnLimpiar.addEventListener('click', () => {
                this.limpiarFiltros();
            });

            document.getElementById('btn-reset-empty')?.addEventListener('click', () => {
                this.limpiarFiltros();
            });
        }

        static limpiarFiltros() {
            state.tipo = null;
            state.caracteristicas.clear();
            state.equipamiento.clear();

            document.querySelectorAll('.filter-chip').forEach((btn) => {
                if (!btn.classList.contains('clear-btn')) {
                    btn.classList.remove('active');
                }
            });

            CardManager.cerrar();
            PropertyApiClient.buscarPropiedades();
        }

        static actualizarContador(total) {
            const countEl = document.getElementById('results-count');
            if (countEl) {
                countEl.textContent = `${total} inmueble${total === 1 ? '' : 's'}`;
            }
        }

        static mostrarCargando(cargando) {
            state.cargando = cargando;
            const toast = document.getElementById('loading-toast');
            if (toast) toast.hidden = !cargando;
        }

        static mostrarMensajeVacio(mostrar) {
            const banner = document.getElementById('empty-results-banner');
            if (banner) banner.hidden = !mostrar;
        }
    }

    // -------------------------------------------------------------------------
    // 7. Inicialización al Cargar el DOM
    // -------------------------------------------------------------------------
    document.addEventListener('DOMContentLoaded', () => {
        MapManager.init();
        CardManager.init();
        UI.init();

        // Carga inicial automática
        PropertyApiClient.buscarPropiedades();
    });
})();
