# Grupo7_TAP_SaraSarraWilliner

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
| Render | Alojamiento previsto de Django, conectado a Supabase y Elastic Cloud. |
| GitHub Actions | Ejecución automática del scraper en un runner de GitHub, con frecuencia y configuración pendientes. |
| Frontend | Tecnología e implementación pendientes, incluido el mapa. |

PostGIS forma parte de PostgreSQL. Elasticsearch es un índice separado que no reemplaza la base principal y no realizará filtros geográficos. SQLite sigue disponible para desarrollo local. La conexión PostgreSQL y las migraciones hasta `0010` están verificadas en Supabase. No se realizó un traslado automático de datos locales.

El profesor confirmó que el sitio debe estar desplegado: el entorno objetivo es Django en Render, PostgreSQL/PostGIS en Supabase y Elasticsearch en Elastic Cloud. Esto reemplaza la alternativa de presentar la aplicación exclusivamente desde una computadora. El equipo ejecutará el scraper mediante GitHub Actions para evitar el mínimo mensual de un job de Render; el workflow y su frecuencia siguen pendientes. Los comandos locales se conservan para desarrollo y pruebas; las búsquedas del sitio público deben utilizar los servicios desplegados. La prueba gratuita de 14 días de Elastic Cloud puede servir para la entrega si cubre la fecha de evaluación, pero no es alojamiento gratuito permanente. El despliegue y la integración de PostGIS y Elasticsearch siguen pendientes; una presentación solo local requiere conversar con el profesor si desplegar resulta imposible.

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

La búsqueda con mapa permitirá indicar un punto y radio, o seleccionar/dibujar un área. PostGIS resolverá las consultas espaciales; al implementarlas se definirán la representación espacial, las unidades y funciones apropiadas como `ST_DWithin`, `ST_Within` o `ST_Contains`, y se evaluarán índices GiST. Hay geocodificación experimental; su validación y la extracción de localidad quedan pendientes.

## Qué existe actualmente

- Proyecto Django `config/` y aplicación `propiedades/`, con SQLite local y configuración PostgreSQL/Supabase mediante `.env` y psycopg.
- Modelo `Propiedad` con procedencia, dirección, tipo, dormitorios, venta/alquiler, precios y monedas por operación, URL original y fecha de actualización; unicidad por `(fuente, identificador_fuente)`.
- Título, descripción, características como texto, ciudad/provincia/zona, ambientes y baños opcionales, agregados en la migración `0008`. Las amenidades no necesitan una columna individual.
- Scraper Brega con Requests y Beautiful Soup, paginación y normalización básica.
- Flujo común en `propiedades/ingesta.py`, contrato `PublicacionNormalizada` y adaptador Brega registrado. El comando `importar_propiedades brega` crea o actualiza publicaciones; `importar_brega` es un alias compatible.
- Brega consulta la ficha completa en cada ingesta y obtiene texto, características y cantidades. Los errores de ficha conservan los detalles guardados. El rótulo ambiguo `Ubicación` se guarda como zona, sin asumir ciudad.
- Brega extrae coordenadas de los círculos publicados en el mapa de la ficha y conserva `ubicacion_aproximada` y `radio_ubicacion_m` (migración `0009`). No requiere ciudad para guardar coordenadas de la fuente. Esas posiciones representan áreas aproximadas, no direcciones exactas.
- La geocodificación experimental con geopy/Nominatim se usa cuando faltan coordenadas de fuente y hay ciudad explícita; no asume Rafaela. Los cambios de ubicación invalidan coordenadas anteriores salvo que la fuente aporte un par nuevo.
- Enriquecimiento inverso opcional con `importar_propiedades brega --completar-ubicacion`: completa ciudad/provincia faltantes con procedencia por campo y caché persistente (migración `0010`), conserva coordenadas/precisión y tolera fallos del proveedor. Los nombres inferidos se invalidan si cambia el punto; los explícitos tienen prioridad. Ver [la guía](docs/base_de_datos.md).
- Listado `/propiedades/` con filtro de venta/alquiler y enlace al aviso original; muestra alquileres por defecto.

La conexión y migraciones hasta `0010` están verificadas en Supabase. La revisión del 8 de octubre de 2026 encontró 173 publicaciones, 172 con coordenadas completas, 170 con ciudad inferida y 172 con provincia inferida; esos conteos no garantizan precisión individual. No se integraron PostGIS o Elasticsearch. Tampoco existen el scraper Avantix, la tercera fuente, un adaptador común por plataforma, búsqueda textual, filtros de tipo/precio/geografía, API de búsqueda o mapa. Pasaron 48 pruebas de ingesta, extracción, comandos, geocodificación y configuración de bases (`python manage.py test propiedades config` con SQLite). Ver [AGENTS.md](AGENTS.md) para ejecutarlas sin utilizar Supabase.

## Ejecutar el prototipo local

Desde la raíz del repositorio, con Python instalado, en PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
```

La ingesta es manual y consulta el sitio externo de Brega; puede tardar por la paginación, las fichas y las pausas entre solicitudes:

```powershell
.\.venv\Scripts\python.exe manage.py importar_brega
```

Para iniciar el servidor de desarrollo:

```powershell
.\.venv\Scripts\python.exe manage.py runserver
```

Abrir [el listado local](http://127.0.0.1:8000/propiedades/). El listado muestra los datos guardados; sin ingesta previa estará vacío. Sin configurar `.env`, estos comandos usan SQLite. Para conectar Supabase/PostgreSQL y trasladar publicaciones existentes, seguir [la guía de bases de datos](docs/base_de_datos.md). Esta ejecución es para desarrollo y pruebas: la entrega requiere el sitio desplegado en Render, con Supabase y Elastic Cloud. La integración de Elasticsearch y PostGIS sigue pendiente.

## Próximos pasos

1. Ampliar el contrato normalizado común ya implementado con los datos adicionales que aporten las fuentes.
2. Completar la primera fuente con persistencia en Supabase/PostgreSQL e indexación en Elasticsearch; verificar altas, actualizaciones, duplicados por fuente, reconstrucción del índice y búsqueda textual.
3. Incorporar una segunda y luego una tercera inmobiliaria reutilizando el flujo común. Avantix es la siguiente fuente propuesta; la tercera sigue pendiente.
4. Integrar PostGIS y preparar coordenadas, consultas por radio/área e índices espaciales.
5. Coordinar texto, relevancia y filtros desde el backend; desarrollar frontend y mapa posteriormente.
6. Preparar Django para producción y desplegarlo en Render, conectado a Supabase y Elastic Cloud; comprobar las funciones desde la URL pública.

El workflow y frecuencia de GitHub Actions, visibilidad del repositorio y cuota disponible, proveedor e intervalo de los pings, validación de la geocodificación experimental y extracción de localidad, tratamiento de publicaciones retiradas, coordinación/paginación de búsquedas, configuración de Elastic Cloud y despliegue en Render siguen pendientes. La detección de una misma propiedad publicada por inmobiliarias diferentes tiene un alcance distinto de evitar duplicados en cargas repetidas y aún debe definirse.

## Contexto para colaborar

Leer [AGENTS.md](AGENTS.md) antes de proponer cambios. Contiene las decisiones confirmadas, el estado actual, los hallazgos de las fuentes y los criterios para avanzar de forma incremental sin sobrearquitecturar. La compatibilidad Tokko de Brega y Avantix y el adaptador compartido deben verificarse antes de asumir reutilización.
