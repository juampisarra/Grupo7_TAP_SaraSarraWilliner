# Contexto e instrucciones para agentes

Este archivo es el punto de entrada para cualquier agente que trabaje en este repositorio. Leerlo antes de proponer cambios o implementar funcionalidades. Mantenerlo actualizado cuando el equipo confirme nuevas decisiones; no convertir propuestas en decisiones sin confirmación.

## Proyecto y prioridades

Trabajo práctico de TAP del Grupo 7 (Sara, Sarra y Williner): un Observatorio Inmobiliario orientado inicialmente a propiedades de Rafaela. Centraliza publicaciones públicas de distintas inmobiliarias para permitir buscar, filtrar y comparar opciones desde una única aplicación, conservando la inmobiliaria de origen y el enlace al aviso original.

Las tres features principales acordadas son:

1. Ingesta mediante scraping desde múltiples inmobiliarias.
2. Búsqueda de texto completo con Elasticsearch y ranking por relevancia.
3. Búsqueda web con filtros estructurados y geográficos, utilizando exclusivamente PostGIS para la lógica geográfica.

La prioridad inmediata es implementar las capacidades del backend y preparar la integración futura. El frontend y el mapa se definirán e implementarán más adelante; por ahora no desarrollar frontend salvo que sea estrictamente necesario para probar una feature. El listado HTML existente es una base de prueba, no la interfaz definitiva acordada.

Los resúmenes del mercado y análisis históricos siguen siendo posibles ampliaciones, no requisitos iniciales. No se trata de un sistema de gestión de contratos o alquileres.

## Stack y responsabilidades confirmadas

| Tecnología | Responsabilidad |
| --- | --- |
| Python | Lenguaje principal para el backend y los jobs de ingesta. |
| Django | Framework del backend ya adoptado e implementado en el repositorio. |
| Supabase / PostgreSQL | Base de datos principal y fuente de verdad: persistencia, información completa de las propiedades y filtros estructurados. |
| PostGIS | Extensión de PostgreSQL responsable de toda la lógica geográfica: coordenadas, distancia, radio, áreas y consultas e índices espaciales. No es una base de datos independiente. |
| Elasticsearch | Índice especializado exclusivamente en búsqueda de texto completo y ranking por relevancia. No reemplaza PostgreSQL ni realiza filtros geográficos. |
| Render | Opción principal de deployment, considerando la necesidad de ejecutar jobs y utilizar Elasticsearch. El despliegue y la ubicación concreta de los servicios aún deben resolverse. |
| Frontend | Tecnología e implementación pendientes, incluida la interfaz de mapa. |

Supabase/PostgreSQL, PostGIS y Elasticsearch son decisiones del stack objetivo; su integración todavía está pendiente. SQLite es la configuración actual del prototipo, no la base principal elegida para el proyecto.

## Estado real del repositorio

Al actualizar este contexto, el código contiene:

- Un proyecto Django en `config/` y la aplicación `propiedades/`, con SQLite configurado en `config/settings.py`.
- El modelo `Propiedad`, con fuente, identificador de origen, dirección, tipo, dormitorios y su estado de verificación, operaciones de venta/alquiler, precios y monedas separados por operación, URL original y fecha de actualización.
- Una restricción única por `(fuente, identificador_fuente)` y un importador que usa `update_or_create` para crear o actualizar publicaciones de Brega.
- Un scraper Brega en `propiedades/scraping/brega.py` que consulta `/Venta` y `/Alquiler` con Requests y Beautiful Soup, recorre páginas con `p`, evita identificadores repetidos y termina ante un lote vacío o sin identificadores nuevos. Tiene un límite de seguridad de 50 páginas, timeout de 15 segundos y pausas de 0,5 segundos; no tiene reintentos implementados.
- Normalización básica de precios, monedas, tipos y operaciones en `propiedades/scraping/normalizacion.py`. El comando `python manage.py importar_brega` integra la ingesta y consulta dormitorios en las fichas; reutiliza los dormitorios ya verificados.
- Una vista y plantilla en `/propiedades/` que consultan datos guardados, filtran por venta o alquiler y enlazan al aviso original. El filtro predeterminado es alquiler.

Todavía no hay integración con Supabase/PostgreSQL, PostGIS ni Elasticsearch; tampoco scrapers de Avantix u otra tercera fuente, un adaptador común por plataforma, búsqueda textual, filtros de precio/tipo/geográficos, API de búsqueda ni mapa. `propiedades/tests.py` no contiene pruebas implementadas. Esta revisión del código no equivale a una verificación actual de los sitios externos ni a una ejecución de la ingesta.

## Arquitectura y flujos esperados

```text
Job Python
  ├─ Scraper/adaptador inmobiliaria A
  ├─ Scraper/adaptador inmobiliaria B
  └─ Scraper/adaptador inmobiliaria C
                   │
                   ▼
             Normalización común
                   │
                   ▼
     Supabase / PostgreSQL con PostGIS
                   │
                   ▼
         Indexación en Elasticsearch

Frontend futuro + mapa → Backend Python
                           ├─ Elasticsearch: texto y relevancia
                           └─ PostgreSQL + PostGIS: datos y filtros
                        → Respuesta única al frontend
```

El scraping debe ejecutarse separado de las consultas de los usuarios: una visita o un cambio de filtro no dispara pedidos a los sitios externos. El usuario consulta la última información guardada. La frecuencia de actualización queda por definir; inicialmente la ingesta puede ejecutarse manualmente como job/comando.

Separar scraping, normalización, acceso a base de datos, indexación, búsqueda textual, consultas geográficas y API. Mantener una solución modular y entendible; no crear tres sistemas independientes ni introducir microservicios, colas u otras capas sin necesidad.

El backend Python coordina las consultas y devuelve un único conjunto de resultados. El frontend no debe acceder directamente a Elasticsearch ni a la base de datos.

## Ingesta y modelo normalizado común

Preparar desde el comienzo una estructura común para aproximadamente tres inmobiliarias. Cada fuente tendrá su scraper/adaptador y configuración; todos deberán producir el mismo modelo normalizado. Se puede compartir un adaptador entre fuentes de la misma plataforma cuando se compruebe su compatibilidad. La lógica específica de cada sitio debe quedar separada de la persistencia, normalización e indexación comunes.

Los datos a contemplar, según lo que realmente proporcione cada fuente, incluyen:

- Identificador de la publicación y la inmobiliaria de origen.
- Tipo de propiedad y operación: venta, alquiler o ambas cuando corresponda.
- Precio y moneda por operación; conservar los campos separados existentes cuando una publicación ofrezca venta y alquiler.
- Dirección, ciudad, barrio o zona.
- Dormitorios, ambientes y superficie con su unidad.
- Título, descripción y características disponibles.
- URL original e imágenes.
- Latitud, longitud y una representación compatible con PostGIS cuando existan coordenadas.

Estos son objetivos del modelo común, no campos ya implementados en su totalidad. Representar los datos faltantes sin inventarlos y distinguir ausencia de información de errores de lectura. No asumir que todas las publicaciones tienen coordenadas ni completar su ciudad únicamente por el foco inicial en Rafaela. Mantener diferenciadas monedas y unidades: un filtro de precio debe indicar la moneda y la operación para comparar valores correctamente.

El job debe crear publicaciones nuevas y actualizar las existentes sin duplicarlas al repetir una carga. Conservar la identidad `(fuente, identificador_fuente)` y la procedencia. Detectar la misma propiedad anunciada por inmobiliarias diferentes es un problema distinto; su alcance sigue pendiente.

La sincronización acordada es:

`Scraper → normalización → PostgreSQL → indexación en Elasticsearch`.

Primero persistir en PostgreSQL y después indexar. El índice debe poder reconstruirse completamente desde las propiedades guardadas en PostgreSQL si se pierde. Al implementar esta integración, definir cómo reintentar o recuperar indexaciones fallidas sin perder datos ni crear duplicados; no dar por resuelta la sincronización entre ambos servicios.

## Búsqueda de texto completo

Utilizar Elasticsearch como motor real de búsqueda; una consulta SQL con `LIKE` no cumple esta feature. PostgreSQL conserva los datos completos y la autoridad sobre ellos.

El objetivo académico incluye documentos, términos, índices invertidos, posting lists, frecuencia de términos, rareza de términos, relevancia y ranking con BM25. Por ejemplo, un índice invertido relaciona `cochera → [propiedad 2, propiedad 8, propiedad 15]` y `quincho → [propiedad 3, propiedad 8]`. Los términos menos frecuentes pueden aportar mayor poder discriminante a la relevancia.

Una búsqueda como `departamento con cochera y quincho` debe devolver resultados ordenados por relevancia, no limitarse a comprobar si aparece cualquiera de las palabras. Los campos candidatos a indexar incluyen título, descripción, dirección, barrio, ciudad, tipo de propiedad y características disponibles.

Contemplar el análisis del texto en español y las stopwords, como `para`, `la`, `el`, `de`, `con` e `y`. La configuración concreta de analizadores, campos y pesos se definirá al implementar y probar el buscador. Elasticsearch se utilizará únicamente para texto y relevancia; toda la lógica geográfica corresponde a PostGIS.

## Filtros estructurados y combinación de resultados

La búsqueda futura debe combinar texto libre y relevancia con tipo de inmueble, operación, precio mínimo/máximo y ubicación. Dormitorios, ambientes, superficie y otros filtros podrán agregarse según los datos disponibles.

- Elasticsearch encuentra y ordena las coincidencias textuales.
- PostgreSQL aplica los filtros estructurados y entrega los datos completos.
- PostGIS aplica los filtros geográficos dentro de PostgreSQL.
- El backend coordina estos resultados y devuelve propiedades que cumplen todas las condiciones solicitadas, conservando el ranking textual cuando haya una búsqueda de texto.

Ejemplo: `departamento con cochera`, operación alquiler, tipo departamento, precio máximo ARS 700.000 y radio de 2 km desde un punto seleccionado. El backend combina relevancia de Elasticsearch, precio/operación/tipo de PostgreSQL y distancia de PostGIS. Sin texto libre, los filtros deben poder consultar PostgreSQL/PostGIS. La estrategia concreta de coordinación, orden y paginación queda por definir al implementar.

## Geografía exclusivamente con PostGIS

Guardar las coordenadas disponibles en PostgreSQL y utilizarlas mediante una representación espacial de PostGIS. Si una fuente solo aporta una dirección, analizar más adelante un mecanismo de geocodificación; todavía no hay proveedor ni proceso elegido. No inventar ubicaciones para datos ausentes.

Las modalidades previstas son:

| Modalidad | Entrada al backend | Consulta prevista en PostGIS |
| --- | --- | --- |
| Radio | Latitud, longitud y radio con su unidad; por ejemplo, 2 km. | Determinar qué propiedades están dentro de la distancia, evaluando `ST_DWithin` según el modelo espacial elegido. |
| Área | Rectángulo/bounding box o geometría/puntos de un polígono seleccionado o dibujado. | Determinar qué propiedades están dentro del área, evaluando `ST_Within`, `ST_Contains`, intersecciones u operaciones de bounding box según corresponda. |

Definir la representación espacial, el sistema de referencia, las unidades de distancia y el tratamiento de los límites del área antes de elegir las funciones concretas. Evaluar índices espaciales como GiST para evitar recorridos completos en cada consulta. PostGIS es la única tecnología responsable de coordenadas y consultas espaciales: no implementar distancia, radio, bounding boxes ni polígonos en Elasticsearch.

El frontend futuro permitirá seleccionar un punto/radio o dibujar un área en un mapa, de forma similar a Airbnb; el cálculo y filtrado geográficos estarán en el backend mediante PostGIS.

## Fuentes exploradas y reutilización

Brega ya tiene un scraper en el repositorio. Se propone sumar Avantix después para comprobar la reutilización; el orden no es una restricción técnica. La tercera fuente todavía no está elegida; se mantiene la propuesta de incorporar otra plataforma para demostrar la extensión con un adaptador distinto.

- Brega: https://www.bregainmobiliaria.ar
- Avantix: https://www.avantix.ar

La exploración manual del usuario mostró en ambos sitios un patrón compatible con Tokko: elementos `li[prop-id]`, clases `.prop-desc-dir` y `.prop-valor-nro`, un primer lote en el HTML y carga adicional al hacer scroll, solicitudes `p=2`, `p=3` y un marcador `--NoMoreProperties--`.

El código Brega utiliza esos selectores y el parámetro `p`, pero no comprueba el marcador de fin: termina por lotes vacíos o sin identificadores nuevos. La compatibilidad de Avantix y la reutilización de un adaptador Tokko siguen sin verificarse con código. Verificar las URLs exactas, parámetros, respuestas y selectores antes de agregar o modificar una fuente. No fijar `p=3` como límite universal ni asumir que todos los sitios Tokko son idénticos.

La hipótesis es compartir un adaptador Tokko entre Brega y Avantix, cambiando la configuración por inmobiliaria: nombre, URL base, URL de búsqueda y ajustes necesarios. Confirmar con código cuánto se puede reutilizar.

## Plan incremental acordado

1. Revisar el código existente y separar el núcleo común de la lógica específica de Brega sin sobrearquitecturar.
2. Completar la primera inmobiliaria de punta a punta: extracción, modelo normalizado, persistencia en Supabase/PostgreSQL e indexación en Elasticsearch.
3. Verificar altas, actualizaciones, ausencia de duplicados por fuente y reconstrucción del índice desde PostgreSQL; probar búsqueda textual y ranking.
4. Incorporar la segunda inmobiliaria y después la tercera, reutilizando el flujo común y verificando los datos de cada fuente.
5. Integrar PostGIS, preparar el almacenamiento de coordenadas y las consultas por radio/área con índices espaciales.
6. Preparar la búsqueda del backend que combine texto, filtros estructurados y filtros geográficos. Desarrollar frontend y mapa posteriormente.

Las prioridades inmediatas son arquitectura de scrapers, modelo común, persistencia, job de ingesta, integración/indexación/búsqueda con Elasticsearch y soporte geográfico con PostGIS. El plan describe trabajo pendiente, no funcionalidades ya terminadas.

## Decisiones de implementación pendientes

- Tercera inmobiliaria y compatibilidad del adaptador compartido con Avantix.
- Detalles del esquema común, configuración y migración a Supabase/PostgreSQL, y representación espacial en PostGIS.
- Frecuencia y ejecución programada de la ingesta; política de publicaciones retiradas y recuperación de errores de indexación.
- Configuración de Elasticsearch, coordinación de consultas, orden y paginación.
- Geocodificación de direcciones y tratamiento de ubicaciones ausentes.
- Tecnología del frontend, mapa y contrato de la API futura.
- Configuración concreta de Render y dónde ejecutar cada servicio, incluido Elasticsearch.

Requests y Beautiful Soup ya se usan para Brega. Comprobar primero si las consultas directas permiten obtener los datos de cada nueva fuente; no dar por necesaria la automatización de un navegador. No se ha adoptado React, un framework de scraping adicional, colas de tareas ni microservicios. Vercel no es la opción principal acordada de deployment.

## Criterios de trabajo

- Revisar el estado real del repositorio antes de hacer cambios grandes y respetar sus convenciones cuando sean razonables.
- Priorizar una solución clara, modular y mantenible para un trabajo práctico universitario. Explicar las decisiones y los conceptos nuevos de forma sencilla.
- Avanzar por pasos pequeños que el equipo pueda ejecutar y comprender; agregar nuevas fuentes sin modificar fuertemente el núcleo.
- Consultar las fuentes con tiempos de espera, ritmo moderado y reintentos limitados; evitar bucles de paginación y cargas duplicadas.
- Verificar extracción y normalización con ejemplos reales; diferenciar datos ausentes de errores y conservar procedencia, monedas y unidades.
- Mantener separadas ingesta y búsquedas, persistencia e índice textual, y consultas textuales y geográficas.
- No presentar tareas pendientes como funcionalidades existentes ni implementar frontend sin la necesidad de prueba indicada o una instrucción posterior del equipo.

## Referencia compartida

Resumen de la idea en el Google Doc «Lluvia de Ideas», pestaña «Idea del TP»:
https://docs.google.com/document/d/1HiQLoD9vaR4fEAyy5bm_5d_fspXELkBCkJn2u0wkB3A/edit?tab=t.xl5s41rt5ksx

Este AGENTS.md contiene el contexto necesario para comenzar sin depender del acceso a la conversación o al documento externo. Las instrucciones explícitas posteriores del equipo prevalecen sobre este contexto.
