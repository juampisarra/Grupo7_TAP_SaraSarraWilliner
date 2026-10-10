# Elasticsearch: índice y búsqueda textual

Actualizado el 10 de octubre de 2026. El proyecto Elastic Cloud ya existe y responde como Elasticsearch 9.6.0. La conexión se comprobó desde Django con el cliente oficial Python 9.5.1. La API key encoded se utiliza directamente, sin decodificarla ni agregar el prefijo `ApiKey `.

Se cargaron **173 documentos** desde Supabase, sin ejecutar scraping ni modificar publicaciones. `propiedades` es el alias del índice activo. La búsqueda y los comandos están implementados localmente; falta configurar las variables en Render y desplegar el código. La actualización automática tras la ingesta todavía no está implementada.

El despliegue queda a cargo del compañero propietario de Render después del push del usuario. Seguir la [guía de continuidad](continuidad.md) para configurar su entorno, publicar y verificar búsquedas desde la URL pública.

## Configuración

```dotenv
ELASTICSEARCH_URL=https://TU_ENDPOINT.elastic.cloud:443
ELASTICSEARCH_API_KEY='TU_API_KEY_ENCODED'
ELASTICSEARCH_INDEX=propiedades
```

Guardar los valores reales en `.env` local y, por separado, en las variables del servicio Render. No subirlos a Git ni enviarlos en capturas. En Render pegar los valores sin comillas adicionales. El sitio y `/health/` pueden arrancar sin Elasticsearch configurado: únicamente una búsqueda textual o un comando del índice requieren conexión. Una búsqueda sin configuración o con el servicio caído devuelve 503, no una lista vacía ni un reemplazo SQL con LIKE.

La key utilizada por la reconstrucción necesita permisos para crear índices, escribir documentos, refrescar, contar y administrar aliases. La búsqueda necesita lectura y apertura/cierre de contextos PIT. Si se separan credenciales de escritura y lectura más adelante, habrá que adaptar la configuración. La prueba cubre la evaluación indicada para el martes 13 de octubre; falta registrar la fecha y hora exactas de vencimiento mostradas por Elastic. No se comprobó ese dato desde el panel y no se asume alojamiento gratuito permanente.

## Comandos

Desde la raíz, usando el `.env` conectado a Supabase:

```powershell
.\.venv\Scripts\python.exe -X utf8 manage.py comprobar_elasticsearch
.\.venv\Scripts\python.exe -X utf8 manage.py reconstruir_indice
.\.venv\Scripts\python.exe -X utf8 manage.py buscar_propiedades "departamento con cochera" --limite 5
```

El primer comando verifica conexión y autenticación sin mostrar secretos. El segundo carga todos los registros de la **base configurada**, no consulta Brega. Verificar que no esté activo un `DB_ENGINE=sqlite` temporal antes de reconstruir el índice de Supabase. Por defecto se rechaza activar una versión vacía; `--permitir-vacio` permite hacerlo explícitamente.

La reconstrucción crea una versión física nueva (`propiedades-<fecha>-<identificador>`) con documentos cuyo `_id` es la PK de PostgreSQL. Fuente e identificador de origen se conservan como procedencia. Repetir el comando no duplica los resultados del alias, aunque conserve versiones físicas distintas.

Después de una carga completa, el comando refresca, comprueba el conteo y cambia el alias en una única operación. Si falla un documento o el conteo, no activa esa versión. Los índices anteriores y las versiones incompletas **se conservan**; no hay borrados automáticos. Pueden limpiarse manualmente desde Elastic después de identificar cuál apunta al alias y confirmar qué versiones se desean eliminar. Si un error de red ocurre justo al cambiar el alias, comprobar su estado antes de repetir: el servidor podría haber aplicado la operación aunque el cliente no recibiera la respuesta.

Ejecutar un solo proceso de reconstrucción y evitar ingestas o cambios de propiedades mientras se reconstruye. Esta etapa no coordina escritores concurrentes ni garantiza sincronización continua entre PostgreSQL y Elasticsearch. Después de una ingesta manual, repetir `reconstruir_indice` hasta implementar la actualización automática y recuperación de fallos.

## Texto y relevancia

Se indexan título, descripción, características, dirección, zona, ciudad, provincia y tipo. No se indexan precios, operaciones ni coordenadas para filtrar: esas responsabilidades siguen en PostgreSQL/PostGIS. Los resultados completos se recuperan desde la base principal.

El analizador incorporado `spanish` tokeniza, normaliza, elimina stopwords y reduce formas de palabras. En la prueba real, `departamentos con cocheras y quinchos` produjo `departament`, `cocher`, `quinch`. Los términos se organizan mediante el índice invertido; BM25 calcula relevancia según frecuencia, rareza y longitud del texto.

Un campo de texto agregado permite encontrar términos repartidos entre diferentes campos. La consulta exige todos los términos analizados cuando hay uno o dos; con más términos requiere al menos el 75%, redondeado hacia abajo. Se agregan pesos para título (3), características (2) y tipo (2). Son pesos iniciales comprobados con ejemplos, no una evaluación exhaustiva de calidad.

Los resultados se ordenan por score descendente; los empates por PK ascendente. Se leen todos los IDs con PIT y `search_after`, en lotes de 100, sin truncar silenciosamente a la primera página. Luego PostgreSQL aplica operación y PostGIS los filtros geográficos; el backend conserva el ranking y descarta IDs ausentes de la base. El listado aún devuelve todos sus resultados: una paginación pública y optimización para volúmenes grandes siguen pendientes.

## Probar desde Django

El listado existente admite `q` por URL, sin un frontend nuevo:

```text
/propiedades/?operacion=alquiler&q=departamento%20con%20cochera
/propiedades/?operacion=venta&q=cochera%20y%20quincho
/propiedades/?q=departamento%20con%20cochera&latitud=-31.25&longitud=-61.49&radio_m=2000&incluir_aproximadas=1
```

Sin `q` se conserva el orden por actualización y no se consulta Elasticsearch. Texto de más de 300 caracteres devuelve 400. Una consulta solo con stopwords no devuelve coincidencias. Cambiar operación desde el selector conserva `q` y los parámetros geográficos. Las ubicaciones aproximadas mantienen las limitaciones descritas en [PostGIS](postgis.md).

## Validación realizada

- Conexión real desde el comando Django: Elasticsearch 9.6.0.
- Primera reconstrucción: 173 documentos; Supabase conserva 173 publicaciones.
- Segunda reconstrucción real: un solo índice activo en el alias, los mismos 173 IDs de Supabase y dos versiones físicas conservadas, sin duplicar resultados.
- Búsqueda real `departamento con cochera`: 16 coincidencias, 5 en alquiler y 11 en venta en esta instantánea.
- Búsqueda real `cochera y quincho`: 2 coincidencias.
- Índice temporal de prueba: una ficha con tres términos obtuvo score 1,726 y una con dos obtuvo 1,151; la de un solo término quedó excluida. Se eliminó exclusivamente ese índice temporal al terminar.
- Búsqueda textual combinada con PostGIS: HTTP 200. No se ejecutó scraping ni indexación durante las consultas.
- Pruebas automáticas con SQLite y Elasticsearch simulado: configuración, paginación, cierre PIT, fallos, reconstrucción, protección ante base vacía, conservación del alias, combinación de resultados y HTTP. Ejecutar con `DB_ENGINE=sqlite` como indica `AGENTS.md`; no crear una base de pruebas en Supabase.
- Suite final: 72 pruebas descubiertas, 71 aprobadas y una integración PostGIS omitida en SQLite. `makemigrations --check --dry-run`, `pip check` y revisión de diferencias sin errores. `.env` continúa ignorado por Git.

Referencias: [cliente oficial Python](https://www.elastic.co/docs/reference/elasticsearch/clients/python/getting-started) y [API de aliases](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-indices-update-aliases).

## Pendiente

Configurar Render y desplegar; comprobar consultas desde la URL pública. Después integrar indexación posterior al guardado con recuperación de fallos y preparar GitHub Actions. La reconstrucción completa ya permite recuperar el índice, pero no reemplaza una política de sincronización automática. La detección de avisos retirados de Brega sigue pendiente: reconstruir refleja lo que está en PostgreSQL, no determina qué avisos siguen publicados en la fuente.
