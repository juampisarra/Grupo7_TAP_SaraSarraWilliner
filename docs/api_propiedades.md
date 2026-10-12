# Filtros, paginación y API de propiedades

Implementación local del 12 de octubre de 2026, pendiente de publicación. Los filtros y la paginación no necesitan nuevas variables ni reconstruir Elasticsearch. El código actual incluye también fotos: requiere aplicar `0012` y ejecutar ingesta para cargar las galerías. No agrega dependencias ni Secrets. Ver [fotos](fotos.md). El sitio público conserva la versión anterior hasta desplegar este código.

## Plan y alcance de esta etapa

1. Definir y validar un contrato común de operación, tipo, dormitorios, moneda, precio y páginas.
2. Aplicar filtros estructurados en PostgreSQL y geográficos exclusivamente en PostGIS.
3. Combinar las coincidencias de Elasticsearch conservando relevancia y paginar después de filtrar.
4. Exponer los mismos resultados en HTML y JSON, conservando parámetros y advertencias de precisión.
5. Probar entradas inválidas, monedas/operaciones separadas, nulos/cero, páginas, ranking, consultas acotadas y servicios no disponibles; documentar funcionamiento y límites.

Implementado en `propiedades/consultas.py` (validación, filtros y coordinación), `propiedades/views.py` (respuestas y serialización), `config/urls.py` y la plantilla de prueba. No se implementó el frontend definitivo ni el mapa. La plantilla incorpora únicamente navegación anterior/siguiente y conservación de filtros; los filtros nuevos se prueban por URL.

## Rutas y métodos

- `GET /propiedades/`: HTML paginado para pruebas.
- `GET /api/propiedades/`: API pública JSON de consulta de publicaciones ya guardadas.
- Ambas aceptan HEAD; POST, PUT y DELETE responden 405 con `Allow: GET, HEAD`.
- No requieren credenciales del visitante. Las claves de Supabase y Elastic permanecen en el backend.
- Consultar no ejecuta scraping, enriquecimiento ni reconstrucción del índice. No se habilita la Data API de Supabase ni se agrega CORS; un frontend alojado en otro origen requerirá definir esa configuración.

## Parámetros compartidos

| Parámetro | Contrato |
| --- | --- |
| `operacion` | `venta` o `alquiler`. Por defecto `alquiler` únicamente si se omite. Otro valor, incluido vacío, devuelve 400. |
| `tipo` | Coincidencia completa sin distinguir mayúsculas (`iexact`); hasta 50 caracteres. Se recortan espacios exteriores. No es búsqueda parcial ni agrupa sinónimos/categorías. Tipo inexistente: cero resultados. |
| `dormitorios` | Cantidad exacta, entero de 0 a 32767. Cero es válido. Los NULL no coinciden con cantidades concretas; se conserva en JSON el estado `dormitorios_verificados`. |
| `moneda` | `ARS` o `USD`, normalizada a mayúsculas. Filtra la moneda de la operación seleccionada. Exige `operacion` explícita. |
| `precio_min`, `precio_max` | Límites inclusivos sobre el precio de la operación. Exigen `operacion` y `moneda` explícitas. Se acepta uno o ambos. Mínimo no puede superar máximo. |
| `q` | Texto, hasta 300 caracteres tras recortar espacios exteriores. Vacío: sin búsqueda textual ni conexión a Elasticsearch. |
| `pagina` | Entero positivo, desde 1; valor predeterminado 1. Límite de validación: 2147483647. |
| `por_pagina` | Entero entre 1 y 100, predeterminado 20. |
| Geografía | Los mismos parámetros de radio/rectángulo y `incluir_aproximadas` de [PostGIS](postgis.md). |

Los filtros opcionales `tipo`, `dormitorios`, `moneda`, `precio_min`, `precio_max` y `q` vacíos se consideran omitidos. Los parámetros de página presentes pero vacíos son inválidos. Los parámetros geográficos conservan su validación estricta; no se omiten valores vacíos.

Los importes se envían sin separadores de miles, usando punto decimal y como máximo dos decimales: `750000`, `100000.25` o `0`. Rango máximo `9999999999999.99`. No se aceptan negativos, coma decimal, NaN, Infinity ni notación científica. Se utiliza Decimal, sin conversiones ARS/USD. Un rango de precio excluye NULL; no los interpreta como cero. Filtrar únicamente moneda no exige que el importe sea conocido.

Los parámetros conocidos repetidos, incluso con el mismo valor, devuelven 400. Los desconocidos se ignoran; no implementan filtros adicionales. Los enlaces de página conservan los parámetros originales codificados. Cambiar operación o texto desde el formulario reinicia en página 1 y conserva los demás filtros.

## Ejemplos

```text
/api/propiedades/?operacion=venta&tipo=Casa&dormitorios=2&moneda=USD&precio_min=50000&precio_max=150000&por_pagina=20&pagina=1
/api/propiedades/?operacion=alquiler&moneda=ARS&precio_max=700000&q=cochera
/api/propiedades/?operacion=venta&q=casa&latitud=-31.25&longitud=-61.49&radio_m=2000&incluir_aproximadas=1
/propiedades/?operacion=venta&tipo=Casa&dormitorios=2&moneda=USD&precio_max=150000&por_pagina=10
```

## Respuesta JSON

Ejemplo ilustrativo de una página vacía:

```json
{
  "total": 0,
  "pagina": 1,
  "por_pagina": 20,
  "total_paginas": 1,
  "siguiente": null,
  "anterior": null,
  "operacion": "alquiler",
  "orden": "actualizacion",
  "advertencias": [],
  "resultados": []
}
```

Cada elemento de `resultados` incluye:

- `fotos`: lista ordenada de URLs externas HTTPS; `foto_portada`: la primera URL o NULL. Sin fotos devuelve lista vacía. Campos agregados en la etapa local posterior que requiere `0012` y una ingesta; ver [fotos](fotos.md).

- Identidad: `id`, `fuente`, `identificador_fuente`, `url_original`.
- Texto y clasificación: `tipo`, `titulo`, `descripcion`, `caracteristicas`.
- Ubicación textual: `direccion`, `ciudad`, `provincia`, `zona`, `ciudad_origen`, `provincia_origen`.
- Cantidades: `dormitorios`, `dormitorios_verificados`, `ambientes`, `banos`.
- Coordenadas y precisión: `latitud`, `longitud`, `ubicacion_aproximada`, `radio_ubicacion_m`. Se preservan NULL y cero. No se expone la columna espacial interna `ubicacion`.
- `actualizada_en`: fecha/hora ISO 8601 con zona horaria.
- `relevancia`: score de Elasticsearch cuando hay texto; NULL sin búsqueda textual. No es un porcentaje ni comparable entre consultas distintas.
- `venta` y `alquiler`, cada una con `disponible` (booleano), `precio` (cadena decimal de dos posiciones o NULL) y `moneda` (cadena o NULL). Se devuelven ambas operaciones, aunque se filtre una sola.

Por ejemplo: `"venta": {"disponible": true, "precio": "100000.25", "moneda": "USD"}`. Los precios se serializan como cadenas para conservar su precisión decimal. Los textos ausentes conservan las cadenas vacías del modelo; las cantidades desconocidas siguen en NULL.

`total` cuenta coincidencias después de todos los filtros, no elementos de la página ni hits brutos de Elasticsearch. `siguiente` y `anterior` son enlaces relativos al mismo endpoint con los filtros conservados, o NULL. `orden` indica `actualizacion` o `relevancia`.

Con un filtro espacial y `incluir_aproximadas=1`, `advertencias` incluye el aviso de centros aproximados y precisión desconocida. Se filtran los puntos publicados, no las áreas de incertidumbre ni la ubicación garantizada de la propiedad. Gaggiotti continúa con precisión desconocida; no se modifica la clasificación geográfica.

## Orden, coordinación y coste

Sin texto se usa SQL: COUNT del resultado filtrado y recuperación de una página, ordenada por `actualizada_en DESC, id DESC`. El ID resuelve empates de forma determinista.

Con texto se conserva la consulta BM25 existente: se leen todos los IDs/score mediante PIT y `search_after`, con score descendente e ID ascendente para empates. PostgreSQL/PostGIS determinan qué IDs cumplen los filtros, en lotes de hasta 500. Se conserva el orden de Elasticsearch, se descartan IDs ausentes y se pagina ese conjunto. Solo se recuperan los modelos completos de la página solicitada (máximo 100), sin cargar todos los textos para descartarlos luego.

No se pagina Elasticsearch antes de filtrar: eso produciría páginas incompletas y totales incorrectos. La estrategia es apropiada al volumen actual; todavía lee todos los IDs coincidentes por consulta textual y usa memoria proporcional al ranking. Optimizar consultas masivas/cursor y cachear resultados queda para una etapa posterior; no hay truncamiento silencioso a 10.000.

El orden es determinista sobre los mismos datos, pero cada solicitud recalcula su consulta. Una ingesta o reconstrucción entre páginas puede cambiar totales y posiciones. No se mantiene un snapshot compartido entre solicitudes del visitante. Las referencias son los datos de PostgreSQL y el índice activo; las altas todavía no indexadas no aparecen en búsquedas textuales hasta reconstruir. La política de bajas local utiliza `en_venta`/`en_alquiler`: avisos retirados de la operación seleccionada quedan excluidos incluso si el índice anterior devuelve sus IDs. Una operación no disponible puede conservar su precio histórico; consultar siempre `disponible`. Ver [mantenimiento](mantenimiento.md).

## Errores

HTML y JSON comparten el contrato de errores de consulta: `{"error": "mensaje"}`.

| Estado | Situación |
| --- | --- |
| 200 | Página válida, incluida página 1 vacía (total 0, una página). |
| 400 | Parámetros inválidos/repetidos, operación o moneda inválidas, rango incoherente, falta de moneda/operación para precio o geografía inválida. |
| 404 | Número de página válido pero inexistente, incluida página 2 de un resultado vacío. No se redirige silenciosamente a la última página. |
| 405 | Método distinto de GET/HEAD. Respuesta estándar de Django; no es un error de consulta JSON. |
| 503 | Elasticsearch no disponible para una consulta textual o filtros geográficos sin PostgreSQL/PostGIS. No se sustituye por LIKE ni lista vacía. |

## Publicación y comprobación

Después de publicar el código y desplegarlo en Render, comprobar `/api/propiedades/`, el enlace `siguiente`, precios por operación/moneda, una búsqueda textual y un filtro PostGIS. En HTML comprobar totales, navegación y conservación de parámetros. Los filtros y la paginación por sí solos no requieren ingesta ni reconstruir el índice. Al publicar junto con fotos, sí debe aplicarse `0012` antes de utilizar el código y ejecutar ingesta para cargar las galerías; ver [fotos y publicación](fotos.md).

Esta etapa se entrega localmente, pendiente de publicación y comprobación pública. No se modifican credenciales ni datos durante las pruebas.

## Validación

Suite local: 137 pruebas, 135 aprobadas y dos integraciones PostGIS omitidas en SQLite. Los nuevos casos cubren filtros combinados, cero/NULL, monedas y operaciones distintas, importes inválidos, límites, parámetros repetidos, páginas y enlaces, empate de fechas, paridad HTML/JSON, fallos de servicios y carga acotada de modelos. Un ranking simulado de más de 1.100 IDs comprueba que el filtrado en lotes no trunca las coincidencias tardías.

Comprobación adicional con vistas locales y Supabase/PostGIS/Elastic reales, dentro de una transacción PostgreSQL de solo lectura: recorrido íntegro de 650 ventas (siete páginas de hasta 100) y 121 alquileres (dos páginas), sin pérdidas ni duplicados y con el orden esperado. Consulta combinada de venta, Casa, dos dormitorios, USD hasta 200.000, texto `cochera` y radio de 2 km desde `-31.25,-61.49`, incluyendo aproximadas: 47 coincidencias; las primeras dos páginas coinciden con el ranking filtrado y HTML respondió 200. Los totales espaciales en modo exactas/aproximadas coinciden con PostGIS. Se conservaron las 754 publicaciones y no se escribió en Supabase ni Elasticsearch. Esto valida el código local conectado a servicios reales, no un despliegue nuevo en Render.

Las integraciones PostGIS se ejecutan únicamente en una base de pruebas independiente. No ejecutar `manage.py test` apuntando a Supabase de producción. Ver [instrucciones de pruebas](../AGENTS.md).

Referencias de implementación: [Paginator de Django](https://docs.djangoproject.com/en/6.0/topics/pagination/) y [JsonResponse](https://docs.djangoproject.com/en/6.0/ref/request-response/#jsonresponse-objects).
