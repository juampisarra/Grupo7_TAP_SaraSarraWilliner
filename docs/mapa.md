# Mapa: interfaz, búsqueda y configuración de MapTiler

Cambios del 12 y 13 de octubre de 2026, después del pull `b74a52a`. El usuario activó MapLibre y autorizó probar MapTiler para mejorar la cobertura de edificios. La plantilla carga MapLibre 6.14.0 y la integración base está en el commit `ed4cd33` (`integrar maptiler y demas herramientas`). El diseño recuperado y el panel compacto están en `e37d837`. El nuevo selector lateral sigue local; el agente no hizo commit, push ni despliegue.

Después de confirmar MapTiler, el usuario autorizó recuperar colores, tipografía y emojis del diseño anterior y compactar todo el panel superior. Luego pidió reemplazar el círculo de avisos compartidos por burbujas apiladas al costado, sin marco envolvente. Está implementado y revisado en el navegador local; las posiciones geográficas reales se conservan.

## Panel lateral de resultados

El 24 de octubre de 2026 el equipo confirmó avanzar por etapas y comenzar solo con la vista en lista. El botón «Ver lista» abre un panel escondible inspirado en el patrón de Airbnb. En escritorio el panel ocupa aproximadamente la mitad izquierda y MapLibre recalcula el mapa en el espacio restante; hasta 900 px se superpone, y en celular ocupa todo el ancho. Escape o el botón de cierre lo ocultan.

El panel reutiliza las propiedades con coordenadas ya cargadas por la búsqueda del mapa. Por eso siempre representa avisos que tienen marcador y no ejecuta una segunda consulta, no simula coordenadas ni altera la lógica de Elasticsearch/PostgreSQL/PostGIS. Informa la relación entre coincidencias totales y avisos ubicados, usa las fotos existentes y abre la ficha original al pulsar una tarjeta.

La lista puede filtrarse localmente por dirección, tipo, inmobiliaria y otros textos ya cargados. Se ordena por relevancia cuando existe una consulta textual, por actualización o por precio ascendente/descendente; los precios desconocidos se conservan al final. Cambiar los filtros principales o la operación actualiza mapa y lista juntos. La versión de CSS y JavaScript es `20261024-panel-lista`.

Esta etapa no incluye comparación, Gemini ni comentarios y no agrega migraciones, variables, dependencias o servicios. Validación: 27 pruebas Django de consultas/plantilla, regresión Node completa del mapa y `scripts/test_panel_resultados.cjs` para carga, filtro, orden, apertura de ficha y texto no interpretado como HTML. La herramienta de navegador integrado no pudo acceder a la página local y no había otro navegador controlable, por lo que la inspección visual independiente sigue pendiente. No se tocaron datos productivos.

## Qué está preparado

- Blanco translúcido, azul, Plus Jakarta Sans y emojis del diseño anterior. Panel superior centrado, con ancho según contenido y controles más juntos; buscador arriba limitado a 290 px. En pantallas pequeñas usa dos filas. Controles compactos abajo.
- Menú hamburguesa con los tipos que tienen avisos vigentes en la operación seleccionada. Incluye categorías nuevas al recargar, sin limitarse a los 13 ejemplos ni inventar tipos. Mantiene selección única y filtro PostgreSQL exacto.
- Marcadores individuales con emoji según el tipo y precio de la operación seleccionada. Importes cero son válidos; valores desconocidos dicen Consultar. La tarjeta muestra importe completo y moneda original.
- La ficha conserva inmobiliaria, aviso original y precisión. Por pedido del usuario se retiró su enlace fijo «Ubicaciones: fuentes originales / OpenStreetMap»; la atribución del mapa y la mención de OpenStreetMap para puntos geocodificados siguen visibles en sus lugares correspondientes.
- Agrupación de etiquetas superpuestas por píxeles de pantalla. Los puntos idénticos o grupos que ocupan como máximo 12 px en cada eje abren directamente una columna de burbujas con emoji/precio. Los demás acercan automáticamente hasta zoom 18; si todavía se solapan, abren la misma columna. El zoom manual puede seguir acercando y separar puntos distintos. No se modifica, promedia ni redondea ninguna coordenada, ni se calculan distancias geográficas. No se identifica ni fusiona una propiedad por parecido visual, dirección o precio.
- La columna carece de fondo, marco y sombra envolventes; cada burbuja conserva su estilo individual. Abre preferentemente a la izquierda del grupo y cambia a la derecha cerca del borde izquierdo. Se ajusta en píxeles al espacio entre cabecera y filtros, anclada al punto original; los grupos grandes permiten desplazamiento vertical. Cada aviso es un botón accesible por teclado; al elegirlo se abre su ficha y se centra la cámara en sus coordenadas reales. Volver a pulsar el grupo, el botón de cierre, el fondo del mapa, moverlo, cambiar filtros o Escape cierra el selector. Compartir coordenadas no confirma que sea el mismo edificio.
- Búsqueda libre y comodidades combinadas en `q`, ejecutadas por Elasticsearch. Ante un error se informa y permite reintentar; se eliminó el reemplazo por búsqueda de palabras en el navegador.
- Operación, tipo, dormitorios y precios se consultan en PostgreSQL. El selector de moneda está oculto: el rango de alquiler usa ARS y el de venta USD. Sin rango se conservan publicaciones en otras monedas. Cambiar operación limpia el rango para evitar reutilizar cantidades de otra moneda.
- Selección de un punto con clic o con Usar centro del mapa; distancia predeterminada 1 km, opciones 500 m, 1 km y 2 km. No hay herramienta para dibujar radio ni rectángulos. El backend rechaza radios mayores a 2000 metros, aunque se modifique la URL.
- Por defecto el filtro espacial conserva la política de solo ubicaciones explícitamente exactas. La casilla permite incluir aproximadas y desconocidas, con advertencia. Las ocho mejoras productivas de coordenadas informadas por el usuario conservan su evidencia y clasificación; esta etapa no las modifica.
- Se recorren los enlaces `siguiente` de la API y se conservan orden y filtros: el mapa ya no se limita a los primeros 100 avisos. El contador distingue coincidencias totales y avisos con coordenadas. Solicitudes canceladas no pisan una búsqueda nueva.

MapLibre es el motor activo y MapTiler su único proveedor cartográfico. El equipo confirmó retirar el respaldo de OpenFreeMap el 13 de octubre. Se requiere `MAPTILER_API_KEY` para mostrar el mapa: sin clave aparece un mensaje de configuración, las vistas se deshabilitan y termina el indicador de carga. Esta clave no es necesaria para iniciar Django, el listado, la API, health ni los jobs. Django transmite únicamente esta configuración del mapa mediante `json_script`, escapada para evitar inyección HTML. No se requieren paquetes Python, migraciones, scraping ni reconstrucción de Elasticsearch por este cambio. La plantilla usa la versión de recursos `20261013-maptiler` para evitar reutilizar JavaScript anterior.

## Tipos según Alquilar o Comprar

El menú muestra únicamente las categorías con publicaciones vigentes en la operación elegida. Por ejemplo, Nave Industrial no aparece en Alquilar si todos sus avisos son de venta. Los tipos se obtienen de todo el catálogo con una consulta agrupada al cargar la página, independientemente de los primeros 100 resultados, coordenadas, búsqueda textual, precio o punto. No se consulta Elasticsearch para determinar disponibilidad. Los cambios de la base se reflejan al recargar.

Cambiar operación oculta y deshabilita las opciones incompatibles. Conserva el tipo elegido si está disponible en la nueva operación; de lo contrario vuelve a Todos los tipos antes de buscar, sin duplicar solicitudes. Conserva texto, comodidades, dormitorios y punto; el rango de precio se limpia como antes. Limpiar mantiene la operación actual y las opciones correspondientes. Si ninguna categoría está disponible, se indica para alquilar o comprar.

Validación: 27 pruebas Django de consultas/plantilla aprobadas, con disponibilidad real por operación en una base efímera, categorías vacías/inactivas, ausencia de coordenadas y catálogo independiente de paginación y texto. Node verifica visibilidad, selección compatible/incompatible, parámetros, búsqueda única, limpieza y estados vacíos, junto con las regresiones anteriores. Sintaxis y estáticos comprobados. Se actualizó la versión de CSS/JavaScript a `20261013-tipos-operacion` para solicitar archivos nuevos. Revisión visual independiente pendiente por el bloqueo previo del navegador; no se modificaron datos productivos. Cambios locales, sin commit, push ni despliegue.

## Vistas Calles, Oscuro y Satélite

El usuario autorizó terminar el selector el 13 de octubre. Está en la esquina inferior izquierda, por encima del logo y de la atribución, separado del panel de filtros. Su botón oscuro con ícono de capas muestra el nombre de la vista activa. Se cierra al elegir, pulsar Escape o hacer clic afuera. Calles es el mapa predeterminado existente.

Si el selector no aparece tras reiniciar Django, comprobar en el código fuente de la página que exista `estilos-menu`. El usuario confirmó su presencia; las copias locales de plantilla y estáticos también contienen el selector. Se agregó `?v=20261013-vistas` a las direcciones del CSS y JavaScript para que el navegador solicite recursos nuevos en lugar de reutilizar los anteriores. Después de recargar con Ctrl+F5, el usuario confirmó que aparece el botón Calles. Pasaron dos pruebas de plantilla y se verificaron las direcciones versionadas tanto con `DEBUG=True` como con `DEBUG=False`; sigue pendiente la inspección independiente del cambio entre las tres vistas.

Con la clave configurada se usan `streets-v4`, `streets-v4-dark` y `hybrid-v4` de MapTiler. Satélite es imagen aérea con etiquetas de calles. Las tres configuraciones respondieron HTTP 200 y versión 8 con la clave local y origen `http://127.0.0.1:8000`. Las dos primeras contienen Building 3D desde zoom 15; Hybrid no trae capa building. El controlador conserva la definición de la fuente Planet v4 de Calles y la agrega a Satélite con una única extrusión, sin recurrir a OpenFreeMap ni modificar coordenadas. Esta vista solicita también las teselas de edificios de MapTiler. El respaldo de 6 m sigue siendo ilustrativo cuando falta altura.

Cambiar la vista conserva cámara (centro, zoom, inclinación y rotación), avisos, ficha y filtros, y no consulta la API de propiedades ni dispara ingesta. La etiqueta cambia después de validar y aplicar el nuevo estilo. Un fallo HTTP/JSON conserva el fondo anterior; la solicitud tiene cancelación independiente y permite reintentar. Sin clave, el mapa no inicia y las tres vistas quedan deshabilitadas con un mensaje de configuración. La opción satelital utiliza la misma clave, sin nuevos Secrets o paquetes.

Pruebas Node: Calles→Oscuro→Satélite→Calles, nombre y selección, conservación de cámara/filtros/punto/avisos, edificios satelitales sin duplicación, Escape, fallos y clave ausente. Pasaron 25 pruebas Django de consultas/plantilla, sintaxis y estáticos. La revisión visual de este nuevo selector sigue pendiente: la herramienta del navegador rechazó el acceso a la página local. No se intentó eludir el bloqueo. Los cambios están locales; la publicación sigue a cargo del usuario.

Al probar en el navegador, verificar las tres vistas en el mismo sector y zoom (al menos 15), el nombre del botón, los edificios sobre Satélite y su atribución. Comprobar además el menú en celular y seleccionar una propiedad después de cambiar el fondo.

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

MapLibre empieza centrado en Rafaela con cámara inclinada 45°, rotación -17° y zoom 15,3. Streets v4 ya contiene una capa 3D: se conserva y activa sin duplicar edificios. Si un estilo no incluye extrusiones pero sí contornos `building`, el controlador reutiliza ese origen, leyendo `height`/`height_min` de Planet v4. Satélite reutiliza la definición de esta fuente desde Calles. El respaldo de 6 m es ilustrativo cuando falta la altura, no una medición del inmueble. No modifica propiedades ni su precisión geográfica. Se conserva la atribución y se agrega el logo obligatorio del plan Free.

Para evaluar cobertura, revisar distintos sectores de Rafaela con el mismo zoom. Los contornos y alturas son cartografía de contexto, no una identificación de la propiedad anunciada. Cambiar únicamente inclinación o colores no agrega construcciones ausentes en el origen.

El plan Free es sin tarjeta y para usos personales/no comerciales. Con MapLibre, cada tesela vectorial solicitada cuenta como una solicitud; no se cuentan avisos inmobiliarios. La cuota publicada es 100.000 solicitudes mensuales por cuenta, compartida entre claves. Al agotarla se pausa el servicio hasta el siguiente mes. Consultar Analytics y las [condiciones vigentes](https://www.maptiler.com/cloud/pricing/). Ante una clave inválida o cuota agotada, revisar la configuración y el panel de MapTiler; retirar la variable ya no cambia de proveedor.

### 4. Comprobaciones de la interfaz

1. Fondo cargado, controles de cámara y marcadores con ícono/precio; acercar y seleccionar un grupo. Si comparten punto o están casi superpuestos, comprobar la columna sin marco, una burbuja por aviso y cierre al volver a pulsar el grupo. Los grupos más extendidos deben dejar de acercarse automáticamente en zoom 18.
2. Abrir un aviso y comprobar fotos, enlace original y precisión. Un grupo no implica direcciones exactas ni propiedades duplicadas.
3. Alternar Alquilar/Comprar y comprobar que solo se ofrecen los tipos disponibles para esa operación. Un tipo compartido debe conservarse; uno incompatible debe volver a Todos los tipos. Comprobar también desactivación al repetir el clic y limpieza.
4. Comparar escribir `con cochera y patio` con seleccionar Cochera/Patio sin texto libre: ambos envían ese mismo `q` y conservan el ranking.
5. Probar punto con 500 m, 1 km y 2 km, quitarlo, cambiar operación y activar aproximadas para comprobar la advertencia. Un radio de 2001 en la API debe devolver 400.
6. Revisar un resultado de más de 100 avisos y distinguir los que carecen de coordenadas. Reintentar un error no debe disparar scraping.
7. En celular comprobar menú, buscador, panel inferior y cierre de tarjeta, sin recortes ni superposición de controles.

La clave local configurada por el usuario respondió HTTP 200 al consultar Streets v4 con origen `http://127.0.0.1:8000` el 13 de octubre. Se verificaron Building, Building 3D (visible desde zoom 15) y Building number del origen `maptiler_planet_v4`. Mapa/controlador locales respondieron HTTP 200 con la configuración correcta y el usuario confirmó que MapTiler funciona. Posteriormente se inspeccionó en navegador real el mapa con edificios, los grupos y el diseño; no garantiza cobertura completa de todas las casas de Rafaela.

## Validación de esta etapa

- Retirada de OpenFreeMap: 27 pruebas Django de consultas/plantilla aprobadas y regresiones Node de MapLibre/MapTiler, Calles→Oscuro→Satélite→Calles, cámara/filtros/coordenadas, logo y edificios sin duplicación. Sin clave se comprueba el mensaje, mapa no creado, vistas deshabilitadas, carga terminada y ausencia de solicitudes. Sintaxis y estáticos comprobados. Se retiraron las pruebas del respaldo anterior. Validación con SQLite efímero y servicios simulados; revisión visual independiente pendiente por el bloqueo previo del navegador. Sin cambios productivos, commit, push ni despliegue.
- Etapa MapTiler: 211 pruebas de `propiedades`, 209 aprobadas y dos integraciones PostGIS omitidas con SQLite, incluyendo configuración opcional y escape de la clave en HTML. La suite previa del proyecto completo había descubierto 216 pruebas antes de estas dos nuevas comprobaciones. No se ejecuta contra Supabase productiva.
- `node scripts/test_mapa_coordenadas.cjs`: coordenadas, grupos, lista segura, precisión, iconos/precios, parámetros, punto, páginas, errores y concurrencia; MapLibre con ambos proveedores, clave codificada en URL, logo, alturas v4 y reutilización de edificios sin cargar fuentes duplicadas.
- Etapa de diseño anterior: 24 pruebas de consultas/plantilla aprobadas. Para la columna lateral, Node verifica selección/cierre, conservación de coordenadas, texto seguro, un botón por aviso con 2/5/8/18 publicaciones, cambio de lado cerca del borde izquierdo y altura limitada en grupos grandes. Conserva las pruebas de separación de puntos distintos al aumentar zoom.
- Corrección de grupos cercanos: lectura de solo consulta de los avisos de Bolívar 137 (IDs 750/Gaggiotti y 442/Avantix) confirmó pequeñas diferencias en ambas coordenadas. Node reproduce ese par y verifica apertura directa sin zoom, selección de cada fuente con coordenadas propias y preservación de datos. También comprueba que otros grupos llegan como máximo automático a zoom 18 y usan la columna si siguen solapados, evitando la lista blanca anterior.
- `node --check` y `collectstatic` comprobados. Los archivos reunidos en staticfiles están ignorados por Git.
- No se consultaron proveedores de geocodificación ni se modificaron publicaciones, fotos, Supabase o índices de Elasticsearch.
- Revisión real posterior en el navegador de la aplicación: 1280×800 y 390×844, panel superior compacto y buscador de 290 px, 14 tipos con emojis, cinco globitos completos de un grupo real y ficha Departamento/Gaggiotti con fotos y precisión. Un grupo cercano de siete avisos se dividió progresivamente al acercar. Se restauró el tamaño habitual del navegador. Esto reemplaza la limitación previa de Chromium/Edge headless; la revisión actual sí incluye el mapa y sus edificios.
- Revisión del nuevo selector lateral en el tamaño habitual del navegador y 390×844: cinco precios apilados junto al grupo, sin fondo ni marco envolventes, ficha Departamento/Gaggiotti correcta y cierre al repetir el clic. Se comprobó fondo transparente, borde de 0 px y ausencia de sombra del contenedor. El tamaño del navegador se restauró después de la prueba móvil.
- Revisión real de Bolívar 137 después de la corrección: con el filtro estructurado Oficina, el grupo abre sus dos burbujas directamente en la vista inicial, sin acercamientos sucesivos ni lista blanca. Se eligió el aviso de Avantix y se comprobaron dirección, precio, 14 fotos, precisión y enlace original. También se revisó la columna en 390×844 y se restauró el tamaño habitual. Esta comprobación no validó búsqueda textual: el proceso local no tenía configuradas las variables de Elasticsearch.

La publicación se mantiene a cargo del usuario: revisar diff, probar, hacer commit/push y esperar el despliegue. El build existente de Render ejecuta collectstatic; estos cambios no crean nuevos servicios ni jobs.
