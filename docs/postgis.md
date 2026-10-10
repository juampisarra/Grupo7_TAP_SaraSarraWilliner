# PostGIS y filtros geográficos

Implementación del 9 de octubre de 2026. La migración `0011_ubicacion_postgis` ya se aplicó a Supabase: PostGIS 3.3.7 en el esquema `extensions`, 173 publicaciones conservadas y 172 puntos espaciales generados. El código nuevo todavía debe desplegarse en Render.

## Almacenamiento y sincronización

Se conserva `DB_ENGINE=postgresql` y el driver psycopg. No se necesita cambiar al backend GeoDjango ni instalar GEOS/GDAL en Windows o Render.

La migración crea una columna de PostgreSQL llamada `ubicacion`, de tipo `geography(Point,4326)`. WGS84/SRID 4326 usa longitud y latitud en grados. `ST_DWithin` sobre `geography` interpreta la distancia en **metros**.

La columna es **generada y almacenada por PostgreSQL** a partir de `longitud` y `latitud`: la base la recalcula automáticamente en altas y actualizaciones, incluidas las que realiza el scraper. No se escribe desde Django ni requiere un segundo job. Pares incompletos o fuera de rango producen NULL; no se inventa un punto. Los nombres de los campos del modelo siguen siendo portátiles y la columna espacial se administra mediante la migración específica de PostgreSQL.

Hay dos índices GiST: uno sobre `ubicacion` para distancia y otro sobre su conversión a `geometry` para áreas. PostGIS hace todos los cálculos; Python solo valida los parámetros. Los valores de las consultas se pasan como parámetros SQL.

En una base PostgreSQL nueva, ejecutar `python manage.py migrate`. El usuario necesita permisos para habilitar PostGIS; si no los tiene, habilitar la extensión desde el panel de Supabase y repetir la migración. Se respeta el esquema donde ya esté instalada. La migración tiene una espera de bloqueo máxima de cinco segundos: si hay una ingesta concurrente, puede fallar y deberá repetirse cuando termine. Revertir `0011` elimina la columna y sus índices, conservando latitud/longitud y la extensión compartida.

En SQLite la migración no crea objetos espaciales. El listado y las pruebas generales siguen funcionando; una solicitud geográfica devuelve 503 explicando que requiere PostgreSQL con PostGIS. No hay un cálculo alternativo en Python.

## Consultas del backend

Los filtros se implementan en `propiedades/geografia.py` y pueden combinarse con venta/alquiler en el listado existente. No hay mapa ni formulario geográfico nuevo. El endpoint sigue devolviendo HTML; no se creó una API JSON de resultados. Los errores de entrada devuelven JSON con estado 400.

Radio de dos kilómetros:

```text
/propiedades/?operacion=alquiler&latitud=-31.25&longitud=-61.49&radio_m=2000&incluir_aproximadas=1
```

Rectángulo:

```text
/propiedades/?operacion=venta&oeste=-61.55&sur=-31.30&este=-61.40&norte=-31.20&incluir_aproximadas=1
```

Las coordenadas son ejemplos de consulta, no ubicaciones asignadas a avisos. Usar el servidor local para probar hasta que estos cambios estén desplegados.

- Radio: los tres parámetros son obligatorios; `radio_m` acepta desde cero hasta 20.000.000 metros. `ST_DWithin` incluye el límite del radio.
- Área: los cuatro límites son obligatorios; se requiere `oeste < este` y `sur < norte`. `ST_Covers` incluye los puntos en el borde. No admite rectángulos que crucen el antimeridiano ni polígonos arbitrarios todavía.
- Se admite radio **o** área por solicitud. No se aceptan valores no finitos, coordenadas fuera de rango o radios negativos.
- Sin parámetros espaciales se conserva el listado normal. No cambia el filtro predeterminado de alquiler.

## Ubicaciones aproximadas

Por defecto, los filtros espaciales solo incluyen registros con `ubicacion_aproximada=False`. True representa un área aproximada; NULL indica precisión desconocida. Actualmente Brega aporta 172 áreas aproximadas y no hay ubicaciones explícitamente exactas, por lo que un filtro espacial sin `incluir_aproximadas=1` puede devolver cero resultados aunque el listado normal tenga avisos.

`incluir_aproximadas=1` habilita también puntos aproximados y de precisión desconocida. **Se filtra el centro publicado, no la extensión del círculo ni la ubicación real garantizada del inmueble.** Un centro dentro puede corresponder a una propiedad fuera, y viceversa. El listado muestra esta advertencia y la precisión disponible. El radio publicado se conserva, pero no se interpreta como distancia al punto buscado. La política futura para intersección o cobertura de áreas de incertidumbre sigue pendiente.

## Verificación

- Suite de 55 pruebas con SQLite: 54 aprobadas y una de integración PostGIS omitida, porque SQLite no soporta esta feature.
- Pruebas reales contra PostGIS usando una tabla temporal dentro de una transacción revertida: punto cero, distancia en metros, límites inclusivos, ubicación aproximada/desconocida, pares incompletos, coordenadas inválidas, actualización e invalidación automática y respuestas HTTP del listado.
- La prueba temporal no insertó avisos de prueba en la tabla persistente. Al finalizar seguían las 173 publicaciones y 172 puntos.

Para automatizar la prueba `PostGISIntegracionTests`, usar una **base PostgreSQL de pruebas independiente** con permisos para crear la base y habilitar PostGIS. No ejecutar `manage.py test` apuntando a Supabase de producción. La suite general se ejecuta con `DB_ENGINE=sqlite` como indica `AGENTS.md`.

Referencias: [PostGIS en Supabase](https://supabase.com/docs/guides/database/extensions/postgis), [ST_DWithin](https://postgis.net/docs/ST_DWithin.html) y [ST_Covers](https://postgis.net/docs/ST_Covers.html).
