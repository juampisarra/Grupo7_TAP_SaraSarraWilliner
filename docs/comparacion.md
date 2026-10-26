# Comparación de publicaciones

Implementación local del 25 de octubre de 2026. El usuario autorizó desarrollar el plan de selección, tabla y análisis con Gemini. No se hizo commit, push ni despliegue, ni se aplicaron migraciones a Supabase. La integración con Gemini está probada mediante respuestas simuladas; falta la prueba real con una cuenta y modelo configurados. La revisión visual de escritorio y celular quedó pendiente: Computer Use se detuvo porque no pudo determinar con suficiente certeza la URL activa de Chrome; no se continuó con la automatización ni se buscó eludir el bloqueo.

## Uso

1. Abrir `/propiedades/mapa/` y buscar como hasta ahora.
2. Pulsar «Agregar a comparación» en tarjetas de la lista o en la ficha del mapa.
3. Seleccionar entre dos y cuatro publicaciones y pulsar «Comparar propiedades».
4. Consultar la tabla y, opcionalmente, pulsar «Generar análisis con IA».

La selección se conserva en memoria al cerrar la ficha, ordenar, filtrar o hacer otra búsqueda de la misma operación. Puede contener publicaciones que ya no aparecen en los resultados nuevos. Cambiar entre alquiler y venta la limpia inmediatamente con un aviso; recargar la página también la pierde. Los avisos de distintas fuentes conservan sus IDs: compartir dirección o punto no prueba que sean el mismo inmueble.

La selección inicial utiliza la lista y ficha existentes, que muestran propiedades con coordenadas. El endpoint comparativo no exige coordenadas: admite IDs válidos y representa su ausencia sin inventar ubicación. No se amplió el alcance del listado del mapa para incluir avisos sin ubicación.

El comparador es un diálogo nativo, con título, cierre, Escape, foco contenido y tabla desplazable horizontalmente. Cerrarlo cancela la espera del navegador y conserva búsqueda y selección; una solicitud ya recibida en Django puede terminar y quedar cacheada. Las respuestas tardías no reemplazan una selección nueva. Hay controles para quitar publicaciones y actualizar la tabla tras cambios o errores.

## Datos y reglas

La tabla se obtiene siempre de `Propiedad` en PostgreSQL o SQLite, conservando el orden pedido. Incluye foto de portada, título, tipo, fuente, dirección/zona/ciudad/provincia, precio y moneda de la operación, dormitorios y su verificación, ambientes, baños, características textuales, precisión, actualización en el observatorio y enlace original.

- NULL y texto vacío se presentan como «No informado», distintos de cero y de ausencia de una comodidad.
- Se comparan precios solo cuando **todas** las publicaciones tienen precio y la misma moneda conocida. La diferencia con el menor precio se calcula en Python con `Decimal`, no con el LLM. No hay conversiones de moneda.
- No hay superficies estructuradas en el modelo; no se calculan m² ni precio/m².
- Se preservan ubicación aproximada, desconocida, geocodificada y ausencia de coordenadas. No se calculan distancias ni se afirma calidad de barrios.
- Los textos de avisos y del análisis se insertan mediante `textContent`. Los enlaces y fotos nuevos del comparador solo aceptan HTTP/HTTPS.

No se consulta Elasticsearch, no se duplican filtros espaciales, no se hace scraping y no se modifica ninguna publicación para comparar.

## Configuración

La tabla funciona sin Gemini. Para generar análisis:

1. Aplicar las migraciones en la base elegida: `python manage.py migrate`. La nueva `0015_comparaciongenerada_usocomparacion` depende de `0014_comentario` y crea únicamente caché y contadores. No cambia los datos inmobiliarios.
2. Configurar `GEMINI_API_KEY` y `GEMINI_MODEL` en `.env` local y, al publicar, en Environment de Render.
3. Elegir un modelo de texto disponible para la cuenta, con generación estructurada JSON Schema y cuota gratuita verificada. No se fija un modelo por defecto ni se asume gratuidad para cualquier modelo.
4. Reiniciar Django. En producción ejecutar también `python manage.py collectstatic --noinput` mediante el flujo de despliegue existente.
5. Hacer una comparación real pequeña y comprobar calidad, demora y consumo en AI Studio antes de la presentación.

No pegar claves en el código, frontend o documentación. La configuración no se exige para arrancar Django, health, búsquedas o jobs. No se agregaron dependencias: el cliente utiliza `requests` existente, por REST con HTTPS, sin redirecciones ni reintentos automáticos. El timeout de conexión es de 3 segundos y el de lectura de 20 segundos. La espera del navegador para IA es de 30 segundos.

Referencias consultadas: [modelos](https://ai.google.dev/gemini-api/docs/models), [precios y uso de contenido](https://ai.google.dev/gemini-api/docs/pricing), [cuotas del proyecto](https://ai.google.dev/gemini-api/docs/rate-limits) y [salidas estructuradas](https://ai.google.dev/gemini-api/docs/structured-output). Las cuotas efectivas se verifican en AI Studio; la API tiene límites por proyecto, no por cada clave.

## Contrato HTTP

### Tabla

`GET /api/propiedades/comparacion/?ids=12,34&operacion=alquiler`

`ids` y `operacion` deben aparecer una vez. Entre 2 y 4 IDs enteros positivos, sin duplicados; operación `alquiler` o `venta`. Devuelve `propiedades`, `operacion`, `precios_comparables`, `firma` e `ia_disponible`. La firma identifica los datos de la tabla, independientemente del orden visual.

### Análisis

`POST /api/propiedades/comparacion/analisis/`, con CSRF y `Content-Type: application/json`:

```json
{"ids": [12, 34], "operacion": "alquiler", "firma": "firma-recibida-en-la-tabla"}
```

Máximo 4096 bytes. No acepta campos extra ni precios o características del cliente. Django recupera los datos, comprueba la firma, obtiene el análisis y vuelve a validar disponibilidad y firma antes de responder. Si la ingesta cambió la instantánea, se requiere actualizar la tabla.

Respuesta: `analisis`, `firma`, `modelo`, `generado_en` y `reutilizado`. El análisis contiene resumen, diferencias, ventajas/limitaciones por `propiedad_id`, datos faltantes y conclusión condicional. Se valida la estructura, cantidad de elementos, longitud y correspondencia exacta de IDs. Una estructura correcta no garantiza exactitud factual: requiere revisión de calidad y aviso visible al usuario.

Errores JSON: `error`, `codigo`, `ids` afectados cuando corresponda. Estados: 400 datos inválidos, 403 CSRF, 404 publicaciones ausentes, 409 retiradas/datos cambiados/generación en curso, 429 límites y 503 falta de configuración/fallo de Gemini. Métodos no admitidos: 405. Ambos endpoints impiden caché HTTP de las respuestas.

## Datos enviados al proveedor

Solo operación, comparabilidad, ID, tipo, ciudad, precio/moneda y diferencia calculada, dormitorios/verificación, ambientes, baños, precisión y hasta 1600 caracteres de características por publicación. Se quitan etiquetas HTML y patrones reconocibles de emails, enlaces y teléfonos del texto antes de enviarlo. Este filtrado no equivale a anonimización universal del lenguaje libre.

No se envían descripciones completas, títulos, direcciones, fotos, coordenadas, comentarios, alias ni datos del visitante. Los textos externos se presentan como datos no confiables y el prompt indica ignorar sus instrucciones. No se habilitan herramientas, navegación, mapas ni grounding. La interfaz informa que los datos acotados se envían a Google al solicitar IA y que el nivel gratuito puede utilizarlos para mejorar productos.

## Caché, concurrencia y límites

`ComparacionGenerada` conserva solo resultado, modelo, huella, fecha, vencimiento y token de reserva; no guarda un historial de búsquedas o visitantes. La caché dura 24 horas y se identifica por datos efectivamente enviados, operación, modelo y versión del prompt. Cambiar esos datos invalida la reutilización; reordenar columnas no consume otra llamada.

Una reserva de 60 segundos evita llamadas simultáneas para el mismo conjunto. Se adquiere mediante clave única y actualización condicional; se libera al fallar y puede recuperarse tras vencimiento si el proceso se interrumpió. El token evita que un proceso anterior sobrescriba o borre una reserva posterior. No hay transacciones abiertas durante HTTP.

`UsoComparacion` aplica contadores compartidos con actualizaciones atómicas: inicialmente **2 generaciones nuevas/minuto por visitante, 5/minuto globales y 100/día UTC globales**. Se configuran en settings y deben ajustarse a la cuota real de la cuenta. Los intentos que llegan al proveedor cuentan aunque fallen. Los aciertos de caché no consumen generación. El día de la aplicación no coincide necesariamente con el reinicio de cuota de Google.

El visitante usa una cookie aleatoria firmada, HttpOnly, SameSite=Lax y Secure en producción, con un día de vigencia. Sin cookie válida se deriva un identificador con HMAC de la conexión; no se confía en cabeceras de IP arbitrarias. La cookie no es autenticación: puede eliminarse para renovar el límite individual; el límite global sigue aplicándose. No es una protección completa frente a ataques distribuidos o tráfico masivo. Registros de uso vencidos y cachés antiguas se limpian al solicitar análisis.

No se agregan Redis, Celery, cuentas de usuario ni workers externos.

## Verificación

Pruebas con SQLite temporal y Gemini simulado; no ejecutan solicitudes al proveedor:

```powershell
$env:DB_ENGINE='sqlite'
.\.venv\Scripts\python.exe manage.py collectstatic --noinput
.\.venv\Scripts\python.exe manage.py test --noinput
node scripts/test_comparador.cjs
node scripts/test_panel_resultados.cjs
node scripts/test_mapa_coordenadas.cjs
node scripts/test_comentarios_ficha.cjs
```

Las pruebas cubren validación, precisión decimal, monedas/ausencias, fuentes distintas en la misma dirección, datos cambiados antes y durante IA, CSRF, caché, cuotas, reservas, liberación tras fallos, payload acotado, cliente REST y errores del proveedor. Node cubre selección/límite, persistencia entre búsquedas, ficha, tabla, cancelación, respuestas tardías, errores y texto seguro.

Resultado final: 243 pruebas Django, 241 aprobadas y dos integraciones PostGIS omitidas con SQLite; las cuatro pruebas Node aprobadas. `check`, `makemigrations --check --dry-run`, `collectstatic` y `git diff --check` correctos.

Pendiente antes de publicar: revisión visual real en escritorio y celular, aplicar migración en el entorno objetivo, elegir/configurar modelo y hacer una prueba real acotada de Gemini.
