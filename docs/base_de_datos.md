# SQLite y Supabase/PostgreSQL

El backend usa el ORM de Django con una conexión PostgreSQL mediante `psycopg`. No necesita el SDK de Supabase ni una API key. PostGIS se integró mediante la migración `0011`, aplicada en Supabase; consultar [almacenamiento y filtros geográficos](postgis.md). Elasticsearch está conectado y cargado localmente; ver [índice y búsqueda](elasticsearch.md).

## Preparación local

Desde la raíz del proyecto, en PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Copiar `.env.example` solo si todavía no existe `.env`, para conservar cualquier configuración propia. Antes de ejecutar Django, completar `DJANGO_SECRET_KEY` con una clave propia, generada mediante:

```powershell
.\.venv\Scripts\python.exe -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Guardar el resultado en `.env`, mantener `DJANGO_DEBUG=True` y `DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1` para desarrollo, y guardar el archivo como UTF-8 sin BOM. No compartir la clave ni subirla a Git. Con `DB_ENGINE=sqlite` se usa `db.sqlite3`; SQLite también es la selección predeterminada si falta `DB_ENGINE`, pero Django requiere la clave secreta incluso con esa base. Las variables del sistema tienen prioridad sobre `.env`. Este archivo y `backups/` están excluidos de Git. Para Render, ver [la guía del despliegue](despliegue.md).

Aplicar las migraciones con el entorno ya configurado:

```powershell
.\.venv\Scripts\python.exe manage.py migrate
```

La migración `0008` agrega campos opcionales sin eliminar publicaciones. Los registros existentes reciben textos vacíos y cantidades NULL; una nueva ingesta podrá completar los datos.

## Conservar publicaciones de SQLite

Antes de cambiar a PostgreSQL, mantener `DB_ENGINE=sqlite`, detener ingestas/servidores que puedan escribir y exportar desde la raíz:

```powershell
.\.venv\Scripts\python.exe manage.py migrate
New-Item -ItemType Directory -Force backups
.\.venv\Scripts\python.exe -X utf8 manage.py dumpdata propiedades.Propiedad --indent 2 --output backups/propiedades.json
```

Guardar también una copia del archivo SQLite si se quiere un respaldo completo:

```powershell
Copy-Item db.sqlite3 backups/db.sqlite3
```

La opción `-X utf8` evita exportar con la codificación regional de Windows y conserva los acentos para la importación. La exportación JSON conserva identificadores internos, identidad por fuente, precios, dormitorios, coordenadas y los demás campos del modelo. No exporta usuarios ni sesiones. No borrar `db.sqlite3` después de exportar; permite volver a la configuración anterior.

## Crear y conectar Supabase

1. Crear un proyecto en Supabase y guardar su contraseña de base de datos.
2. Abrir **Connect** y obtener los datos de conexión directa o **Session pooler**. La conexión directa requiere IPv6 salvo que el proyecto tenga el complemento IPv4; Session pooler permite conectar desde una red IPv4. Para este backend usar una de esas modalidades, no Transaction pooler.
3. Completar `.env` con los datos exactos del panel:

```dotenv
DB_ENGINE=postgresql
PGHOST=host-copiado-del-panel
PGPORT=5432
PGDATABASE=postgres
PGUSER=usuario-copiado-del-panel
PGPASSWORD='contraseña-real-de-la-base'
PGSSLMODE=require
```

El usuario de Session pooler normalmente incluye el identificador del proyecto. No construir el host a mano. `PGPASSWORD` es la contraseña de PostgreSQL, no una API key, y se escribe sin codificarla como una URL. `.env` nunca debe subirse al repositorio.

Las opciones de conexión se basan en la [documentación oficial de Supabase](https://supabase.com/docs/guides/database/connecting-to-postgres).

Crear las tablas mediante las migraciones de Django y verificar la conexión:

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py showmigrations propiedades
```

`manage.py check` revisa la configuración, pero no demuestra por sí solo que PostgreSQL sea accesible. `migrate`/`showmigrations` sí necesitan conectarse. Si la conexión falla, no se vuelve automáticamente a SQLite.

## Importar el respaldo en el destino vacío

Con PostgreSQL ya configurado y migrado, comprobar cuántas propiedades tiene:

```powershell
.\.venv\Scripts\python.exe manage.py shell -c "from propiedades.models import Propiedad; print(Propiedad.objects.count())"
```

Usar el respaldo solo si el destino tiene **cero propiedades**:

```powershell
.\.venv\Scripts\python.exe -X utf8 manage.py loaddata backups/propiedades.json
.\.venv\Scripts\python.exe manage.py shell -c "from propiedades.models import Propiedad; print(Propiedad.objects.count())"
```

Comparar el total con el origen y revisar ejemplos desde Django Admin o el listado. `loaddata` conserva las claves internas: no usar este procedimiento para mezclar una base que ya tiene publicaciones, porque podría sobrescribir registros o generar conflictos. En ese caso se requiere otro procedimiento por `(fuente, identificador_fuente)`.

Si no se quieren trasladar datos, omitir la importación y ejecutar directamente:

```powershell
.\.venv\Scripts\python.exe manage.py importar_propiedades brega
```

## Pruebas

Para las pruebas locales, usar `DB_ENGINE=sqlite` y ejecutar:

```powershell
.\.venv\Scripts\python.exe manage.py test propiedades config
```

Las pruebas cubren el modelo, ingesta, extracción y configuración PostgreSQL con el driver instalado; no reemplazan una prueba de conexión y migración contra un proyecto real de Supabase. En este entorno ya se verificaron conexión y migraciones hasta `0010`, y se comprobaron 173 publicaciones en la ingesta previa. No hubo un traslado automático desde SQLite.

## Coordenadas del mapa de Brega

El scraper lee las coordenadas del círculo que Brega publica en el mapa de cada ficha. Guarda `latitud`, `longitud`, `ubicacion_aproximada=True` y `radio_ubicacion_m`. El radio proviene del aviso; las tres fichas comprobadas publicaban 400 metros. No se calcula una distancia ni se realiza un filtro espacial en Python: esas consultas siguen reservadas a PostGIS.

Tener coordenadas no implica conocer ciudad/provincia. Sin enriquecimiento opcional, esos textos siguen vacíos si la fuente no los identifica; `zona` conserva el rótulo de ubicación del aviso. El centro de un círculo aproximado tampoco garantiza la dirección exacta del inmueble.

Después de actualizar el código, aplicar las migraciones y repetir la ingesta para completar los datos disponibles:

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py importar_propiedades brega
```

## Completar ciudad/provincia opcionalmente

La migración `0010` incorpora procedencia de los nombres y caché persistente de consultas inversas. Para activar el enriquecimiento:

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py importar_propiedades brega --completar-ubicacion
```

El comando habitual sin la opción conserva el scraping de siempre, sin nuevas consultas inversas. El alias `importar_brega` también acepta la opción.

- Solo se completan ciudad/provincia faltantes. Lo explícito de la inmobiliaria tiene prioridad.
- `ciudad_origen` y `provincia_origen` registran `fuente` o `nominatim_inversa` por separado. Un origen vacío en datos antiguos significa que no se registró su procedencia.
- Latitud, longitud, zona y precisión permanecen como las aporta la fuente. No se reemplaza el punto por las coordenadas devueltas por Nominatim.
- `propiedades_consultalocalidad` guarda los nombres, estado y fecha de consulta por par de coordenadas. Reutiliza respuestas válidas, vacías y ambiguas; un error temporal se reintenta después de 24 horas. Las respuestas no fallidas no se refrescan automáticamente mientras el punto no cambie.
- Al cambiar coordenadas, se descartan únicamente nombres obtenidos por geocodificación inversa del punto anterior. Esto ocurre incluso sin activar la opción; el nuevo punto puede consultar o reutilizar su propia caché cuando se active.
- Si no hay coordenadas, falla el servicio, aparecen categorías contradictorias o el resultado contradice un lugar conocido, no se completan los campos y continúa la ingesta. No se interpreta barrio/departamento como ciudad. Puede completarse solo provincia si no se identifica localidad.

El servicio conserva sus nombres: por ejemplo, en la muestra real devolvió `Municipio de Lehmann`. Los valores inferidos pueden ser incorrectos cerca de límites administrativos, especialmente con los círculos aproximados de Brega. No se verifica si un círculo cruza esos límites; las consultas espaciales futuras corresponden a PostGIS.

Nominatim directo e inverso comparten un ritmo mínimo de 1,5 segundos entre solicitudes y no reintentan inmediatamente. Ejecutar un único job con Nominatim público a la vez. Consultar sus [condiciones de uso](https://operations.osmfoundation.org/policies/nominatim/) y [documentación de geocodificación inversa](https://nominatim.org/release-docs/latest/api/Reverse/). Los datos derivados proceden de OpenStreetMap y deben conservar su atribución al mostrarlos.

La muestra inicial de tres puntos devolvió Bella Italia/Santa Fe, Rafaela/Santa Fe y Municipio de Lehmann/Santa Fe. Posteriormente, la revisión de solo lectura del 8 de octubre de 2026 comprobó 173 publicaciones en Supabase, 172 con coordenadas completas, 170 con ciudad inferida, 172 con provincia inferida y 164 entradas de caché. Estos conteos muestran que ya se utilizó el enriquecimiento para guardar publicaciones; no garantizan que cada nombre inferido sea correcto.
