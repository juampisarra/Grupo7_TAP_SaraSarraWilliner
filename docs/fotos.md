# Fotos de las propiedades

Implementado localmente el 12 de octubre de 2026 por solicitud del equipo. Pendiente de publicación, migración `0012` y primera ingesta productiva que cargue las galerías. No se cambiaron Supabase ni Elasticsearch. Se guardan **URLs externas**, sin descargar o alojar copias, sin nuevos servicios, variables, Secrets ni dependencias.

Plan ejecutado: relevar galerías reales de las tres fuentes, definir validación/orden, agregar persistencia y migración, exponer HTML/JSON, probar fallos y actualización, y documentar la publicación.

## Datos y actualización

`Propiedad.fotos` es un `JSONField` con una lista ordenada de URLs HTTPS, sin duplicados. La primera es la portada; `foto_portada` es una propiedad calculada que devuelve esa URL o `None`. No se duplica la portada en otra columna ni se agrega una tabla que requiera consultas por cada resultado. `default=list` genera listas independientes; las filas existentes reciben `[]` con la migración. Esa lista inicial significa que no hay fotos guardadas, no que se haya comprobado una galería vacía.

Se valida sin descargar imágenes ni resolver DNS: formato HTTPS, sin credenciales, espacios ni barras invertidas; se rechazan localhost y direcciones IP literales no públicas. Se resuelven rutas relativas con la URL base de cada fuente y URLs que empiezan por `//`. Se conserva la query; se quita el fragmento y se deduplican enlaces idénticos conservando el orden. HTTP no se convierte arbitrariamente a HTTPS; se considera no verificable para evitar enlaces inseguros en el sitio HTTPS. No se comprueba la existencia de cada archivo durante la ingesta.

El contrato `DetallesPropiedad.fotos` distingue:

| Valor | Comportamiento |
| --- | --- |
| `None` | Galería ausente, desconocida o inválida: conserva las fotos guardadas. |
| `[]` | Galería explícitamente vacía y reconocida: limpia las fotos anteriores. |
| Lista válida | Reemplaza la galería completa y su orden, sin acumular enlaces antiguos. |

Se actualizan mediante la ficha que ya obtiene el importador común. No hay consultas HTTP adicionales para recogerlas ni en las visitas de los usuarios. Un error HTTP o de ficha conserva las fotos anteriores. Una galería inválida devuelve `None` con una advertencia y permite actualizar el resto de los detalles; no entrega una lista parcial que pueda borrar fotos válidas anteriores.

La retirada de una publicación conserva sus fotos junto con la ficha. Si reaparece, se actualiza la misma fila. Un cambio del enlace de portada no crea otra publicación. Las fotos no se agregan al documento ni a los filtros de Elasticsearch.

## Extracción por fuente

**Brega y Avantix:** parser común Tokko sobre `#ficha_slider .slides`, con sus elementos `li` y una `img.zoomImg` por elemento. Conserva el orden del HTML; toma `data-src` si está presente y, en su defecto, `src`. No importa logos, iconos, mapas, imágenes de avisos recomendados, miniaturas de otra sección ni Open Graph. La primera imagen es portada por orden de la galería: no se inventa una marca explícita que estas fichas no publican.

Un contenedor reconocido sin elementos es una galería vacía. La ausencia de ese contenedor, varias galerías ambiguas, una estructura distinta, una imagen sin URL o una URL inválida dejan `fotos=None`. No se usa una única imagen Open Graph como sustituto de una galería completa anterior.

**Gaggiotti:** lee `photos` de la ficha JSON que ya devuelve `Search`. Usa `image`, no descarga `original` ni `thumb`. Respeta `isFrontCover` y después `order`; los empates mantienen la posición original. Si no hay portada explícita, usa la primera por orden. Varias portadas, orden inválido, esquema desconocido o URL inválida conservan la galería anterior. `photos=[]` confirma ausencia; campo ausente o `null` no autoriza borrar. Se conservan todas las imágenes de la galería, incluidos planos si están publicados dentro de ella.

## API y listado de prueba

Cada resultado de `/api/propiedades/` agrega:

```json
{
  "fotos": [
    "https://cdn.ejemplo.com/propiedades/123/portada.jpg",
    "https://cdn.ejemplo.com/propiedades/123/patio.jpg"
  ],
  "foto_portada": "https://cdn.ejemplo.com/propiedades/123/portada.jpg"
}
```

Sin fotos: `"fotos": []` y `"foto_portada": null`. Son campos adicionales: filtros, relevancia, paginación, procedencia y precios conservan su contrato. El JSON devuelve la galería completa de las propiedades de la página; volúmenes mayores podrían requerir una respuesta resumida para el listado.

El HTML existente muestra únicamente una portada de prueba, con `loading="lazy"`, texto alternativo y `referrerpolicy="no-referrer"`. `propiedades/fotos.js` sustituye imágenes fallidas por «Foto no disponible»; sin enlaces guardados muestra «Sin fotos disponibles». No se implementó un frontend definitivo ni una galería interactiva.

El navegador solicita los archivos al servidor de imágenes original. Su disponibilidad y política de acceso pueden cambiar; una URL guardada no garantiza carga permanente. Se mantienen la inmobiliaria de origen y el enlace al aviso. No se implementa un proxy ni almacenamiento de archivos en Render o Supabase Storage.

## Publicar y cargar fotos

1. Publicar el código y esperar a que Render complete el build, que ya ejecuta `collectstatic` y `migrate`. **Esta etapa sí requiere `0012_propiedad_fotos`**, a diferencia de filtros y mantenimiento anteriores. Ver [despliegue](despliegue.md).
2. Comprobar que `0012` esté aplicada antes de ejecutar ingesta. El workflow ahora ejecuta `migrate --check` antes de comprobar Elasticsearch: si falta una migración, falla antes de pedir listados o escribir publicaciones. No aplica migraciones automáticamente desde Actions.
3. Ejecutar el workflow con `modo: ingesta` para las tres fuentes. La ingesta también aplica la política local de bajas por operación; revisar todos los resúmenes. Una reconstrucción sola no recoge fotos: no consulta las inmobiliarias. Las fotos no requieren cambiar el mapping de Elasticsearch; el workflow reconstruye como parte del flujo existente.
4. Consultar `/api/propiedades/?operacion=venta&por_pagina=5` y comprobar `fotos`, `foto_portada`, procedencia y orden. Verificar una portada de cada fuente en el listado HTML. Si una ficha falló, sus fotos anteriores se conservaron y las nuevas se podrán recoger en la próxima ingesta.

Para un entorno local independiente configurado mediante `.env`:

```powershell
.\.venv\Scripts\python.exe -X utf8 manage.py migrate
.\.venv\Scripts\python.exe -X utf8 manage.py collectstatic --noinput
# Importa y escribe en la base seleccionada; evitar concurrencia con Actions.
.\.venv\Scripts\python.exe -X utf8 manage.py importar_propiedades
```

Comprobar `DB_ENGINE` antes de ejecutar esos comandos. No ejecutar ingestas locales y Actions al mismo tiempo. Las filas no se rellenan automáticamente con fotos durante la migración: comienza con listas vacías y se completa al ingerir.

## Validación

Suite final: 182 pruebas, 180 aprobadas y dos integraciones PostGIS omitidas con SQLite. Sin cambios de modelo fuera de las migraciones creadas ni dependencias rotas. `collectstatic` generó el script con manifiesto; se comprobó su sintaxis y el reemplazo ante errores previos/posteriores a registrar el evento. `actionlint` validó el workflow actualizado. Preparar el manifiesto con `collectstatic --noinput` antes de ejecutar la suite con DEBUG=False, como indica AGENTS.md.

- Pruebas locales de URLs, orden, portada, duplicados, relativas/lazy load, exclusión de imágenes ajenas, ausencia/vacío, esquema inválido, preservación ante errores, reemplazo de galería, retirada/reaparición, API y HTML. Los documentos de Elasticsearch siguen sin imágenes.
- Extracción real de tres fichas Brega (18, 18 y 15 fotos) y tres Avantix (10, 8 y una foto), sin persistencia productiva. Una portada por fuente respondió HTTP 200 `image/jpeg` sin Referer; también se comprobó una de Gaggiotti. Es una muestra de acceso, no una garantía de toda la galería.
- Extracción completa real de Gaggiotti: 306 publicaciones, 4.774 fotos y ninguna galería desconocida o vacía en esa revisión. Se reutilizaron las fichas de `Search`, sin GET adicional por aviso.
- Reproducción de esas respuestas en SQLite en memoria: seis fichas Brega/Avantix y 306 Gaggiotti persistidas; repetición sin duplicados y validación de campos con `full_clean`. Se probaron `0011 → 0012`, conservación de una fila previa y su nueva lista vacía. No se modificó `db.sqlite3`, Supabase ni Elasticsearch.

Referencia de almacenamiento: [JSONField de Django](https://docs.djangoproject.com/en/6.1/ref/models/fields/#jsonfield).
