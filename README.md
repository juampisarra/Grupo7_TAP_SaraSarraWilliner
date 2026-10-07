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
| Elasticsearch | Índice de texto completo y ranking por relevancia; reconstruible desde PostgreSQL. |
| Render | Opción principal de deployment, considerando jobs y Elasticsearch; configuración y distribución de servicios pendientes. |
| Frontend | Tecnología e implementación pendientes, incluido el mapa. |

PostGIS forma parte de PostgreSQL. Elasticsearch es un índice separado que no reemplaza la base principal y no realizará filtros geográficos. SQLite es la configuración actual del prototipo; la integración con el stack objetivo todavía debe implementarse.

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

La búsqueda con mapa permitirá indicar un punto y radio, o seleccionar/dibujar un área. PostGIS resolverá las consultas espaciales; al implementarlas se definirán la representación espacial, las unidades y funciones apropiadas como `ST_DWithin`, `ST_Within` o `ST_Contains`, y se evaluarán índices GiST. La geocodificación de direcciones queda pendiente.

## Qué existe actualmente

- Proyecto Django `config/` y aplicación `propiedades/`, con SQLite local.
- Modelo `Propiedad` con procedencia, dirección, tipo, dormitorios, venta/alquiler, precios y monedas por operación, URL original y fecha de actualización; unicidad por `(fuente, identificador_fuente)`.
- Scraper Brega con Requests y Beautiful Soup, paginación y normalización básica.
- Comando `importar_brega` que crea o actualiza publicaciones y consulta dormitorios en las fichas, reutilizando los ya verificados.
- Listado `/propiedades/` con filtro de venta/alquiler y enlace al aviso original; muestra alquileres por defecto.

Todavía no se integraron Supabase/PostgreSQL, PostGIS ni Elasticsearch. Tampoco existen el scraper Avantix, la tercera fuente, un adaptador común por plataforma, búsqueda textual, filtros de tipo/precio/geografía, API de búsqueda o mapa. El archivo `propiedades/tests.py` todavía no contiene pruebas implementadas. Esta descripción surge de revisar el código; no implica una ejecución reciente del scraper contra la fuente.

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

Abrir [el listado local](http://127.0.0.1:8000/propiedades/). El listado muestra los datos guardados; sin ingesta previa estará vacío. Estos comandos usan la configuración SQLite actual y no configuran Supabase, Elasticsearch, PostGIS ni un despliegue en Render.

## Próximos pasos

1. Separar el flujo común de la lógica específica de Brega y definir el modelo normalizado.
2. Completar la primera fuente con persistencia en Supabase/PostgreSQL e indexación en Elasticsearch; verificar altas, actualizaciones, duplicados por fuente, reconstrucción del índice y búsqueda textual.
3. Incorporar una segunda y luego una tercera inmobiliaria reutilizando el flujo común. Avantix es la siguiente fuente propuesta; la tercera sigue pendiente.
4. Integrar PostGIS y preparar coordenadas, consultas por radio/área e índices espaciales.
5. Coordinar texto, relevancia y filtros desde el backend; desarrollar frontend y mapa posteriormente.

La frecuencia de actualización, geocodificación, tratamiento de publicaciones retiradas, coordinación/paginación de búsquedas y configuración concreta del despliegue siguen pendientes. La detección de una misma propiedad publicada por inmobiliarias diferentes tiene un alcance distinto de evitar duplicados en cargas repetidas y aún debe definirse.

## Contexto para colaborar

Leer [AGENTS.md](AGENTS.md) antes de proponer cambios. Contiene las decisiones confirmadas, el estado actual, los hallazgos de las fuentes y los criterios para avanzar de forma incremental sin sobrearquitecturar. La compatibilidad Tokko de Brega y Avantix y el adaptador compartido deben verificarse antes de asumir reutilización.
