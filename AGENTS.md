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
| Elasticsearch / Elastic Cloud | Elasticsearch es el índice especializado exclusivamente en búsqueda de texto completo y ranking por relevancia; se alojará en Elastic Cloud. No reemplaza PostgreSQL ni realiza filtros geográficos. |
| Render | Django está desplegado y conectado a Supabase y Elastic Cloud. `/propiedades/` permite probar búsqueda textual por relevancia mediante un formulario simple. |
| GitHub Actions | Ejecuta el comando general de ingesta y reconstruye Elasticsearch todos los lunes a las 00:00 de Argentina; también admite ejecución manual. Secrets, concurrencia y primera ejecución están verificados. |
| Frontend | Tecnología e implementación pendientes, incluida la interfaz de mapa. |

Supabase/PostgreSQL, PostGIS y Elasticsearch son decisiones del stack objetivo. La conexión PostgreSQL está implementada mediante psycopg y variables de entorno, y se verificaron las migraciones hasta `0011` en Supabase. En la revisión del 8 de octubre de 2026 se comprobaron 173 publicaciones, incluyendo datos guardados por el enriquecimiento inverso. No se realizó un traslado automático de SQLite. PostGIS y la búsqueda con Elasticsearch están desplegados. La ingesta programada reconstruye el índice completo después de persistir; la actualización incremental por publicación sigue pendiente. Sin configuración se utiliza SQLite para desarrollo local. Guardar `.env` como UTF-8 sin BOM para que se reconozca correctamente la primera variable.

### Entorno objetivo y despliegue

Entregar un sitio accesible desde una URL pública. Utilizar Django en Render, PostgreSQL y PostGIS en Supabase, Elasticsearch en Elastic Cloud y GitHub Actions para la ingesta automática. Las búsquedas del sitio desplegado funcionan sin depender de una computadora del equipo. Conservar la ejecución local para desarrollo y pruebas. El 11 de octubre de 2026 el equipo confirmó la búsqueda textual pública, el formulario mínimo y una ejecución manual exitosa del workflow completo. PostGIS ya está desplegado. Ver [estado y configuración del despliegue](docs/despliegue.md).

#### Elasticsearch en Elastic Cloud

Utilizar la prueba gratuita de 14 días sin tarjeta para la entrega, comprobando que su vigencia cubra la evaluación antes de activarla. No asumir alojamiento gratuito permanente; la continuidad después de la prueba sigue por resolver. Mantener las credenciales en variables de entorno y conectar Elasticsearch desde el backend y el job, nunca directamente desde el frontend. La creación del servicio, conexión, reconstrucción del índice, búsqueda textual pública y reconstrucción automática posterior a la ingesta están implementadas. El índice puede reconstruirse desde las propiedades guardadas en Supabase. Ver [prueba de Elastic Cloud](https://www.elastic.co/cloud/elasticsearch-service/signup).

#### Ingesta automática con GitHub Actions

El workflow `.github/workflows/ingesta.yml` obtiene el código, instala dependencias, comprueba Elasticsearch, ejecuta `python manage.py importar_propiedades` para todas las fuentes registradas y finalmente ejecuta `python manage.py reconstruir_indice`. Usa Ubuntu 24.04, Python 3.14 y las acciones oficiales basadas en Node 24. Está programado los lunes a las 00:00 de Argentina (`03:00 UTC`) y admite `workflow_dispatch`.

Las credenciales se guardan como Actions Secrets y no en el repositorio. `concurrency` impide dos ejecuciones simultáneas del mismo workflow; también deben evitarse ingestas locales concurrentes contra los mismos servicios. El 11 de octubre de 2026 se verificó una ejecución manual exitosa. Si falla la reconstrucción, PostgreSQL conserva la ingesta y el alias anterior continúa activo; la recuperación actual consiste en corregir la causa y reejecutar el workflow. La recuperación incremental sigue pendiente.

Los runners estándar son gratuitos en repositorios públicos. En repositorios privados, GitHub Free incluye 2.000 minutos mensuales compartidos entre los workflows y repositorios privados de la cuenta propietaria, no por integrante ni por repositorio. Verificar la visibilidad y cuota disponible antes de configurar la programación: el 9 de octubre de 2026 se verificó que este repositorio es público. Ver [facturación de Actions](https://docs.github.com/en/billing/concepts/product-billing/github-actions).

No hace falta contratar un Render Cron Job para esta arquitectura. Esa alternativa tiene un mínimo mensual de USD 1 por servicio, independiente de las solicitudes al servicio web. Ver [Render Cron Jobs](https://render.com/docs/cronjobs).

#### Solicitudes periódicas al servicio web

Preparar solicitudes periódicas desde un servicio externo a una ruta ligera de Django para reducir el reposo por inactividad. Render gratuito entra en reposo tras 15 minutos sin tráfico entrante; los pings no eliminan sus límites ni garantizan disponibilidad continua. Una visita, un filtro o un ping no deben disparar scraping ni indexación. La ruta no debe consultar Supabase o Elasticsearch solo para mantener activo el servicio. Ver [Render Free](https://render.com/docs/free).

La ruta `/health/` está desplegada. El equipo creó el job en [cron-job.org](https://cron-job.org/en/); falta comprobar una ejecución programada HTTP 200 en su historial y el intervalo efectivamente guardado (se propuso GET cada diez minutos). No presentar la creación del job como prueba de ejecución. Vercel fue una opción consultada, no adoptada.

## Estado real del repositorio

### Integración local de Avantix — 11 de octubre de 2026

Avantix está implementada y registrada como segunda fuente mediante `AdaptadorAvantix`. Brega y Avantix reutilizan parsers comunes de Tokko para listados y campos generales de ficha; la configuración de URLs y la interpretación geográfica permanecen separadas por fuente. El comando específico es `python manage.py importar_propiedades avantix` y el comando sin argumentos recorre ambas fuentes, por lo que el workflow existente no requiere cambios ni Secrets adicionales cuando este código se despliegue.

La validación pública de solo lectura obtuvo HTTP 200 en `/Venta` y `/Alquiler`, con 20 tarjetas completas en el primer lote de cada operación. `?p=2` devolvió 20 avisos de venta y 15 de alquiler, y `?p=99` terminó sin tarjetas mediante `--NoMoreProperties--`. Una ficha real confirmó `#prop-desc`, `.ficha_detalle_item`, `#lista_informacion_basica` y `.ficha_ul`; el parser obtuvo título, descripción, zona, ambientes, dormitorios y baños.

El mapa de Avantix observado contiene un marcador de Google Maps con coordenadas, pero no publica un círculo ni un radio. Por decisión confirmada del equipo el 11 de octubre, la integración trata ese marcador como una ubicación exacta: lee únicamente `q=latitud,longitud` del iframe de Google Maps dentro de `#ficha_mapa`, valida el par y guarda `ubicacion_aproximada=False` con `radio_ubicacion_m=NULL`. Formatos desconocidos, valores inválidos y varios puntos distintos se descartan. No se reutiliza el lector de círculos de Brega. Esta clasificación como exacta es una decisión del equipo; la fuente no declara explícitamente esa precisión.

Una ingesta real controlada contra la base efímera de pruebas de Django procesó 275 publicaciones únicas: 250 de venta y 35 de alquiler, con superposición entre operaciones. Verificó 274 fichas y continuó correctamente ante un error de detalle; el resumen temporal no conservó la URL ni la causa concreta, por lo que debe revisarse en los logs de la próxima ejecución. Los otros 274 registros obtuvieron título, descripción y dormitorios verificados. Esa ingesta se hizo antes de habilitar la extracción del marcador, por lo que no recibió coordenadas y no mide cuántas fichas actuales las publican. Después se verificó una ficha pública real: el parser obtuvo `-31.250540799413834, -61.49395149727678`, precisión exacta según la decisión del equipo y radio nulo. La base efímera se destruyó al finalizar: no se modificaron `db.sqlite3`, Supabase ni Elasticsearch. Avantix todavía no está desplegada ni incorporada a los datos públicos.

Validación automática posterior: 87 pruebas descubiertas, 86 aprobadas y una integración PostGIS omitida al usar SQLite. La suite incluye el iframe realista de Avantix, punto cero, formatos inválidos o ambiguos y persistencia de `False` sin geocodificación. `makemigrations --check --dry-run` no detectó cambios y `pip check` no encontró dependencias rotas. El comando general procesa las fuentes en orden alfabético (`avantix`, luego `brega`). Los errores de una ficha se aíslan, pero un fallo de listado o paginación de cualquier fuente todavía aborta el comando general y evita la reconstrucción posterior del índice. El equipo acordó implementar más adelante aislamiento por fuente: registrar el fallo, continuar con las fuentes restantes y finalizar informando cuáles fallaron.

### Automatización y búsqueda pública — 11 de octubre de 2026

El equipo cargó los Repository Secrets y comprobó manualmente el workflow completo de GitHub Actions. El job comprueba Elastic Cloud antes de escribir, ejecuta el comando general sin argumentos y reconstruye el índice desde Supabase al finalizar. La primera ejecución informada terminó correctamente en 3 minutos y 53 segundos. El workflow usa `concurrency`, tiene un límite de 60 minutos y queda programado semanalmente para los lunes a las 00:00 de Argentina.

Elasticsearch quedó configurado en Render y el equipo confirmó que la búsqueda pública funciona. `/propiedades/` incorpora un cuadro de texto mínimo para enviar `q`; conserva la operación seleccionada y muestra los resultados en el orden de relevancia recibido desde Elasticsearch. Sigue sin existir mapa, paginación pública ni frontend definitivo.

La automatización actual hace una reconstrucción completa después de cada ingesta, no indexación incremental después de cada propiedad. Ante un fallo durante la reconstrucción, los datos nuevos permanecen en PostgreSQL y el alias anterior de Elasticsearch continúa atendiendo búsquedas. Siguen pendientes la recuperación incremental, una política de limpieza de versiones físicas anteriores y la política de publicaciones retiradas.

La siguiente feature en desarrollo es Avantix como segunda fuente. Antes de implementarla se verificó mediante solicitudes públicas que `/Venta` y `/Alquiler` usan tarjetas Tokko con `li[prop-id]`, `.prop-desc-tipo-ub`, `.prop-desc-dir` y `.prop-valor-nro`; `?p=2` devuelve lotes parciales de 20 avisos y las páginas posteriores terminan con `--NoMoreProperties--`. Las fichas comparten `#prop-desc`, `.ficha_detalle_item`, `#lista_informacion_basica` y `.ficha_ul`. A diferencia de Brega, el mapa observado usa un punto de Google Maps sin publicar un radio ni declarar precisión. La precaución inicial de no persistirlo fue reemplazada por la decisión confirmada del equipo de tratarlo como exacto.

### Elasticsearch y despliegue — 10 de octubre de 2026

El equipo pidió dejar esta etapa documentada para que el compañero propietario de la cuenta de Render publique el código y configure sus variables. No desplegar ni hacer push en su nombre: el usuario hará el push. Seguir la [guía de continuidad](docs/continuidad.md), que distingue `.env` local de Environment en Render y lista las pruebas públicas pendientes.

El equipo confirmó el despliegue de health, plantilla y PostGIS. Se verificaron públicamente `/health/` (200), filtros espaciales (200 y 400 ante entrada inválida) y avisos de precisión. El equipo creó un job de ping en cron-job.org; falta comprobar su historial de ejecución, no asumir que ya funciona regularmente.

Elasticsearch está integrado localmente con el cliente oficial Python 9.5.1 y un proyecto Elastic Cloud que responde como 9.6.0. Las credenciales están en `.env`, sin versionar. El equipo indicó evaluación el martes 13 de octubre; la prueba de 14 días cubre esa fecha, pero falta registrar su vencimiento exacto en el panel.

`comprobar_elasticsearch` valida conexión; `reconstruir_indice` crea una versión completa desde la base configurada y cambia atómicamente el alias `propiedades`, conservando versiones anteriores y rechazando por defecto una base vacía. Se cargaron 173 documentos desde Supabase sin scraping ni cambios de publicaciones. `buscar_propiedades` prueba consultas con score. El analizador es `spanish`, ranking BM25, texto agregado y pesos iniciales por campo. No se indexan precios ni coordenadas para filtrar.

`/propiedades/?q=...` busca texto y combina IDs ordenados con los filtros PostgreSQL/PostGIS, conservando relevancia. Sin texto no consulta Elasticsearch; ante fallos de búsqueda responde 503, sin reemplazar por LIKE. Se usa PIT/search_after para leer todas las coincidencias. El 11 de octubre se agregó un formulario mínimo para `q`; no hay mapa ni paginación pública. Los cambios de operación conservan los parámetros de búsqueda. Pruebas reales: 16 coincidencias para `departamento con cochera` (5 alquiler/11 venta), 2 para `cochera y quincho` y ranking verificado con un índice temporal luego eliminado.

Esta integración Elasticsearch todavía debe configurarse y desplegarse en Render. La indexación automática tras cada guardado no se implementó en esta etapa: después de una ingesta se debe reconstruir manualmente. Recuperación incremental, concurrencia de reconstrucción/ingesta y política de avisos retirados siguen pendientes. Ver [configuración, comandos, límites y validación](docs/elasticsearch.md). El resto de las revisiones fechadas conserva el estado histórico de cada etapa.

Validación final: 72 pruebas descubiertas, 71 aprobadas y una PostGIS omitida en SQLite; sin cambios de modelo pendientes ni dependencias incompatibles. Dos reconstrucciones reales dejaron 173 documentos, un único índice activo por alias y dos versiones físicas conservadas; los IDs coinciden exactamente con Supabase. No se modificaron publicaciones ni se ejecutó ingesta. `.env` sigue ignorado por Git. No se publicó ni desplegó el código de esta etapa.

### Revisión y correcciones del 9 de octubre de 2026

Se verificó `https://observatorio-grupo7.onrender.com/propiedades/`: HTTP 200 para alquiler (40 avisos) y venta (136), estáticos accesibles y redirección HTTP a HTTPS. Supabase conserva 173 publicaciones de Brega sin duplicados, 172 pares completos y 164 entradas de caché. El repositorio es público. Son conteos de esa revisión; ver [informe inicial](docs/revision_2026-10-09.md).

Después, por solicitud del equipo, se implementó `/health/` con GET/HEAD, sin base ni servicios externos, y se corrigió la visualización de valores cero. Con DEBUG=False se exige HTTPS, cookies seguras y HSTS de una hora, sin subdominios ni preload; estas dos recomendaciones de `check --deploy` siguen visibles. El correo está explícitamente deshabilitado en producción mediante un backend que falla ante un intento de envío; no se configuró un proveedor. Se eliminó la definición duplicada de MIDDLEWARE.

Se aplicó `0011_ubicacion_postgis` a Supabase: PostGIS 3.3.7 en `extensions`, columna generada `ubicacion geography(Point,4326)` y dos índices GiST (distancia y área). PostgreSQL deriva el punto de longitud/latitud en cada escritura, sin añadir un campo GeoDjango ni requerir GEOS/GDAL. SQLite omite los objetos espaciales y rechaza filtros geográficos con 503. El backend incorpora filtros GET por radio en metros y rectángulo con bordes incluidos, exclusivamente mediante PostGIS. Por defecto solo usa ubicaciones explícitamente exactas; `incluir_aproximadas=1` incluye centros aproximados y precisión desconocida con advertencia. No se interpreta el círculo como ubicación exacta ni se implementó intersección de áreas de incertidumbre. No hay polígonos arbitrarios todavía. Ver [contrato y límites](docs/postgis.md).

Suite de esa etapa: 55 pruebas en SQLite, 54 aprobadas y una integración PostGIS omitida. Se comprobaron radio, metros, bordes, precisión, nulos, actualizaciones y respuestas HTTP contra PostGIS real en una tabla temporal revertida, conservando las 173 publicaciones. No se ejecutó scraping. Esta descripción registra la preparación del 9 de octubre: el despliegue de esas correcciones se comprobó el 10 y el job de cron-job.org ya fue creado, con historial pendiente de validar. La suite posterior de Elasticsearch descubrió 72 pruebas, 71 aprobadas y una omitida en SQLite.

Al actualizar este contexto, el código contiene:

- Un proyecto Django en `config/` y la aplicación `propiedades/`. `config/database.py` permite SQLite o PostgreSQL según `DB_ENGINE`; `config/settings.py` carga `.env` sin sobrescribir variables del sistema. `.env.example` documenta los valores; no contiene credenciales reales.
- Configuración para el despliegue básico: `DJANGO_SECRET_KEY` obligatorio desde el entorno, `DJANGO_DEBUG` con valor predeterminado False y `DJANGO_ALLOWED_HOSTS` como lista separada por comas. El dominio recibido en `RENDER_EXTERNAL_HOSTNAME` se agrega automáticamente; en Render se configura el encabezado del proxy HTTPS y cookies de sesión/CSRF seguras.
- Gunicorn `26.2.0`, WhiteNoise `6.12.0`, archivos estáticos en `staticfiles/` con almacenamiento comprimido y manifiesto, y `.python-version` con `3.14`. `.env` y `staticfiles/` están excluidos de Git. Comandos de construcción y arranque documentados en [docs/despliegue.md](docs/despliegue.md).
- El modelo `Propiedad`, con fuente, identificador de origen, dirección, tipo, dormitorios y su estado de verificación, operaciones de venta/alquiler, precios y monedas separados por operación, URL original, fecha de actualización y latitud/longitud opcionales. PostgreSQL deriva de estos FloatField la columna espacial generada `ubicacion`; SQLite conserva solo los campos portátiles.
- Ampliación acotada del modelo en la migración `0008`: título, descripción, características como texto, ciudad, provincia, zona, ambientes y baños. Dormitorios ya existía. No se agregan columnas para cada amenidad: cochera, parrilla y otras características se conservan en el texto extraído. Los textos faltantes quedan vacíos y las cantidades desconocidas en NULL; cero es un valor válido.
- La migración `0009` agrega `ubicacion_aproximada` (NULL: precisión desconocida; False: punto tratado como exacto; True: la fuente publica un área) y `radio_ubicacion_m` opcional. Un círculo no representa una dirección exacta ni garantiza que la propiedad esté en su centro. Avantix queda como False por decisión del equipo aunque la fuente no declare explícitamente la precisión de su marcador.
- Una restricción única por `(fuente, identificador_fuente)` y persistencia común con `update_or_create` en `propiedades/ingesta.py`.
- Un scraper Brega en `propiedades/scraping/brega.py` que consulta `/Venta` y `/Alquiler` con Requests y Beautiful Soup, recorre páginas con `p`, evita identificadores repetidos y termina ante un lote vacío o sin identificadores nuevos. Tiene un límite de seguridad de 50 páginas, timeout de 15 segundos y pausas de 0,5 segundos; no tiene reintentos implementados.
- Normalización básica de precios, monedas, tipos y operaciones en `propiedades/scraping/normalizacion.py`. El contrato `PublicacionNormalizada` y el protocolo `AdaptadorFuente` están en `propiedades/scraping/contratos.py`; `AdaptadorBrega` traduce la extracción existente a ese contrato.
- El flujo común `importar_fuente` en `propiedades/ingesta.py` consolida operaciones/precios, consulta una ficha completa por aviso en cada ingesta, gestiona coordenadas y persiste. Las fuentes se registran en `propiedades/scraping/fuentes.py`; están registradas Brega y Avantix. Ya no se omiten fichas por tener dormitorios verificados: también deben refrescarse descripción y características. Si falla la ficha se conservan los detalles guardados; la ausencia de un dato nuevo (None) tampoco borra el anterior. La detección de datos retirados de una ficha queda pendiente.
- `python manage.py importar_propiedades brega` y `python manage.py importar_propiedades avantix` importan una fuente específica; el mismo comando sin argumentos importa, en orden alfabético, todas las fuentes registradas. `python manage.py importar_brega` se conserva como alias compatible.
- Geocodificación experimental con geopy/Nominatim en `propiedades/scraping/geocoding.py`, limitada a direcciones con ciudad explícita y con separación mínima de 1,5 segundos entre consultas por proceso. Sin ciudad no se consulta el proveedor: no se supone Rafaela ni se deducen localidades por nombres de calles.
- Si cambia dirección, ciudad, provincia o zona, se invalidan ambas coordenadas anteriores y se intenta resolver la nueva ubicación solo si hay ciudad explícita. Si no se encuentra o el proveedor falla, quedan vacías; los errores del proveedor se registran. Un par incompleto también se invalida y se intenta completar. Un par completo se reutiliza si la ubicación no cambió, incluso si alguna coordenada vale cero.
- Brega extrae el título Open Graph, descripción de `#prop-desc` (limpiando HTML escapado, con respaldo Open Graph), características de `.ficha_ul`, cantidades de `.ficha_detalle_item`/`#lista_informacion_basica` y ubicación textual. El rótulo `Ubicación` puede ser localidad o barrio: se guarda como `zona`, nunca se transforma automáticamente en ciudad. Ciudad/provincia solo se extraen si aparecen con esos rótulos explícitos.
- Brega ahora extrae también el par latitud/longitud y radio del `L.circle([latitud, longitud], radio, {...})` publicado dentro de `#ficha_mapa`, sin ejecutar JavaScript ni consultar servicios adicionales. En tres fichas reales se verificaron círculos distintos con radio de 400 metros. No se extrae el centro de `setView`, ni mapas del footer, ni se fija 400 como valor universal. Formatos no reconocidos quedan sin coordenadas nuevas; valores fuera de rango, radios inválidos o varios círculos distintos se descartan con advertencia.
- Avantix extrae únicamente el parámetro `q=latitud,longitud` del iframe de Google Maps contenido en `#ficha_mapa`. Guarda el par como exacto (`ubicacion_aproximada=False`) y sin radio por decisión del equipo. No interpreta marcadores JavaScript, direcciones dentro de `q`, iframes externos al mapa ni varios puntos distintos.
- Las coordenadas válidas de la fuente tienen prioridad sobre la geocodificación, incluso sin ciudad; se renuevan en cada ingesta y conservan precisión/radio. Sin coordenadas de fuente se mantiene la lógica de invalidación y geocodificación con ciudad explícita. No se mezclan pares parciales con datos anteriores. Al invalidar coordenadas también se borra precisión/radio. Las coordenadas históricas conservadas no se consideran auditadas.
- Geocodificación inversa opcional en `propiedades/enriquecimiento.py`, activada únicamente con `--completar-ubicacion`. Completa ciudad/provincia faltantes, sin modificar coordenadas, zona ni precisión. La migración `0010` agrega `ciudad_origen`, `provincia_origen` y el modelo `ConsultaLocalidad` para caché persistente por par de coordenadas. Origen `fuente` identifica valores explícitos recibidos en la ingesta; `nominatim_inversa` identifica nombres inferidos. El origen vacío de datos históricos significa procedencia no registrada, no una inferencia confirmada.
- La caché guarda respuestas resueltas, vacías, ambiguas y errores. Las respuestas no fallidas se reutilizan sin nueva consulta; los errores temporales se reintentan después de 24 horas. Cambiar las coordenadas selecciona otra entrada de caché y borra solo nombres inferidos del punto anterior, incluso sin activar el enriquecimiento. Los datos explícitos siempre tienen prioridad y los nombres inferidos no se usan para volver a geocodificar una dirección.
- El enriquecimiento acepta `city`/`town`/`village` y `state` con país `ar`; no confunde barrio o departamento con ciudad. Rechaza localidades contradictorias, estructuras inválidas y resultados incompatibles con valores ya conocidos. Una respuesta parcial puede completar solo uno de los campos. Estos controles no detectan si el círculo aproximado cruza límites administrativos: los nombres siguen siendo inferencias, no datos garantizados. No se calculan límites ni distancias en Python.
- Las consultas directas e inversas a Nominatim comparten un limitador de 1,5 segundos, sin reintentos inmediatos. Ejecutar un solo job que utilice el proveedor público a la vez; la limitación es por proceso y no coordina procesos distintos. Fallos del proveedor se registran y permiten continuar guardando publicaciones.
- Una vista y plantilla en `/propiedades/` que consultan datos guardados, filtran por venta o alquiler, permiten enviar una búsqueda textual simple y enlazan al aviso original. El filtro predeterminado es alquiler.

La conexión y las migraciones hasta `0011` se verificaron en Supabase/PostgreSQL. La revisión de solo lectura del 8 de octubre de 2026 encontró 173 publicaciones: 172 con coordenadas completas, 170 con `ciudad_origen=nominatim_inversa`, 172 con `provincia_origen=nominatim_inversa` y 164 entradas de caché. Estos conteos son una instantánea, no valores esperados fijos ni una validación individual de precisión. Se comprobó además el proveedor con tres puntos: Bella Italia devolvió Bella Italia/Santa Fe; Barrio 30 de Octubre devolvió Rafaela/Santa Fe; Lehmann devolvió Municipio de Lehmann/Santa Fe.

PostGIS está integrado mediante `0011` y filtros por radio/rectángulo. Elasticsearch, el formulario textual mínimo y GitHub Actions están desplegados y verificados. Avantix está integrada y validada localmente, pero aún no se desplegó ni se cargó en Supabase; todavía no hay una tercera fuente, filtros de precio/tipo, API JSON, paginación pública ni mapa. `/health/` ya está desplegado; el ping externo fue creado y falta verificar su historial. Para ejecutar pruebas en PowerShell sin usar Supabase, configurar antes una `DJANGO_SECRET_KEY` de desarrollo:

```powershell
$env:DB_ENGINE = "sqlite"
.\.venv\Scripts\python.exe -X utf8 manage.py test propiedades config
Remove-Item Env:DB_ENGINE
```

El ejemplo supone que no había una variable de sistema `DB_ENGINE` previamente definida en esa terminal; si la había, guardar y restaurar su valor. La selección temporal de SQLite evita crear una base de pruebas en Supabase. También se verificaron ausencia de cambios de modelo sin migración (`makemigrations --check --dry-run`) y dependencias instaladas (`pip check`).

## Ejecutar la ingesta local

Para instalar dependencias, configurar `.env`, conectar Supabase y conservar datos de SQLite, seguir [docs/base_de_datos.md](docs/base_de_datos.md). La selección es `DB_ENGINE=sqlite` (predeterminado) o `DB_ENGINE=postgresql` con `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD` y `PGSSLMODE`. PostgreSQL usa TLS por defecto. No se guardan credenciales en el código ni se requiere una API key de Supabase. Ejecutar migraciones antes de la ingesta. La exportación/importación documentada está destinada a un PostgreSQL vacío, no a mezclar bases con publicaciones existentes. En Windows usar `python.exe -X utf8` para `dumpdata`/`loaddata` y conservar correctamente los acentos.

Actualmente se scrapean publicaciones de Brega y Avantix. Con el entorno virtual activado, los comandos específicos son `python manage.py importar_propiedades brega` y `python manage.py importar_propiedades avantix`: `importar_propiedades` lleva un guion bajo y la clave de fuente se escribe en minúsculas. Desde la raíz del proyecto, en PowerShell, también se puede usar directamente el Python del entorno virtual:

```powershell
.\.venv\Scripts\python.exe manage.py importar_propiedades brega
.\.venv\Scripts\python.exe manage.py importar_propiedades avantix
```

El nombre de fuente es opcional: si se indica, debe ser una fuente registrada y no una URL; si se omite, el comando importa todas las fuentes registradas en un solo proceso. La forma específica es `python manage.py importar_propiedades <fuente>`, reemplazando `<fuente>` por `brega` o `avantix`, sin los signos `<` y `>`. Escribir otro nombre no agrega soporte automáticamente. Reutilizar el importador y la persistencia existentes.

Para completar opcionalmente ciudad/provincia faltantes desde las coordenadas, usando la caché persistente:

```powershell
.\.venv\Scripts\python.exe manage.py importar_propiedades brega --completar-ubicacion
```

El alias `importar_brega` también admite `--completar-ubicacion`. Sin esa opción no se hacen consultas inversas nuevas. El resumen incluye `Localidades completadas`, que cuenta avisos donde se completó al menos un campo, incluso desde caché. Los cambios de coordenadas siempre invalidan nombres inferidos anteriores.

## Arquitectura y flujos esperados

```text
Job Python en GitHub Actions (semanal y manual)
  ├─ Scraper/adaptador Brega (disponible)
  ├─ Scraper/adaptador Avantix (implementado localmente; pendiente de despliegue)
  └─ Scraper/adaptador inmobiliaria C (pendiente)
                   │
                   ▼
             Normalización común
                   │
                   ▼
     Supabase / PostgreSQL con PostGIS
                   │
                   ▼
    Indexación en Elasticsearch / Elastic Cloud

Frontend futuro + mapa → Django en Render
                           ├─ Elasticsearch: texto y relevancia
                           └─ PostgreSQL + PostGIS: datos y filtros
                        → Respuesta única al frontend
```

El scraping se ejecuta separado de las consultas de los usuarios: una visita, un cambio de filtro o un ping al servicio web no dispara pedidos a los sitios externos. El usuario consulta la última información guardada. GitHub Actions ejecuta semanalmente la ingesta y reconstrucción completa del índice; el comando manual se conserva para desarrollo y recuperación.

Separar scraping, normalización, acceso a base de datos, indexación, búsqueda textual, consultas geográficas y API. Mantener una solución modular y entendible; no crear tres sistemas independientes ni introducir microservicios, colas u otras capas sin necesidad.

El backend Python coordina las consultas y devuelve un único conjunto de resultados. El frontend no debe acceder directamente a Elasticsearch ni a la base de datos.

## Ingesta y modelo normalizado común

Preparar desde el comienzo una estructura común para aproximadamente tres inmobiliarias. Cada fuente tendrá su scraper/adaptador y configuración; todos deberán producir el mismo modelo normalizado. Se puede compartir un adaptador entre fuentes de la misma plataforma cuando se compruebe su compatibilidad. La lógica específica de cada sitio debe quedar separada de la persistencia, normalización e indexación comunes.

Implementación común actual: cada adaptador expone `nombre`, `operaciones`, `extraer(operacion)` y `extraer_detalles(url)`. `extraer` devuelve objetos `PublicacionNormalizada`, uno por aviso y operación, con precio/moneda de ese listado. `extraer_detalles` devuelve `DetallesPropiedad` con datos opcionales de la ficha; los errores de lectura deben propagarse. El núcleo consolida por identificador dentro de cada fuente y mantiene precios separados. Para incorporar una fuente, implementar ese contrato y registrarla, sin copiar el importador. Brega y Avantix reutilizan los parsers Tokko de listado y ficha; cada módulo conserva URLs, paginación y cualquier interpretación geográfica específica. Avantix interpreta el punto verificado de Google Maps como exacto por decisión del equipo y lo deja sin radio.

Ciudad/provincia y zona se persisten cuando se aportan, sin inferirlas por el foco del proyecto. La reconstrucción completa del índice desde PostgreSQL está implementada y GitHub Actions la ejecuta tras la ingesta; la persistencia sigue concentrada en `guardar_publicacion`. La indexación incremental después de guardar y su recuperación específica siguen pendientes. La política de publicaciones retiradas sigue pendiente.

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

Brega y Avantix tienen scrapers registrados en el repositorio; Avantix está validada localmente y pendiente de despliegue. La tercera fuente todavía no está elegida; se mantiene la propuesta de incorporar otra plataforma para demostrar la extensión con un adaptador distinto.

- Brega: https://www.bregainmobiliaria.ar
- Avantix: https://www.avantix.ar

La exploración mediante solicitudes directas confirmó en ambos sitios un patrón compatible con Tokko: elementos `li[prop-id]`, clases `.prop-desc-dir`, `.prop-desc-tipo-ub` y `.prop-valor-nro`, un primer lote en el HTML y carga adicional mediante `?p=2`, con lotes de 20 en Avantix y marcador `--NoMoreProperties--` al finalizar.

Las fichas Avantix verificadas también comparten `.ficha_detalle_item`, `#lista_informacion_basica`, `.ficha_ul` y `#prop-desc`. El código reutiliza esos parsers sin mezclar la geografía: Brega publica un `L.circle` con radio y Avantix expone un punto en Google Maps que el equipo decidió clasificar como exacto y sin radio. No fijar una cantidad universal de páginas ni asumir que todos los sitios Tokko son idénticos.

Compartir la extracción Tokko verificada de listados, paginación y campos comunes de ficha. Mantener en cada fuente la configuración de nombre, URL base, URLs de búsqueda y cualquier extracción geográfica cuya semántica difiera.

## Plan incremental acordado

1. Ampliar el contrato y flujo de ingesta común ya implementados con los datos adicionales que aporten las fuentes, manteniendo separada la extracción específica.
2. Completar la primera inmobiliaria de punta a punta: extracción, modelo normalizado, persistencia en Supabase/PostgreSQL e indexación en Elasticsearch.
3. Verificar altas, actualizaciones, ausencia de duplicados por fuente y reconstrucción del índice desde PostgreSQL; probar búsqueda textual y ranking.
4. Incorporar la segunda inmobiliaria y después la tercera, reutilizando el flujo común y verificando los datos de cada fuente.
5. PostGIS básico implementado y desplegado: almacenamiento generado, radio y rectángulo con índices GiST. Falta ampliar a polígonos y definir el tratamiento de áreas de incertidumbre.
6. Preparar la búsqueda del backend que combine texto, filtros estructurados y filtros geográficos. Desarrollar frontend y mapa posteriormente.

Las prioridades inmediatas son arquitectura de scrapers, modelo común, persistencia, job de ingesta, integración/indexación/búsqueda con Elasticsearch y soporte geográfico con PostGIS. El plan conserva las etapas originales; el soporte PostGIS básico ya se implementó por solicitud posterior del equipo. Las demás features indicadas como pendientes no están terminadas.

### Avance del despliegue y siguiente paso

El despliegue básico, health, PostGIS, Elasticsearch público, el formulario textual mínimo y GitHub Actions ya están comprobados. Avantix reutiliza la extracción Tokko verificada y persiste el punto validado de su mapa como exacto y sin radio por decisión del equipo. Falta desplegar esta integración, ejecutar la ingesta controlada contra Supabase y validar resultados públicos antes de considerarla operativa en producción.

1. Parsers comunes de listado y ficha, y recorrido común de paginación extraídos sin alterar el comportamiento verificado de Brega; cada fuente conserva sus URLs, solicitudes y configuración.
2. `AdaptadorAvantix` implementado y registrado, con pruebas de listados, operaciones dobles, precios, detalles, registro y terminación/límite de páginas.
3. Extracción pública e ingesta efímera local validadas; falta ejecutar una ingesta controlada contra Supabase y reconstruir Elasticsearch mediante el workflow.
4. Falta comprobar en el despliegue identidad por fuente, ausencia de duplicados, resultados públicos de ambas inmobiliarias y comportamiento operativo ante errores parciales.

El primer despliegue comprueba la infraestructura; no completa las features pendientes ni requiere definir una nueva interfaz.

## Decisiones de implementación pendientes

- Tolerancia a fallos por fuente en la ingesta general: si falla por completo el listado o la paginación de una fuente, registrar el error, continuar con las demás y comunicar al final las fuentes fallidas. Todavía no está implementada; definir también el estado de salida apropiado para que GitHub Actions avise sin descartar el trabajo exitoso.
- Tercera inmobiliaria; Avantix ya está implementada y validada localmente, pendiente de despliegue y validación contra Supabase/Elasticsearch.
- Traslado de datos locales si se desea conservar información que no esté en la ingesta de Supabase; política de intersección de áreas de incertidumbre, polígonos arbitrarios y futuras ampliaciones del esquema común; la representación espacial y los filtros básicos ya están implementados. El proyecto Supabase, conexión y migraciones hasta `0011` están verificados.
- [X] Workflow y frecuencia en GitHub Actions: lunes a las 00:00 de Argentina, ejecución manual, Secrets, exclusión de simultaneidad, comprobación previa de Elastic e indexación completa posterior verificadas.
- [ ] Automatización pendiente: recuperación incremental y política de limpieza de versiones físicas anteriores del índice.
- [ ] Política de publicaciones retiradas y recuperación de errores de indexación (Pendiente).
- Comprobación del historial de cron-job.org y del intervalo guardado; `/health/` ya está desplegada y el job fue creado.
- Ajuste de relevancia y paginación pública. Elasticsearch en Render, combinación con filtros, orden por score y reconstrucción automática posterior a la ingesta ya están implementados.
- Validación del geocodificador experimental, extracción explícita de ciudad/provincia, auditoría de coordenadas históricas y tratamiento definitivo de ubicaciones ausentes.
- Tecnología del frontend, mapa y contrato de la API futura.
- Registro del vencimiento exacto de la prueba de Elastic Cloud y continuidad posterior; configuración y comprobación de Django en Render con Elasticsearch. El servicio Elastic y su índice ya existen; el despliegue básico con Supabase ya funciona.

Requests y Beautiful Soup ya se usan para Brega. Comprobar primero si las consultas directas permiten obtener los datos de cada nueva fuente; no dar por necesaria la automatización de un navegador. No se ha adoptado React, un framework de scraping adicional, colas de tareas ni microservicios. El despliegue del sitio es un requisito de entrega; Django ya está alojado en Render y no se ha adoptado Vercel.

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
