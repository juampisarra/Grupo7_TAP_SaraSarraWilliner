# Grupo7_TAP_SaraSarraWilliner

Actualización del 9 de octubre: `/health/`, la corrección de valores cero y los ajustes de seguridad están listos para desplegar. PostGIS ya está instalado en Supabase con la migración `0011`; los filtros por radio y rectángulo están implementados en el backend local. Ver [estado de despliegue](docs/despliegue.md) y [uso de PostGIS](docs/postgis.md). Elasticsearch, GitHub Actions y el mapa siguen pendientes.

Trabajo práctico de TAP del Grupo 7 (Sara, Sarra y Williner): un Observatorio Inmobiliario orientado inicialmente a propiedades de Rafaela. Centraliza publicaciones de distintas inmobiliarias para buscar, filtrar y comparar opciones desde una única aplicación, conservando la fuente y el enlace al aviso original.

## Objetivo y prioridades

Las features principales acordadas son:

1. Un job de ingesta mediante scraping para aproximadamente tres inmobiliarias, con adaptadores por fuente y un modelo normalizado común.
2. Búsqueda de texto completo con Elasticsearch y ranking por relevancia, trabajando con índices invertidos, términos, documentos, posting lists, stopwords y BM25.
3. Búsqueda web que combine texto con filtros estructurados y geográficos, usando exclusivamente PostGIS para la lógica geográfica.

La prioridad actual es el backend: scrapers, normalización, persistencia, ingesta, indexación y consultas. El frontend y el mapa se definirán e implementarán más adelante. El listado HTML existente sirve como base de prueba; su presencia no significa que la interfaz futura esté definida.

## Stack acordado

| Componente | Función |
| --- | --- |
| Python y Django | Backend y jobs de ingesta; Django ya está presente en el repositorio. |
| Supabase / PostgreSQL | Base principal y fuente de verdad: propiedades completas y filtros estructurados. |
| PostGIS | Extensión de PostgreSQL para coordenadas y toda consulta geográfica: radio, distancia, bounding boxes y polígonos. |
| Elasticsearch / Elastic Cloud | Índice de texto completo y ranking por relevancia alojado en Elastic Cloud; reconstruible desde PostgreSQL. |
| Render | Django ya desplegado en el plan Free y conectado a Supabase; conexión con Elastic Cloud pendiente. |
| GitHub Actions | Ejecución automática del scraper en un runner de GitHub, con frecuencia y configuración pendientes. |
| Frontend | Tecnología e implementación pendientes, incluido el mapa. |

PostGIS forma parte de PostgreSQL. Elasticsearch es un índice separado que no reemplaza la base principal y no realizará filtros geográficos. SQLite sigue disponible para desarrollo local. La conexión PostgreSQL y las migraciones hasta `0011` están verificadas en Supabase. No se realizó un traslado automático de datos locales.

La entrega requiere un sitio desplegado. El entorno objetivo es Django en Render, PostgreSQL/PostGIS en Supabase y Elasticsearch en Elastic Cloud. El 9 de octubre de 2026 el equipo confirmó que el despliegue básico muestra las propiedades de Brega guardadas en Supabase desde `/propiedades/`. Elasticsearch sigue pendiente. PostGIS ya está integrado en Supabase y en el código local, pendiente de despliegue. El scraper se ejecuta manualmente por comando; GitHub Actions será su ejecución automática, con workflow y frecuencia pendientes. Los comandos locales se conservan para desarrollo y pruebas. Elastic Cloud ofrece una [prueba de 14 días sin tarjeta](https://www.elastic.co/cloud/elasticsearch-service/signup); hay que confirmar que cubra la evaluación y resolver la continuidad después de su vencimiento. Ver [la configuración del despliegue y el próximo paso](docs/despliegue.md).

Actions ejecutará el comando de ingesta con credenciales en GitHub Secrets y guardará los datos en Supabase; actualizará Elasticsearch después de implementar esa integración. Los runners estándar son gratuitos en repositorios públicos. Para repositorios privados, GitHub Free incluye 2.000 minutos por mes compartidos entre los workflows y repositorios privados de la cuenta propietaria, no por integrante. La visibilidad de este repositorio no está verificada. Ver [condiciones oficiales](https://docs.github.com/en/billing/concepts/product-billing/github-actions). El horario programado puede sufrir demoras.

También se prevén solicitudes periódicas desde un servicio externo a una ruta ligera de Django para reducir el reposo por inactividad. El proveedor y el intervalo siguen por definir; Vercel es una opción consultada, no adoptada. Esos pings no ejecutarán la ingesta ni garantizan disponibilidad continua. [Render Cron Jobs](https://render.com/docs/cronjobs), con un mínimo mensual de USD 1 por servicio, queda como alternativa al job de GitHub Actions; no es necesario contratarlo para el esquema elegido. [Vercel Hobby](https://vercel.com/docs/cron-jobs/usage-and-pricing) limita cada cron a una ejecución diaria.

## Flujo previsto

```text
Scrapers/adaptadores por inmobiliaria
               ↓
       Normalización común
               ↓
Supabase / PostgreSQL con PostGIS
               ↓
   Indexación en Elasticsearch

Frontend futuro + mapa → Backend Python
                           ├─ Elasticsearch: texto y ranking
                           └─ PostgreSQL + PostGIS: datos y filtros
                        → Resultados al frontend
```

El job crea o actualiza publicaciones sin duplicarlas por fuente e identificador. Primero guarda en PostgreSQL y después indexa en Elasticsearch. La reconstrucción del índice y la recuperación de indexaciones fallidas deben contemplarse al implementar la integración.

Las búsquedas consultan la información guardada y no ejecutan scraping. El backend coordina Elasticsearch para texto/relevancia, PostgreSQL para filtros estructurados y PostGIS para ubicación; el frontend no accede directamente a esos servicios.

Los filtros previstos incluyen tipo, venta/alquiler, precio mínimo/máximo con moneda y ubicación. Una propiedad puede tener venta y alquiler con precios distintos. El modelo común también contemplará, según disponibilidad, dirección, ciudad, barrio, dormitorios, ambientes, superficie y unidad, título, descripción, características, imágenes, URL y coordenadas. Los datos faltantes se representarán sin inventarlos.

La búsqueda con mapa permitirá indicar un punto y radio, o seleccionar/dibujar un área. PostGIS ya resuelve radio con `ST_DWithin` y rectángulos con `ST_Covers`, en WGS84 y con índices GiST. La consulta por polígonos arbitrarios sigue pendiente; ver [límites y precisión](docs/postgis.md). Hay geocodificación experimental; su validación y la extracción de localidad quedan pendientes.

## Qué existe actualmente

- Proyecto Django `config/` y aplicación `propiedades/`, con SQLite local y configuración PostgreSQL/Supabase mediante `.env` y psycopg.
- Despliegue básico de Django en Render Free: Gunicorn, WhiteNoise, clave secreta por entorno, `DEBUG=False`, dominio permitido automáticamente y configuración HTTPS del proxy. Preparación en el commit `5f61bf9`; listado público comprobado por el equipo.
- Modelo `Propiedad` con procedencia, dirección, tipo, dormitorios, venta/alquiler, precios y monedas por operación, URL original y fecha de actualización; unicidad por `(fuente, identificador_fuente)`.
- Título, descripción, características como texto, ciudad/provincia/zona, ambientes y baños opcionales, agregados en la migración `0008`. Las amenidades no necesitan una columna individual.
- Scraper Brega con Requests y Beautiful Soup, paginación y normalización básica.
- Flujo común en `propiedades/ingesta.py`, contrato `PublicacionNormalizada` y adaptador Brega registrado. El comando `importar_propiedades brega` crea o actualiza publicaciones; `importar_brega` es un alias compatible.
- Brega consulta la ficha completa en cada ingesta y obtiene texto, características y cantidades. Los errores de ficha conservan los detalles guardados. El rótulo ambiguo `Ubicación` se guarda como zona, sin asumir ciudad.
- Brega extrae coordenadas de los círculos publicados en el mapa de la ficha y conserva `ubicacion_aproximada` y `radio_ubicacion_m` (migración `0009`). No requiere ciudad para guardar coordenadas de la fuente. Esas posiciones representan áreas aproximadas, no direcciones exactas.
- La geocodificación experimental con geopy/Nominatim se usa cuando faltan coordenadas de fuente y hay ciudad explícita; no asume Rafaela. Los cambios de ubicación invalidan coordenadas anteriores salvo que la fuente aporte un par nuevo.
- Enriquecimiento inverso opcional con `importar_propiedades brega --completar-ubicacion`: completa ciudad/provincia faltantes con procedencia por campo y caché persistente (migración `0010`), conserva coordenadas/precisión y tolera fallos del proveedor. Los nombres inferidos se invalidan si cambia el punto; los explícitos tienen prioridad. Ver [la guía](docs/base_de_datos.md).
- Listado `/propiedades/` con filtro de venta/alquiler y enlace al aviso original; muestra alquileres por defecto.

La conexión y migraciones hasta `0011` están verificadas en Supabase. La revisión del 8 de octubre de 2026 encontró 173 publicaciones, 172 con coordenadas completas, 170 con ciudad inferida y 172 con provincia inferida; esos conteos no garantizan precisión individual. PostGIS está integrado; Elasticsearch sigue pendiente. Tampoco existen el scraper Avantix, la tercera fuente, un adaptador común por plataforma, búsqueda textual, filtros de tipo/precio, API JSON de búsqueda o mapa. Hay filtros PostGIS por radio y rectángulo, pendientes de despliegue. Pasaron 48 pruebas de ingesta, extracción, comandos, geocodificación y configuración de bases (`python manage.py test propiedades config` con SQLite). Ver [AGENTS.md](AGENTS.md) para ejecutarlas sin utilizar Supabase.

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

La ingesta es manual y consulta el sitio externo de Brega; puede tardar por la paginación, las fichas y las pausas entre solicitudes:

```powershell
.\.venv\Scripts\python.exe manage.py importar_propiedades brega
```

Para iniciar el servidor de desarrollo:

```powershell
.\.venv\Scripts\python.exe manage.py runserver
```

Abrir [el listado local](http://127.0.0.1:8000/propiedades/). El listado muestra los datos de la base configurada; sin datos previos estará vacío. Usar Supabase permite consultar las publicaciones ya cargadas sin repetir la ingesta. El alias `importar_brega` sigue disponible. El comando general que importará todas las fuentes en la versión final está acordado pero todavía no implementado: hoy el argumento `brega` es obligatorio. La ejecución local es para desarrollo y pruebas; Django ya está desplegado en Render con Supabase, mientras que Elasticsearch sigue pendiente y el código de filtros PostGIS debe desplegarse.

## Próximos pasos

1. Crear Elasticsearch en Elastic Cloud y comprobar la conexión desde Django, con credenciales por entorno y vencimiento de la prueba registrado.
2. Crear el índice con análisis en español y un comando que lo reconstruya desde las propiedades de Supabase; comprobar búsquedas y ranking.
3. Integrar búsqueda e indexación después de persistir, definir recuperación de errores y probar desde Render.
4. Incorporar una segunda y luego una tercera inmobiliaria reutilizando el flujo común. Avantix es la siguiente fuente propuesta; la tercera sigue pendiente. Preparar el único comando general de ingesta acordado.
5. Configurar y probar el workflow de GitHub Actions para automatizar la ingesta, con credenciales en Secrets y sin ejecuciones simultáneas.
6. Integrar PostGIS para coordenadas y consultas por radio/área con índices espaciales; coordinar texto y filtros desde el backend. Desarrollar frontend y mapa posteriormente y comprobar las features desde la URL pública.

El workflow y frecuencia de GitHub Actions, visibilidad del repositorio y cuota disponible, proveedor e intervalo de los pings, validación de la geocodificación experimental y extracción de localidad, tratamiento de publicaciones retiradas, coordinación/paginación de búsquedas y configuración de Elastic Cloud siguen pendientes. La detección de una misma propiedad publicada por inmobiliarias diferentes tiene un alcance distinto de evitar duplicados en cargas repetidas y aún debe definirse.

## Contexto para colaborar

Leer [AGENTS.md](AGENTS.md) antes de proponer cambios. Contiene las decisiones confirmadas, el estado actual, los hallazgos de las fuentes y los criterios para avanzar de forma incremental sin sobrearquitecturar. La compatibilidad Tokko de Brega y Avantix y el adaptador compartido deben verificarse antes de asumir reutilización.
