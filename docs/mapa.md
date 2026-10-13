# Mapa: interfaz, búsqueda y configuración de MapTiler

Cambios locales del 12 y 13 de octubre de 2026, después del pull `b74a52a`. El usuario activó MapLibre siguiendo la guía anterior y autorizó probar MapTiler para mejorar la cobertura de edificios. La plantilla ya carga MapLibre 6.14.0. No se hizo commit, push ni despliegue de esta etapa.

El 13 de octubre pidió recuperar colores, tipografía y emojis del diseño anterior, mantener el buscador arriba con menor ancho y desplegar en círculo los avisos que comparten un punto. Es la siguiente etapa: primero integrar y probar MapTiler. Esos cambios visuales y la expansión circular todavía no están implementados; las posiciones geográficas reales deberán conservarse al representar la expansión.

## Qué está preparado

- Diseño propio en azul tinta, papel claro y cobre; buscador arriba y controles compactos abajo, adaptados a pantallas pequeñas.
- Menú hamburguesa de tipos generado desde el catálogo vigente existente. Incluye cualquier categoría nueva de la base, sin limitarse a los 13 ejemplos ni inventar tipos. Mantiene selección única y filtro PostgreSQL exacto.
- Marcadores individuales con dibujo SVG según el tipo y precio de la operación seleccionada. Importes cero son válidos; valores desconocidos dicen Consultar. La tarjeta muestra importe completo y moneda original.
- Agrupación visual de etiquetas que se superponen, además de los puntos idénticos del pull. El grupo cuenta avisos y al pulsarlo acerca la cámara; si comparten un punto o se llegó al zoom cercano, abre una lista para seleccionar. Se agrupa por píxeles de pantalla, sin modificar coordenadas, promediarlas ni calcular distancias geográficas.
- Búsqueda libre y comodidades combinadas en `q`, ejecutadas por Elasticsearch. Ante un error se informa y permite reintentar; se eliminó el reemplazo por búsqueda de palabras en el navegador.
- Operación, tipo, dormitorios y precios se consultan en PostgreSQL. El selector de moneda está oculto: el rango de alquiler usa ARS y el de venta USD. Sin rango se conservan publicaciones en otras monedas. Cambiar operación limpia el rango para evitar reutilizar cantidades de otra moneda.
- Selección de un punto con clic o con Usar centro del mapa; distancia predeterminada 1 km, opciones 500 m, 1 km y 2 km. No hay herramienta para dibujar radio ni rectángulos. El backend rechaza radios mayores a 2000 metros, aunque se modifique la URL.
- Por defecto el filtro espacial conserva la política de solo ubicaciones explícitamente exactas. La casilla permite incluir aproximadas y desconocidas, con advertencia. Las ocho mejoras productivas de coordenadas informadas por el usuario conservan su evidencia y clasificación; esta etapa no las modifica.
- Se recorren los enlaces `siguiente` de la API y se conservan orden y filtros: el mapa ya no se limita a los primeros 100 avisos. El contador distingue coincidencias totales y avisos con coordenadas. Solicitudes canceladas no pisan una búsqueda nueva.

MapLibre es el motor activo. Con `MAPTILER_API_KEY` configurada, utiliza Streets v4 de MapTiler; sin clave conserva Bright de OpenFreeMap. Django transmite únicamente esta configuración del mapa mediante `json_script`, escapada para evitar inyección HTML. No se requieren paquetes Python, migraciones, scraping ni reconstrucción de Elasticsearch por este cambio.

## Configurar MapTiler

MapLibre dibuja el mapa y MapTiler aporta sus datos. El estilo es `https://api.maptiler.com/maps/streets-v4/style.json`, conforme a la [integración oficial con MapLibre](https://docs.maptiler.com/maplibre/examples/how-to-use-maplibre/). La biblioteca, los filtros y los datos de propiedades permanecen separados del proveedor cartográfico.

### 1. Crear cuenta y clave local

Crear una cuenta Free en [MapTiler Cloud](https://cloud.maptiler.com/). En API keys crear una clave `Observatorio local` y configurar Allowed HTTP origins con estos dominios, uno por línea y sin protocolo ni puerto:

```text
localhost
127.0.0.1
```

No configurar Allowed User-Agent para esta aplicación web. Guardar y copiar el valor en el `.env` local, sin subirlo al repositorio:

```env
MAPTILER_API_KEY=tu_clave_local
```

Esta es una clave destinada al navegador: puede verse en el HTML y en las solicitudes. Guardarla en `.env` evita versionarla, pero no la oculta al visitante. No es la SECRET_KEY de Django ni una credencial de Supabase/Elasticsearch. La protección se configura por origen en MapTiler. Ver [claves y orígenes permitidos](https://docs.maptiler.com/guides/credentials/api-key/).

### 2. Configurar Render al publicar

Crear otra clave `Observatorio Render`, cuyo único origen permitido sea:

```text
observatorio-grupo7.onrender.com
```

Agregar `MAPTILER_API_KEY` en Environment del servicio Render con esa clave. El `.env` local no se transmite al desplegar. No permitir localhost en la clave productiva. Reiniciar o redesplegar el servicio después de cambiar variables.

### 3. Probar localmente

Reiniciar Django después de guardar `.env`. Desde la raíz del repositorio:

```powershell
.\.venv\Scripts\python.exe manage.py runserver
```

Abrir `http://127.0.0.1:8000/propiedades/mapa/`. Para probar la búsqueda por punto se necesita PostgreSQL/PostGIS; para texto, la configuración de Elasticsearch. SQLite devuelve 503 ante un filtro espacial y no simula distancias. En desarrollo local utilizar `DJANGO_DEBUG=True` y hosts `localhost,127.0.0.1`.

MapLibre empieza centrado en Rafaela con cámara inclinada 45°, rotación -17° y zoom 15,3. Streets v4 ya contiene una capa 3D: se conserva y activa, sin duplicar edificios ni cargar el origen de OpenFreeMap sobre MapTiler. Si un estilo no incluye extrusiones pero sí contornos `building`, el controlador reutiliza ese origen, leyendo `height`/`height_min` (Planet v4) o `render_height`/`render_min_height` (OpenMapTiles). El respaldo de 6 m para MapTiler es ilustrativo cuando falta la altura, no una medición del inmueble. No modifica propiedades ni su precisión geográfica. Se conserva la atribución y se agrega el logo obligatorio del plan Free.

Para comparar cobertura, revisar exactamente el mismo sector y zoom de Rafaela con ambos proveedores. Los contornos y alturas son cartografía de contexto, no una identificación de la propiedad anunciada. Cambiar únicamente inclinación o colores no agrega construcciones ausentes en el origen.

El plan Free es sin tarjeta y para usos personales/no comerciales. Con MapLibre, cada tesela vectorial solicitada cuenta como una solicitud; no se cuentan avisos inmobiliarios. La cuota publicada es 100.000 solicitudes mensuales por cuenta, compartida entre claves. Al agotarla se pausa el servicio hasta el siguiente mes. Consultar Analytics y las [condiciones vigentes](https://www.maptiler.com/cloud/pricing/). No hay fallback automático ante una clave inválida o cuota agotada: quitar la variable y reiniciar permite volver a OpenFreeMap.

### 4. Comprobaciones de la interfaz

1. Fondo cargado, controles de cámara y marcadores con ícono/precio; acercar y seleccionar un grupo.
2. Abrir un aviso y comprobar fotos, enlace original y precisión. Un grupo no implica direcciones exactas ni propiedades duplicadas.
3. Elegir distintos tipos del menú y comprobar selección, Todos los tipos y limpieza.
4. Comparar escribir `con cochera y patio` con seleccionar Cochera/Patio sin texto libre: ambos envían ese mismo `q` y conservan el ranking.
5. Probar punto con 500 m, 1 km y 2 km, quitarlo, cambiar operación y activar aproximadas para comprobar la advertencia. Un radio de 2001 en la API debe devolver 400.
6. Revisar un resultado de más de 100 avisos y distinguir los que carecen de coordenadas. Reintentar un error no debe disparar scraping.
7. En celular comprobar menú, buscador, panel inferior y cierre de tarjeta, sin recortes ni superposición de controles.

La clave local configurada por el usuario respondió HTTP 200 al consultar Streets v4 con origen `http://127.0.0.1:8000` el 13 de octubre. Se verificaron sus capas Building, Building 3D (visible desde zoom 15) y Building number, todas del origen `maptiler_planet_v4`. El servidor local también respondió HTTP 200 al mapa y su controlador actualizado, con la configuración MapTiler presente en el HTML. Estas comprobaciones confirman acceso, esquema e integración local, no una inspección visual del navegador ni cobertura completa de todas las casas de Rafaela. La comprobación visual queda pendiente del usuario.

## Validación de esta etapa

- Etapa MapTiler: 211 pruebas de `propiedades`, 209 aprobadas y dos integraciones PostGIS omitidas con SQLite, incluyendo configuración opcional y escape de la clave en HTML. La suite previa del proyecto completo había descubierto 216 pruebas antes de estas dos nuevas comprobaciones. No se ejecuta contra Supabase productiva.
- `node scripts/test_mapa_coordenadas.cjs`: coordenadas, grupos, lista segura, precisión, iconos/precios, parámetros, punto, páginas, errores y concurrencia; MapLibre con ambos proveedores, clave codificada en URL, logo, alturas v4 y reutilización de edificios sin cargar fuentes duplicadas.
- `node --check` y `collectstatic` comprobados. Los archivos reunidos en staticfiles están ignorados por Git.
- No se consultaron proveedores de geocodificación ni se modificaron publicaciones, fotos, Supabase o índices de Elasticsearch.
- Revisión visual automática pendiente: Chromium de Playwright no estaba instalado y Edge headless no pudo arrancar en el entorno. Las pruebas de objetos simulados no equivalen a una revisión visual o a verificar WebGL/datos 3D reales.

La publicación se mantiene a cargo del usuario: revisar diff, probar, hacer commit/push y esperar el despliegue. El build existente de Render ejecuta collectstatic; estos cambios no crean nuevos servicios ni jobs.
