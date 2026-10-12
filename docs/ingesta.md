# Ingesta y tolerancia a fallos por fuente

Implementado localmente el 11 de octubre de 2026 y publicado el 12 de octubre. El [workflow manual](https://github.com/juampisarra/Grupo7_TAP_SaraSarraWilliner/actions/runs/38213432407) completó las tres fuentes y la reconstrucción correctamente, sin errores de detalle. El aislamiento ante fallo parcial/total está cubierto por pruebas locales; no se provocó una caída de fuente en producción. No requiere migraciones, nuevas dependencias, variables ni Secrets.

## Ejecución

```powershell
.\.venv\Scripts\python.exe manage.py importar_propiedades
```

Procesa las fuentes registradas en orden alfabético: Avantix, Brega y Gaggiotti. También admite `importar_propiedades avantix`, `importar_propiedades brega`, `importar_propiedades gaggiotti` y el alias `importar_brega`. La opción `--completar-ubicacion` se transmite a cada fuente seleccionada. Las tres fuentes están verificadas en producción; ver [adaptador y validación de Gaggiotti](gaggiotti.md).

Cada fuente se ejecuta de forma independiente. Si falla su inicialización, listado, paginación o ingesta, se informa el nombre, tipo de excepción y causa por stderr, y se continúa con la siguiente. Al terminar se enumeran las fuentes completadas y fallidas. No se capturan interrupciones del proceso como Ctrl+C o `SystemExit`.

El resumen de una fuente completada conserva los conteos anteriores. Los errores recuperables de fichas individuales siguen contándose en `Errores detalle` y no convierten por sí solos a toda la fuente en fallida. «Completada» significa que terminó el flujo; no garantiza que todas sus fichas se hayan podido refrescar.

`Detalles solicitados` cuenta llamadas al adaptador. Gaggiotti reutiliza la ficha completa recibida en el listado de esa misma ejecución y evita una solicitud HTTP adicional por aviso.

## Resultado del comando y del workflow

| Situación | Código de salida | Reconstrucción en Actions | Estado final del job |
| --- | --- | --- | --- |
| Todas las fuentes seleccionadas completadas | `0` | Sí | Exitoso si también termina la reconstrucción. |
| Al menos una completada y alguna fallida | `3` | Sí, desde lo guardado en PostgreSQL | Fallido, aunque el índice se actualice. |
| Todas las fuentes seleccionadas fallidas | `1` | No | Fallido. |
| Registro vacío, fallo de preparación o error sin resultado parcial | Error | No | Fallido. |
| Cancelación del workflow | Cancelado | No se inicia la reconstrucción | Cancelado. |

La salida `3` está reservada al resultado parcial; no se utiliza `2`, habitual para errores de argumentos. Importar una única fuente que falla devuelve `1`. En PowerShell se puede consultar `$LASTEXITCODE` inmediatamente después de ejecutar el comando.

El paso `ingesta` del workflow registra el código en `GITHUB_OUTPUT` y termina con ese mismo código. El paso del índice comprueba explícitamente `0` o `3` y que no haya cancelación. No se usa `continue-on-error`: un fallo parcial permanece visible como ejecución fallida aun cuando se reconstruya correctamente el índice. Si falla la comprobación previa de Elasticsearch o la instalación, la ingesta no empieza y tampoco se reconstruye.

La condición utiliza una función de estado para permitir la reconstrucción después del paso fallido, según la [documentación de expresiones de GitHub Actions](https://docs.github.com/en/actions/reference/workflows-and-actions/expressions#status-check-functions). Las notificaciones que reciba cada integrante dependen de sus preferencias en GitHub.

## Qué ocurre con los datos

No se borran publicaciones ni se revierte toda la ejecución. El importador descarga los listados de una fuente antes de comenzar a persistirla: un fallo de listado o paginación conserva sus datos anteriores. Si el fallo ocurre después de haber guardado algunas publicaciones, esas escrituras también se conservan.

La reconstrucción lee la base completa. Después de un fallo parcial, incluye datos nuevos de las fuentes completadas y datos conservados de las demás, incluidas escrituras parciales que hayan llegado a guardarse. No afirma que todo esté actualizado. Si todas fallan, se mantiene el índice anterior hasta una reconstrucción posterior.

La protección existente del índice rechaza una base vacía y activa la nueva versión solo después de validar la carga. Los fallos previos al cambio del alias conservan la versión anterior. Ante un error de red durante el cambio del alias, comprobar su estado: el servidor puede haber aplicado el cambio. Ver [Elasticsearch](elasticsearch.md).

## Recuperación

1. Revisar el log de **Ejecutar ingesta**: identificar la fuente y la causa, y leer el resumen final.
2. Revisar si **Reconstruir índice de Elasticsearch** terminó correctamente o fue omitido.
3. Corregir la causa y reejecutar el workflow, o importar solo la fuente fallida y luego reconstruir el índice manualmente.

```powershell
.\.venv\Scripts\python.exe manage.py importar_propiedades avantix
# Después de comprobar que terminó correctamente:
.\.venv\Scripts\python.exe manage.py reconstruir_indice
```

Evitar ingestas locales simultáneas con Actions y escrituras durante una reconstrucción. Repetir una ingesta conserva la identidad por fuente e identificador y no crea duplicados por repetir la carga. No se agregan reintentos automáticos ni se resuelve aquí la política de publicaciones retiradas.

## Validación

- Suite final, incluida Gaggiotti: 117 pruebas, 116 aprobadas y una integración PostGIS omitida al usar SQLite.
- Casos nuevos: fallo de la primera o última fuente, todas fallidas, inicialización fallida, fuente específica, alias Brega, propagación de opciones, interrupciones, registro vacío, errores de ficha y código real de salida del comando.
- Prueba con el importador y SQLite efímero: se conservan publicaciones anteriores de la fuente fallida, se guarda la otra fuente y se repite sin duplicados.
- Script Bash del workflow ejecutado localmente con un comando simulado: conserva y comunica los códigos `0`, `3`, `1` y `130`.

Las pruebas de aislamiento usan servicios simulados y base efímera; no modifican Supabase o Elasticsearch. La validación separada de Gaggiotti incluyó solicitudes públicas reales y repetición de sus respuestas capturadas en una base efímera. El 12 de octubre se publicó el código y el workflow completó la ingesta productiva y reconstrucción: 754 documentos, iguales a PostgreSQL. Los detalles están en la guía de Gaggiotti.
