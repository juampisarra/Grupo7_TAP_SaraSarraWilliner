# Gaggiotti: tercera inmobiliaria

Elegida por el equipo el 11 de octubre de 2026. Adaptador implementado en `propiedades/scraping/gaggiotti.py`, registrado como `gaggiotti`, con procedencia persistida `Gaggiotti`. Comparte contrato, importador, persistencia, indexación y tolerancia por fuente con Brega y Avantix. Su extracción JSON es independiente de los parsers Tokko.

Estado al 12 de octubre de 2026: publicada y verificada en Supabase, Elasticsearch y búsquedas públicas. No necesita migraciones, dependencias, variables de entorno ni Secrets nuevos.

## Primera ejecución productiva verificada — 12 de octubre

El usuario autorizó al agente a realizar commit, push a `main` y ejecución manual del workflow. El código se publicó en `a390093`; [Actions terminó correctamente](https://github.com/juampisarra/Grupo7_TAP_SaraSarraWilliner/actions/runs/38213432407) entre las 03:37:27 y las 03:52:17 de Argentina. Completó Avantix, Brega y Gaggiotti, con cero errores de detalle en las tres fuentes, y reconstruyó el índice.

| Comprobación | Resultado |
| --- | --- |
| Gaggiotti en Supabase | 306 publicaciones: 264 en venta, 46 en alquiler y cuatro compartidas. |
| Detalles y ubicación | 306 detalles verificados, 306 pares de coordenadas y puntos PostGIS; 305 ciudades explícitas. |
| Precisión | Las 306 ubicaciones siguen con precisión desconocida y radio nulo. |
| Identidad y modelo | Sin duplicados por fuente/identificador; todos los modelos de Gaggiotti pasan validación de campos. |
| Base completa | 173 Brega, 275 Avantix y 306 Gaggiotti: 754 publicaciones. |
| Elasticsearch | Alias sobre `propiedades-20261012065209-0b10f499`, 754 documentos. IDs y contenido de todos los documentos coinciden con PostgreSQL. |
| Listado público | HTTP 200: 650 ventas y 121 alquileres, con los 264/46 avisos de Gaggiotti respectivamente. |
| Texto `cochera` | HTTP 200: 299 ventas (112 Gaggiotti) y 37 alquileres (12 Gaggiotti). El orden público coincide exactamente con el ranking de Elasticsearch. |
| Radio 2 km, centro `-31.25,-61.49`, venta | Solo exactas: 113 resultados, cero Gaggiotti. Con `incluir_aproximadas=1`: 308 resultados, 119 Gaggiotti y advertencia de precisión. Coinciden con PostGIS. |
| Health y errores | `/health/` responde 200; radio negativo responde 400. |
| Aviso original | Una ficha Gaggiotti enlazada desde la base respondió HTTP 200. |

Los conteos son una instantánea de esta ejecución. Brega procesó 171 avisos actuales y conserva dos registros anteriores: no se implementó una política de bajas. Las comprobaciones posteriores al workflow fueron de solo lectura; la escritura productiva y la reconstrucción se realizaron mediante Actions. Los resultados locales del apartado siguiente corresponden al desarrollo previo.

## Servicio público verificado

Las páginas de [venta](https://www.gaggiotti.com.ar/propiedades/compra-venta) y [alquiler](https://www.gaggiotti.com.ar/propiedades/alquiler) cargan los avisos con JavaScript. Se inspeccionó el código público de la página y se reprodujeron las solicitudes de lectura que hace el navegador, sin login ni claves:

- `POST https://www.gaggiotti.com.ar/api/Property/Search`: listado filtrado y paginado. Este POST es una búsqueda, no modifica propiedades.
- `GET https://www.gaggiotti.com.ar/api/Property/<id>`: ficha completa de un aviso.
- `GET /api/Property/Operation`: confirmó `1 = Compra-Venta` y `2 = Alquiler` durante el relevamiento.
- `GET /api/Location/Property`: permitió contrastar la jerarquía de ciudades y barrios durante el relevamiento. La ingesta no necesita consultar este catálogo.

La ficha original enlazada desde el observatorio utiliza la ruta pública `/propiedad/compra-venta/<id>/` o `/propiedad/alquiler/<id>/`. Se comprobó que la ruta funciona sin el slug opcional del título. No se guarda como URL original la ruta técnica de la API.

## Listados, paginación y límites

El cuerpo de búsqueda reproduce los filtros del frontend: `operationTypes=[1]` o `[2]`, tipos/dormitorios vacíos, `withParking=null`, orden por ID descendente, `localizationType=3`, `localizationIds=[null]`, `limit=20` y `offset`. No se fija Rafaela como filtro: se conserva la localidad que publica cada aviso.

Se lee `response.properties` y se comprueban `pagination.limit`, `offset`, `totalCount` y `remaining`. El desplazamiento avanza por la cantidad realmente recibida; se termina cuando `remaining=0`. Un listado vacío coherente es válido. Páginas repetidas, IDs duplicados, un total cambiante, un lote vacío con resultados pendientes o un formato desconocido generan error de fuente; no se presentan como una ingesta completa.

Hay timeout de 15 segundos por solicitud, pausa de 0,5 segundos entre páginas y un máximo de 50 páginas por operación. Alcanzar el límite con resultados pendientes es un error. No se agregan reintentos automáticos.

`Search` ya devuelve los campos completos de las fichas: se contrastaron con el endpoint de detalle de un aviso real. El adaptador reutiliza esos objetos dentro de la misma instancia, únicamente después de completar el listado. Así la ingesta normal no necesita un GET por aviso. No es una caché persistente: una nueva ingesta descarga de nuevo los listados. Una consulta directa a `extraer_detalles` sin listado previo usa GET como respaldo. El importador común sigue procesando una ficha por publicación única, incluso si figura en ambas operaciones, y conserva su pausa de 0,5 segundos. El contador `Detalles solicitados` mide llamadas al adaptador, no solicitudes HTTP.

## Correspondencia de datos

| Datos de Gaggiotti | Destino y criterio |
| --- | --- |
| `id` | `identificador_fuente`, como texto. La identidad sigue siendo `(fuente, identificador_fuente)`. |
| `realAddress`, respaldo `address` | `direccion`. Se verificó que la web muestra `realAddress`; no se deduce una dirección a partir de coordenadas. |
| `type.name` | `tipo`. |
| `publicationTitle` | `titulo`. |
| `description`, respaldo `richDescription` | `descripcion`, con HTML y entidades limpiados y scripts/estilos eliminados. |
| `tags`, `customTags`, `extraAttributes` y cocheras positivas | `caracteristicas`, como texto, sin una columna por amenidad. |
| `suiteAmount` | `dormitorios`: se comprobó su uso como habitaciones en el frontend. |
| `roomAmount` | `ambientes`, separado de dormitorios. |
| `bathroomAmount` | `banos`, sin sumar toilettes automáticamente. |
| `operations` | Una publicación normalizada por operación; el importador consolida venta/alquiler y conserva precios separados. |
| `location.fullLocation` | Jerarquía `país | provincia | departamento | ciudad | barrio`. Castellanos no se guarda como ciudad. Sin nivel de ciudad, queda ausente. |
| `geoLatitude`, `geoLongitude` | Par numérico validado, sin cálculos espaciales en Python. |

No se inventan datos ausentes. Las cantidades desconocidas quedan en NULL y el cero explícito se conserva. Los textos vacíos recibidos en una ficha no borran información anterior, conforme a la política común existente. Formatos inválidos de cantidades generan error de ficha y conservan los detalles anteriores.

### Precios y monedas

Se selecciona la operación exacta (`Compra-Venta` o `Alquiler`). Los importes JSON se convierten a Decimal directamente: no se les aplica el lector de separadores de precios HTML de Tokko, que podría alterar los decimales.

Se respeta `webPrice`: solo se guarda el precio cuando es `true`, aunque la respuesta incluya importes ocultos. Si no hay precio publicado queda NULL. Se admiten ARS y USD con el período `0` observado en las operaciones regulares; monedas o períodos distintos se omiten con advertencia, sin conversiones. Se valida rango, finitud y como máximo dos decimales.

Si una operación publica varios precios, se conserva el primero, igual que hace el frontend de Gaggiotti. Se verificó un aviso con USD y ARS: no se suman ni mezclan esos valores. El modelo actual solo permite un importe/moneda por operación.

### Coordenadas y precisión

El mapa de la ficha usa los campos `geoLatitude` y `geoLongitude` para un marcador, sin círculo ni radio. `gmLocationType` incluye valores como `ROOFTOP`, `BY_HAND`, `RANGE_INTERPOLATED`, `APPROXIMATE`, `GEOMETRIC_CENTER` y `UNKNOWN`; describe cómo se obtuvo el punto y no se toma como garantía de precisión del aviso.

Por eso se guarda **`ubicacion_aproximada=NULL` y `radio_ubicacion_m=NULL`**. La decisión particular del equipo sobre Avantix no se extrapola a Gaggiotti. Para incluir estos puntos en los filtros PostGIS hay que usar `incluir_aproximadas=1`; se consulta el punto publicado, con precisión desconocida.

Pares incompletos, no finitos o fuera de rango se descartan con advertencia. La ingesta común conserva su política de geocodificación únicamente con ciudad explícita. No se consulta Nominatim para completar nombres que ya aporta la jerarquía de la fuente. La geografía continúa exclusivamente en PostGIS.

## Ejecución y publicación

Solo Gaggiotti:

```powershell
.\.venv\Scripts\python.exe -X utf8 manage.py importar_propiedades gaggiotti
```

Todas las fuentes:

```powershell
.\.venv\Scripts\python.exe -X utf8 manage.py importar_propiedades
```

El orden será `avantix`, `brega`, `gaggiotti`. Después de una ingesta manual, reconstruir el índice con `python manage.py reconstruir_indice`, comprobando previamente el resultado de la ingesta. El workflow ya coordina ambos pasos, incluido el éxito parcial: ver [tolerancia y recuperación](ingesta.md).

Para publicar: hacer push del código, dejar que Render tome la nueva versión si corresponde y ejecutar **Ingesta Semanal de Propiedades** desde GitHub Actions. Revisar el resumen de Gaggiotti, la reconstrucción del índice, los registros `fuente=Gaggiotti` en Supabase y sus enlaces/resultados en `/propiedades/`. No hace falta volver a configurar cuentas ni servicios.

## Verificación y límites

El relevamiento inicial del 11 de octubre obtuvo 264 avisos de venta y 46 de alquiler, con cuatro compartidos: 306 identificadores únicos. Son conteos de esa revisión, no constantes que deban fijarse en el scraper. Se leyeron todas las páginas y se normalizaron las respuestas capturadas de ambas operaciones.

La primera ingesta real en SQLite efímero guardó 306 publicaciones, pero solo verificó 278 fichas: 28 consultas de detalle recibieron HTTP 502. Esto motivó reutilizar las fichas completas del listado. Un intento posterior también recibió 502 en el primer listado. La última comprobación en vivo con la versión optimizada terminó correctamente: 264 resultados de venta, 46 de alquiler y 306 detalles únicos parseados sin errores ni GET de fichas. Esta última comprobación solo extrajo datos; la persistencia se verificó por separado como se explica a continuación. La disponibilidad de la fuente sigue siendo externa al proyecto.

La versión optimizada se verificó reproduciendo las 17 respuestas de listado reales capturadas, a través del adaptador y del importador común: 306 altas, 306 detalles verificados, cero errores, 306 pares de coordenadas y 305 ciudades explícitas. La publicación restante solo informa provincia/departamento y no recibe una ciudad inventada. Una segunda pasada produjo cero altas y 306 actualizaciones, manteniendo 306 filas. Se validaron los 306 modelos con `full_clean` y su serialización al documento textual de Elasticsearch. No hubo GET de fichas ni consultas de geocodificación. Esta repetición utiliza respuestas capturadas, no certifica una nueva ejecución completa contra el sitio en vivo.

Suite final: 117 pruebas descubiertas, 116 aprobadas y una integración PostGIS omitida por usar SQLite. La base efímera se destruyó al finalizar; no se modificaron `db.sqlite3`, Supabase ni Elasticsearch.

Las pruebas automáticas cubren precios separados y ocultos, múltiples monedas, cero/NULL, limpieza de texto, jerarquía de ubicación, precisión desconocida, IDs y URLs, paginación completa/errónea, timeouts, persistencia y actualizaciones sin duplicados. También prueban que otra fuente fallida no impida procesar Gaggiotti y que un fallo de Gaggiotti no bloquee las posteriores. Se comprueba la serialización de sus campos al documento común de Elasticsearch.

La política de avisos retirados sigue pendiente para todas las fuentes. No se interpreta `deletedAt` como baja: el servicio lo devuelve incluso en avisos que lista públicamente. Tampoco se importan automáticamente imágenes o superficies a columnas nuevas; esas ampliaciones del modelo siguen fuera de esta etapa.
