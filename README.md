# Grupo7_TAP_SaraSarraWilliner

**Actualización del 12 de octubre:** mapa y API con fotos públicos comprobados; Supabase tiene `0012`. Se agregó localmente diagnóstico y enriquecimiento conservador de coordenadas, conservación del original y agrupación de puntos compartidos. Esta última etapa requiere **0013** y sigue pendiente de publicar/aplicar. Ver [guía de coordenadas](docs/geocodificacion.md). Las notas anteriores de preparación conservan su contexto histórico.

Fotos agregadas localmente el 12 de octubre: URLs ordenadas para las tres fuentes, portada, API y muestra mínima en HTML. **Requiere migración `0012` y luego ingesta para cargar fotos**; todavía no está publicado. No agrega servicios, Secrets ni almacenamiento de archivos. Ver [fotos y publicación](docs/fotos.md).

Etapa anterior del 12 de octubre: filtros de tipo/dormitorios/precio por operación y moneda, paginación y `/api/propiedades/` implementados y probados localmente; pendientes de publicar. HTML y JSON comparten relevancia, geografía y totales. Ver [contrato y ejemplos de la API](docs/api_propiedades.md). No requiere migraciones, variables nuevas ni reconstrucción del índice.

Actualización del 12 de octubre: `/health/`, PostGIS, Elasticsearch y el formulario textual mínimo están desplegados. **Brega, Avantix y Gaggiotti están publicadas y verificadas**, junto con la tolerancia a fallos por fuente. El workflow manual terminó correctamente: Supabase tiene 754 publicaciones y Elasticsearch contiene los mismos documentos. Se comprobaron listados, relevancia y filtros geográficos públicos. Ver [Gaggiotti y resultados de validación](docs/gaggiotti.md) y [operación y recuperación de ingesta](docs/ingesta.md). El frontend definitivo y el mapa siguen pendientes. Ver [despliegue](docs/despliegue.md), [PostGIS](docs/postgis.md) y [Elasticsearch](docs/elasticsearch.md).

**Para el compañero que administra Render:** la [guía de continuidad](docs/continuidad.md) conserva la configuración, recuperación y pendientes. El usuario autorizó al agente a publicar Gaggiotti y la tolerancia por fuente; `.env` no se sube ni actualiza Render automáticamente y no se necesitaron variables nuevas.

Trabajo práctico de TAP del Grupo 7 (Sara, Sarra y Williner): un Observatorio Inmobiliario orientado inicialmente a propiedades de Rafaela. Centraliza publicaciones de distintas inmobiliarias para buscar, filtrar y comparar opciones desde una única aplicación, conservando la fuente y el enlace al aviso original.

## Objetivo y prioridades

Las features principales acordadas son:

1. Un job de ingesta mediante scraping para aproximadamente tres inmobiliarias, con adaptadores por fuente y un modelo normalizado común.
2. Búsqueda de texto completo con Elasticsearch y ranking por relevancia, trabajando con índices invertidos, términos, documentos, posting lists, stopwords y BM25.
3. Búsqueda web que combine texto con filtros estructurados y geográficos, usando exclusivamente PostGIS para la lógica geográfica.

El backend implementa scrapers, normalización, persistencia, ingesta, indexación y consultas. El equipo incorporó el frontend y mapa en `/propiedades/mapa/`; el listado HTML anterior sigue disponible para pruebas. La etapa actual mejora el diagnóstico y la procedencia de las coordenadas.

## Stack acordado

| Componente | Función |
| --- | --- |
| Python y Django | Backend y jobs de ingesta; Django ya está presente en el repositorio. |
| Supabase / PostgreSQL | Base principal y fuente de verdad: propiedades completas y filtros estructurados. |
| PostGIS | Extensión de PostgreSQL para coordenadas y toda consulta geográfica: radio, distancia, bounding boxes y polígonos. |
| Elasticsearch / Elastic Cloud | Índice de texto completo y ranking por relevancia alojado en Elastic Cloud; reconstruible desde PostgreSQL. |
| Render | Django desplegado en el plan Free y conectado a Supabase y Elastic Cloud. |
| GitHub Actions | Ingesta y reconstrucción del índice los lunes a las 00:00 de Argentina, con ejecución manual disponible. |
| Frontend | Django Templates, JavaScript y Leaflet en `/propiedades/mapa/`, consumiendo la API de Django. |

PostGIS forma parte de PostgreSQL. Elasticsearch es un índice separado que no reemplaza la base principal y no realizará filtros geográficos. SQLite sigue disponible para desarrollo local. La conexión PostgreSQL y las migraciones hasta `0011` están verificadas en Supabase. No se realizó un traslado automático de datos locales.

La entrega requiere un sitio desplegado. El entorno actual es Django en Render, PostgreSQL/PostGIS en Supabase y Elasticsearch en Elastic Cloud. El equipo confirmó el listado público, la búsqueda por relevancia y los filtros geográficos. GitHub Actions ejecuta el comando general y reconstruye Elasticsearch después de la ingesta; los comandos locales se conservan para desarrollo y recuperación. Elastic Cloud usa una prueba de 14 días y todavía hay que registrar su vencimiento exacto y resolver la continuidad posterior. Ver [la configuración del despliegue y el próximo paso](docs/despliegue.md).

Actions ejecuta el comando de ingesta con credenciales en GitHub Secrets, guarda los datos en Supabase y reconstruye Elasticsearch. Los runners estándar son gratuitos en repositorios públicos. Para repositorios privados, GitHub Free incluye 2.000 minutos por mes compartidos entre los workflows y repositorios privados de la cuenta propietaria, no por integrante. Este repositorio se comprobó público el 9 de octubre. Ver [condiciones oficiales](https://docs.github.com/en/billing/concepts/product-billing/github-actions). El horario programado puede sufrir demoras.

El equipo creó un job en cron-job.org para consultar `/health/` y reducir el reposo por inactividad. Falta comprobar una ejecución programada exitosa en su historial y el intervalo guardado; se propuso GET cada diez minutos. Los pings no ejecutan ingesta ni indexación y no garantizan disponibilidad continua. No hace falta contratar un Render Cron Job para esta arquitectura. Ver [comprobación del ping](docs/continuidad.md#5-comprobar-el-ping).

## Flujo previsto

```text
Scrapers/adaptadores por inmobiliaria
               ↓
       Normalización común
               ↓
Supabase / PostgreSQL con PostGIS
               ↓
   Indexación en Elasticsearch

Frontend + mapa → Backend Python
                           ├─ Elasticsearch: texto y ranking
                           └─ PostgreSQL + PostGIS: datos y filtros
                        → Resultados al frontend
```

El flujo guarda primero en PostgreSQL y después reconstruye Elasticsearch. La ingesta crea o actualiza publicaciones sin duplicarlas por fuente e identificador. La nueva tolerancia por fuente continúa con las demás ante un fallo y devuelve un resumen final: salida `0` si todas terminan, `3` ante éxito parcial y `1` si todas fallan. El workflow reconstruye con `0` o `3`, conservando el estado fallido del job ante fallo parcial; omite el índice ante fallo total. En una ejecución manual ambos comandos siguen siendo pasos separados. La recuperación incremental sigue pendiente. Ver [detalles y límites](docs/ingesta.md).

Las búsquedas consultan la información guardada y no ejecutan scraping. El backend coordina Elasticsearch para texto/relevancia, PostgreSQL para filtros estructurados y PostGIS para ubicación; el frontend no accede directamente a esos servicios.

Los filtros previstos incluyen tipo, venta/alquiler, precio mínimo/máximo con moneda y ubicación. Una propiedad puede tener venta y alquiler con precios distintos. El modelo común también contemplará, según disponibilidad, dirección, ciudad, barrio, dormitorios, ambientes, superficie y unidad, título, descripción, características, imágenes, URL y coordenadas. Los datos faltantes se representarán sin inventarlos.

La búsqueda con mapa permitirá indicar un punto y radio, o seleccionar/dibujar un área. PostGIS ya resuelve radio con `ST_DWithin` y rectángulos con `ST_Covers`, en WGS84 y con índices GiST. La consulta por polígonos arbitrarios sigue pendiente; ver [límites y precisión](docs/postgis.md). Hay geocodificación experimental; su validación y la extracción de localidad quedan pendientes.

## Qué existe actualmente

- Proyecto Django `config/` y aplicación `propiedades/`, con SQLite local y configuración PostgreSQL/Supabase mediante `.env` y psycopg.
- Despliegue básico de Django en Render Free: Gunicorn, WhiteNoise, clave secreta por entorno, `DEBUG=False`, dominio permitido automáticamente y configuración HTTPS del proxy. Preparación en el commit `5f61bf9`; listado público comprobado por el equipo.
- Modelo `Propiedad` con procedencia, dirección, tipo, dormitorios, venta/alquiler, precios y monedas por operación, URL original y fecha de actualización; unicidad por `(fuente, identificador_fuente)`.
- Título, descripción, características como texto, ciudad/provincia/zona, ambientes y baños opcionales, agregados en la migración `0008`. Las amenidades no necesitan una columna individual.
- Scrapers Brega y Avantix con Requests y Beautiful Soup, paginación y normalización común Tokko.
- Adaptador Gaggiotti para su servicio JSON público: listados paginados con fichas completas, normalización al modelo común y precios separados por operación, respetando los precios ocultos. Coordenadas con precisión desconocida: los filtros espaciales requieren `incluir_aproximadas=1`. Ver [contrato y validación](docs/gaggiotti.md).
- Flujo común en `propiedades/ingesta.py`, contrato `PublicacionNormalizada` y tres adaptadores registrados. `importar_propiedades` procesa todas las fuentes; también acepta `brega`, `avantix` o `gaggiotti`. `importar_brega` es un alias compatible.
- Brega consulta la ficha completa en cada ingesta y obtiene texto, características y cantidades. Los errores de ficha conservan los detalles guardados. El rótulo ambiguo `Ubicación` se guarda como zona, sin asumir ciudad.
- Brega extrae coordenadas de los círculos publicados en el mapa de la ficha y conserva `ubicacion_aproximada` y `radio_ubicacion_m` (migración `0009`). No requiere ciudad para guardar coordenadas de la fuente. Esas posiciones representan áreas aproximadas, no direcciones exactas.
- Avantix extrae el punto del iframe de Google Maps, lo valida y lo conserva con `ubicacion_aproximada=False` y radio nulo. Esta clasificación como exacta es una decisión del equipo; la fuente no declara expresamente su precisión.
- La geocodificación experimental con geopy/Nominatim se usa cuando faltan coordenadas de fuente y hay ciudad explícita; no asume Rafaela. Los cambios de ubicación invalidan coordenadas anteriores salvo que la fuente aporte un par nuevo.
- Enriquecimiento inverso opcional con `importar_propiedades brega --completar-ubicacion`: completa ciudad/provincia faltantes con procedencia por campo y caché persistente (migración `0010`), conserva coordenadas/precisión y tolera fallos del proveedor. Los nombres inferidos se invalidan si cambia el punto; los explícitos tienen prioridad. Ver [la guía](docs/base_de_datos.md).
- Listado `/propiedades/` con filtro de venta/alquiler, búsqueda textual mínima por relevancia y enlace al aviso original; muestra alquileres por defecto.

La conexión y migraciones hasta `0012` están verificadas en Supabase. La revisión del 12 de octubre registra 754 publicaciones históricas y 752 vigentes: 171 Brega, 275 Avantix y 306 Gaggiotti. La API pública paginada con fotos y el mapa responden correctamente. La búsqueda por relevancia y PostGIS tienen sus comprobaciones previas documentadas. El enriquecimiento de coordenadas y la agrupación del mapa de esta etapa siguen locales, con `0013` pendiente. Suite actual: 212 pruebas, 210 aprobadas y dos integraciones PostGIS omitidas con SQLite. Ver [AGENTS.md](AGENTS.md) para ejecutarlas sin utilizar Supabase.

## Ejecutar el prototipo local

Desde la raíz del repositorio, con Python instalado, en PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Antes de ejecutar Django, generar una clave propia:

```powershell
.\.venv\Scripts\python.exe -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Copiar el resultado en `DJANGO_SECRET_KEY` dentro de `.env` y conservar `DJANGO_DEBUG=True` y `DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1` para desarrollo. Guardar `.env` como UTF-8 sin BOM y no subirlo a Git. Con `DB_ENGINE=sqlite` se utiliza SQLite; para conectar Supabase seguir [la guía de bases de datos](docs/base_de_datos.md). Cada integrante configura su propio entorno.

Aplicar las migraciones:

```powershell
.\.venv\Scripts\python.exe manage.py migrate
```

La ingesta consulta los sitios externos y puede tardar por la paginación, las fichas y las pausas entre solicitudes. Se puede ejecutar una fuente específica:

```powershell
.\.venv\Scripts\python.exe manage.py importar_propiedades brega
.\.venv\Scripts\python.exe manage.py importar_propiedades avantix
.\.venv\Scripts\python.exe manage.py importar_propiedades gaggiotti
```

Sin argumento procesa las tres fuentes registradas:

```powershell
.\.venv\Scripts\python.exe manage.py importar_propiedades
```

Para iniciar el servidor de desarrollo:

```powershell
.\.venv\Scripts\python.exe manage.py runserver
```

Abrir [el listado local](http://127.0.0.1:8000/propiedades/). El listado muestra los datos de la base configurada; sin datos previos estará vacío. Usar Supabase permite consultar las publicaciones ya cargadas sin repetir la ingesta. El alias `importar_brega` sigue disponible. La ejecución local es para desarrollo y pruebas; Django, PostGIS, Elasticsearch y las tres fuentes ya están disponibles en el sitio desplegado.

## Próximos pasos

1. Tolerancia por fuente completada y publicada; aislamiento probado localmente y workflow exitoso en producción.
2. Gaggiotti completada y publicada; carga, índice y resultados públicos verificados el 12 de octubre.
3. Filtros de tipo, dormitorios y precio por operación/moneda implementados y probados localmente; publicar y comprobar.
4. Paginación y API JSON implementadas y probadas localmente; publicar y comprobar. Ver [API de propiedades](docs/api_propiedades.md).
5. Desarrollar el frontend y el mapa después del backend.

Bajas por operación, reconstrucción independiente en Actions y limpieza de índices con vista previa están implementadas localmente, pendientes de publicación y comprobación productiva. Ver [mantenimiento](docs/mantenimiento.md). Siguen pendientes comprobar el historial e intervalo del ping, registrar el vencimiento exacto y continuidad de Elastic Cloud, validar la geocodificación experimental e implementar indexación/recuperación incremental. La detección de una misma propiedad publicada por inmobiliarias diferentes tiene un alcance distinto de evitar duplicados en cargas repetidas y aún debe definirse.

## Contexto para colaborar

Leer [AGENTS.md](AGENTS.md) antes de proponer cambios. Contiene las decisiones confirmadas, el estado actual, los hallazgos de las fuentes y los criterios para avanzar de forma incremental sin sobrearquitecturar. La compatibilidad Tokko de Brega y Avantix y el adaptador compartido deben verificarse antes de asumir reutilización.
