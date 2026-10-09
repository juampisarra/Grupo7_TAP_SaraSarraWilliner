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

Supabase/PostgreSQL, PostGIS y Elasticsearch son decisiones del stack objetivo. La conexión PostgreSQL está implementada mediante psycopg y variables de entorno, y se verificaron las migraciones hasta `0010` en Supabase. En la revisión del 8 de octubre de 2026 se comprobaron 173 publicaciones, incluyendo datos guardados por el enriquecimiento inverso. No se realizó un traslado automático de SQLite. PostGIS y Elasticsearch siguen pendientes. Sin configuración se utiliza SQLite para desarrollo local. Guardar `.env` como UTF-8 sin BOM para que se reconozca correctamente la primera variable.

## Estado real del repositorio

Al actualizar este contexto, el código contiene:

- Un proyecto Django en `config/` y la aplicación `propiedades/`. `config/database.py` permite SQLite o PostgreSQL según `DB_ENGINE`; `config/settings.py` carga `.env` sin sobrescribir variables del sistema. `.env.example` documenta los valores; no contiene credenciales reales.
- El modelo `Propiedad`, con fuente, identificador de origen, dirección, tipo, dormitorios y su estado de verificación, operaciones de venta/alquiler, precios y monedas separados por operación, URL original, fecha de actualización y latitud/longitud opcionales. Las coordenadas son campos FloatField del prototipo, todavía sin representación PostGIS.
- Ampliación acotada del modelo en la migración `0008`: título, descripción, características como texto, ciudad, provincia, zona, ambientes y baños. Dormitorios ya existía. No se agregan columnas para cada amenidad: cochera, parrilla y otras características se conservan en el texto extraído. Los textos faltantes quedan vacíos y las cantidades desconocidas en NULL; cero es un valor válido.
- La migración `0009` agrega `ubicacion_aproximada` (NULL: precisión desconocida; True: la fuente publica un área) y `radio_ubicacion_m` opcional. Se conserva la precisión de la fuente: un círculo no representa una dirección exacta ni garantiza que la propiedad esté en su centro.
- Una restricción única por `(fuente, identificador_fuente)` y persistencia común con `update_or_create` en `propiedades/ingesta.py`.
- Un scraper Brega en `propiedades/scraping/brega.py` que consulta `/Venta` y `/Alquiler` con Requests y Beautiful Soup, recorre páginas con `p`, evita identificadores repetidos y termina ante un lote vacío o sin identificadores nuevos. Tiene un límite de seguridad de 50 páginas, timeout de 15 segundos y pausas de 0,5 segundos; no tiene reintentos implementados.
- Normalización básica de precios, monedas, tipos y operaciones en `propiedades/scraping/normalizacion.py`. El contrato `PublicacionNormalizada` y el protocolo `AdaptadorFuente` están en `propiedades/scraping/contratos.py`; `AdaptadorBrega` traduce la extracción existente a ese contrato.
- El flujo común `importar_fuente` en `propiedades/ingesta.py` consolida operaciones/precios, consulta una ficha completa por aviso en cada ingesta, gestiona coordenadas y persiste. Las fuentes se registran en `propiedades/scraping/fuentes.py`. Solo está registrada Brega. Ya no se omiten fichas por tener dormitorios verificados: también deben refrescarse descripción y características. Si falla la ficha se conservan los detalles guardados; la ausencia de un dato nuevo (None) tampoco borra el anterior. La detección de datos retirados de una ficha queda pendiente.
- `python manage.py importar_propiedades brega` ejecuta el flujo común. `python manage.py importar_brega` se conserva como alias compatible.
- Geocodificación experimental con geopy/Nominatim en `propiedades/scraping/geocoding.py`, limitada a direcciones con ciudad explícita y con separación mínima de 1,5 segundos entre consultas por proceso. Sin ciudad no se consulta el proveedor: no se supone Rafaela ni se deducen localidades por nombres de calles.
- Si cambia dirección, ciudad, provincia o zona, se invalidan ambas coordenadas anteriores y se intenta resolver la nueva ubicación solo si hay ciudad explícita. Si no se encuentra o el proveedor falla, quedan vacías; los errores del proveedor se registran. Un par incompleto también se invalida y se intenta completar. Un par completo se reutiliza si la ubicación no cambió, incluso si alguna coordenada vale cero.
- Brega extrae el título Open Graph, descripción de `#prop-desc` (limpiando HTML escapado, con respaldo Open Graph), características de `.ficha_ul`, cantidades de `.ficha_detalle_item`/`#lista_informacion_basica` y ubicación textual. El rótulo `Ubicación` puede ser localidad o barrio: se guarda como `zona`, nunca se transforma automáticamente en ciudad. Ciudad/provincia solo se extraen si aparecen con esos rótulos explícitos.
- Brega ahora extrae también el par latitud/longitud y radio del `L.circle([latitud, longitud], radio, {...})` publicado dentro de `#ficha_mapa`, sin ejecutar JavaScript ni consultar servicios adicionales. En tres fichas reales se verificaron círculos distintos con radio de 400 metros. No se extrae el centro de `setView`, ni mapas del footer, ni se fija 400 como valor universal. Formatos no reconocidos quedan sin coordenadas nuevas; valores fuera de rango, radios inválidos o varios círculos distintos se descartan con advertencia.
- Las coordenadas válidas de la fuente tienen prioridad sobre la geocodificación, incluso sin ciudad; se renuevan en cada ingesta y conservan precisión/radio. Sin coordenadas de fuente se mantiene la lógica de invalidación y geocodificación con ciudad explícita. No se mezclan pares parciales con datos anteriores. Al invalidar coordenadas también se borra precisión/radio. Las coordenadas históricas conservadas no se consideran auditadas.
- Geocodificación inversa opcional en `propiedades/enriquecimiento.py`, activada únicamente con `--completar-ubicacion`. Completa ciudad/provincia faltantes, sin modificar coordenadas, zona ni precisión. La migración `0010` agrega `ciudad_origen`, `provincia_origen` y el modelo `ConsultaLocalidad` para caché persistente por par de coordenadas. Origen `fuente` identifica valores explícitos recibidos en la ingesta; `nominatim_inversa` identifica nombres inferidos. El origen vacío de datos históricos significa procedencia no registrada, no una inferencia confirmada.
- La caché guarda respuestas resueltas, vacías, ambiguas y errores. Las respuestas no fallidas se reutilizan sin nueva consulta; los errores temporales se reintentan después de 24 horas. Cambiar las coordenadas selecciona otra entrada de caché y borra solo nombres inferidos del punto anterior, incluso sin activar el enriquecimiento. Los datos explícitos siempre tienen prioridad y los nombres inferidos no se usan para volver a geocodificar una dirección.
- El enriquecimiento acepta `city`/`town`/`village` y `state` con país `ar`; no confunde barrio o departamento con ciudad. Rechaza localidades contradictorias, estructuras inválidas y resultados incompatibles con valores ya conocidos. Una respuesta parcial puede completar solo uno de los campos. Estos controles no detectan si el círculo aproximado cruza límites administrativos: los nombres siguen siendo inferencias, no datos garantizados. No se calculan límites ni distancias en Python.
- Las consultas directas e inversas a Nominatim comparten un limitador de 1,5 segundos, sin reintentos inmediatos. Ejecutar un solo job que utilice el proveedor público a la vez; la limitación es por proceso y no coordina procesos distintos. Fallos del proveedor se registran y permiten continuar guardando publicaciones.
- Una vista y plantilla en `/propiedades/` que consultan datos guardados, filtran por venta o alquiler y enlazan al aviso original. El filtro predeterminado es alquiler.

La conexión y las migraciones hasta `0010` se verificaron en Supabase/PostgreSQL. La revisión de solo lectura del 8 de octubre de 2026 encontró 173 publicaciones: 172 con coordenadas completas, 170 con `ciudad_origen=nominatim_inversa`, 172 con `provincia_origen=nominatim_inversa` y 164 entradas de caché. Estos conteos son una instantánea, no valores esperados fijos ni una validación individual de precisión. Se comprobó además el proveedor con tres puntos: Bella Italia devolvió Bella Italia/Santa Fe; Barrio 30 de Octubre devolvió Rafaela/Santa Fe; Lehmann devolvió Municipio de Lehmann/Santa Fe.

No hay integración PostGIS o Elasticsearch; tampoco scrapers de Avantix u otra tercera fuente, un adaptador común por plataforma, búsqueda textual, filtros de precio/tipo/geográficos, API de búsqueda ni mapa. Las 48 pruebas automáticas pasaron usando SQLite y servicios simulados. Para ejecutarlas en PowerShell sin usar Supabase:

```powershell
$env:DB_ENGINE = "sqlite"
.\.venv\Scripts\python.exe -X utf8 manage.py test propiedades config
Remove-Item Env:DB_ENGINE
```

El ejemplo supone que no había una variable de sistema `DB_ENGINE` previamente definida en esa terminal; si la había, guardar y restaurar su valor. La selección temporal de SQLite evita crear una base de pruebas en Supabase. También se verificaron ausencia de cambios de modelo sin migración (`makemigrations --check --dry-run`) y dependencias instaladas (`pip check`).

## Ejecutar la ingesta local

Para instalar dependencias, configurar `.env`, conectar Supabase y conservar datos de SQLite, seguir [docs/base_de_datos.md](docs/base_de_datos.md). La selección es `DB_ENGINE=sqlite` (predeterminado) o `DB_ENGINE=postgresql` con `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD` y `PGSSLMODE`. PostgreSQL usa TLS por defecto. No se guardan credenciales en el código ni se requiere una API key de Supabase. Ejecutar migraciones antes de la ingesta. La exportación/importación documentada está destinada a un PostgreSQL vacío, no a mezclar bases con publicaciones existentes. En Windows usar `python.exe -X utf8` para `dumpdata`/`loaddata` y conservar correctamente los acentos.

Desde la raíz del proyecto, en PowerShell, usar el Python del entorno virtual y agregar al final el nombre de la fuente que se quiere scrapear:

```powershell
.\.venv\Scripts\python.exe manage.py importar_propiedades <fuente>
```

Reemplazar `<fuente>` por el nombre registrado de la inmobiliaria, sin los signos `<` y `>`; no se debe colocar una URL. Actualmente solo está disponible `brega`:

```powershell
.\.venv\Scripts\python.exe manage.py importar_propiedades brega
```

El nombre de la fuente es obligatorio. Para incorporar otra página, primero debe implementarse su adaptador y registrarse en `propiedades/scraping/fuentes.py`; escribir un nombre nuevo en el comando no agrega soporte automáticamente. La ingesta consulta los servicios externos y crea o actualiza publicaciones en la base configurada.

Para completar opcionalmente ciudad/provincia faltantes desde las coordenadas, usando la caché persistente:

```powershell
.\.venv\Scripts\python.exe manage.py importar_propiedades brega --completar-ubicacion
```

El alias `importar_brega` también admite `--completar-ubicacion`. Sin esa opción no se hacen consultas inversas nuevas. El resumen incluye `Localidades completadas`, que cuenta avisos donde se completó al menos un campo, incluso desde caché. Los cambios de coordenadas siempre invalidan nombres inferidos anteriores.

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

Implementación común actual: cada adaptador expone `nombre`, `operaciones`, `extraer(operacion)` y `extraer_detalles(url)`. `extraer` devuelve objetos `PublicacionNormalizada`, uno por aviso y operación, con precio/moneda de ese listado. `extraer_detalles` devuelve `DetallesPropiedad` con datos opcionales de la ficha; los errores de lectura deben propagarse. El núcleo consolida por identificador dentro de cada fuente y mantiene precios separados. Para incorporar una fuente, implementar ese contrato y registrarla, sin copiar el importador. No se creó un adaptador Tokko compartido ni se verificó Avantix.

Ciudad/provincia y zona se persisten cuando se aportan, sin inferirlas por el foco del proyecto. La indexación no está implementada: la persistencia está concentrada en `guardar_publicacion`; la integración futura deberá indexar después de guardar y resolver recuperación/reconstrucción. La política de publicaciones retiradas sigue pendiente.

Los datos a contemplar, según lo que realmente proporcione cada fuente, incluyen:

- Identificador de la publicación y la inmobiliaria de origen.
- Tipo de propiedad y operación: venta, alquiler o ambas cuando corresponda.
- Precio y moneda por operación; conservar los campos separados existentes cuando una publicación ofrezca venta y alquiler.
- Dirección, ciudad, barrio o zona.
- Dormitorios, ambientes y superficie con su unidad.
- Título, descripción y características disponibles.
- URL original e imágenes.
- Latitud, longitud y una representación compatible con PostGIS cuando existan coordenadas.

El contrato común incluye latitud/longitud opcionales, indicación de ubicación aproximada y radio publicado en metros. La extracción y validación numérica no realizan consultas geográficas. Los futuros filtros PostGIS deben contemplar la incertidumbre de las áreas publicadas; no tratar sus centros como ubicaciones exactas.

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

Guardar las coordenadas disponibles en PostgreSQL y utilizarlas mediante una representación espacial de PostGIS. El prototipo incluye geocodificación experimental mediante geopy/Nominatim, únicamente con ciudad explícita. Su uso definitivo, validación de precisión y extracción de localidad siguen pendientes. No inventar ubicaciones para datos ausentes. No se implementaron filtros espaciales fuera de PostGIS.

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

1. Ampliar el contrato y flujo de ingesta común ya implementados con los datos adicionales que aporten las fuentes, manteniendo separada la extracción específica.
2. Completar la primera inmobiliaria de punta a punta: extracción, modelo normalizado, persistencia en Supabase/PostgreSQL e indexación en Elasticsearch.
3. Verificar altas, actualizaciones, ausencia de duplicados por fuente y reconstrucción del índice desde PostgreSQL; probar búsqueda textual y ranking.
4. Incorporar la segunda inmobiliaria y después la tercera, reutilizando el flujo común y verificando los datos de cada fuente.
5. Integrar PostGIS, preparar el almacenamiento de coordenadas y las consultas por radio/área con índices espaciales.
6. Preparar la búsqueda del backend que combine texto, filtros estructurados y filtros geográficos. Desarrollar frontend y mapa posteriormente.

Las prioridades inmediatas son arquitectura de scrapers, modelo común, persistencia, job de ingesta, integración/indexación/búsqueda con Elasticsearch y soporte geográfico con PostGIS. El plan describe trabajo pendiente, no funcionalidades ya terminadas.

## Decisiones de implementación pendientes

- Tercera inmobiliaria y compatibilidad del adaptador compartido con Avantix.
- Traslado de datos locales si se desea conservar información que no esté en la ingesta de Supabase; representación espacial en PostGIS, tratamiento de ubicaciones aproximadas en búsquedas y futuras ampliaciones del esquema común. El proyecto Supabase, conexión y migraciones hasta `0010` están verificados.
- Frecuencia y ejecución programada de la ingesta; política de publicaciones retiradas y recuperación de errores de indexación.
- Configuración de Elasticsearch, coordinación de consultas, orden y paginación.
- Validación del geocodificador experimental, extracción explícita de ciudad/provincia, auditoría de coordenadas históricas y tratamiento definitivo de ubicaciones ausentes.
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
