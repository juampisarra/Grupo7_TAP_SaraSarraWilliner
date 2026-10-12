# Bajas de publicaciones y mantenimiento de Elasticsearch

Implementado localmente el 12 de octubre de 2026, por decisión del equipo. Pendiente de publicación y primera ejecución productiva. No se cambiaron Supabase ni los índices reales durante esta implementación. No requiere migraciones, dependencias, variables ni Secrets nuevos. Los permisos de la API key sí deben cubrir las operaciones de mantenimiento que se utilicen.

Nota sobre la etapa posterior de fotos: el conjunto actual de cambios sí requiere la migración `0012` antes de ejecutar ingesta; las funciones de mantenimiento por sí solas no cambiaron el esquema. Actions ahora comprueba migraciones pendientes antes de Elasticsearch. Ver [publicación de fotos](fotos.md).

## Publicaciones retiradas: conservar y desactivar por operación

`en_venta` y `en_alquiler` representan disponibilidad vigente. Si un aviso desaparece del listado completo de venta, se desactiva solo `en_venta`; puede seguir en alquiler. Cuando ambos son falsos se conserva la fila como inactiva. No se borran ficha, procedencia, coordenadas, precios ni monedas anteriores. Esos precios conservados no indican disponibilidad: la API expone `disponible` por operación.

Se considera evidencia la presencia en el listado de cada operación, aunque el texto de una tarjeta mencione ambas. Una fuente que solo declara una operación no modifica la otra. Si un aviso reaparece, se reactiva la misma fila por `(fuente, identificador_fuente)`, sin duplicarla. No se incorpora un historial de cambios ni fechas individuales de baja en esta etapa; `actualizada_en` cambia al desactivar.

El importador descarga **todos los listados de la fuente antes de persistir**. Después de persistir sus publicaciones, concilia las ausencias de las operaciones declaradas en una transacción corta:

- Un error de HTTP, esquema, paginación, límite de páginas o persistencia impide llegar a las bajas de esa fuente. Las otras fuentes mantienen su aislamiento y pueden continuar.
- Una interrupción conserva las escrituras previas; no desactiva ausentes antes de completar la persistencia. Las altas o reactivaciones ya guardadas no se revierten.
- Un error recuperable de ficha no es evidencia de baja: si el listado confirma el aviso, sigue vigente y conserva sus detalles anteriores.
- Si hay tarjetas omitidas por falta de identificador o URL, se omiten **todas las bajas de esa fuente** y se informa `Bajas omitidas: 1`. La fuente puede terminar con altas/actualizaciones; revisar también ese contador, no solo el estado verde de Actions.
- Un listado vacío confirmado puede desactivar toda una operación. Un cuerpo desconocido o una página repetida no equivalen a un listado vacío.

Brega y Avantix deben terminar con el marcador `--NoMoreProperties--`: el parser rechaza respuestas sin tarjetas ni marcador. Un identificador repetido durante el recorrido, incluso una superposición parcial, invalida la extracción en lugar de asumir finalización. Gaggiotti ya comprueba el total, los offsets, las páginas pendientes y la ausencia de IDs repetidos. El contrato del adaptador exige devolver un listado completo o lanzar una excepción.

Esta validación reduce bajas por errores de extracción, pero no garantiza una instantánea: Tokko no proporciona un total estable ni un snapshot. Si la fuente cambia mientras se recorren sus páginas, podría omitir avisos sin producir duplicados. La política adoptada aplica la ausencia en una extracción completa; no exige dos ejecuciones consecutivas. No ejecutar ingestas concurrentes contra los mismos servicios.

HTML y JSON filtran disponibilidad en PostgreSQL antes de paginar. Un aviso inactivo queda excluido incluso si un índice anterior todavía devuelve su ID. Al reconstruir, Elasticsearch recibe únicamente publicaciones vigentes en al menos una operación. Una base con filas y todas inactivas produce un índice vacío válido; una base realmente vacía sigue requiriendo `--permitir-vacio` para evitar reemplazos accidentales por una configuración local incorrecta.

## Recuperar el índice sin repetir scraping

Después de publicar `.github/workflows/ingesta.yml`, abrir **Actions → Ingesta Semanal de Propiedades → Run workflow**:

| `modo` | Resultado |
| --- | --- |
| `ingesta` (predeterminado) | Comprueba Elastic, importa las tres fuentes y reconstruye con salida `0` o `3`. Un éxito parcial mantiene el job fallido para avisar. |
| `reconstruir` | Comprueba Elastic y reconstruye desde Supabase. No importa fuentes ni modifica sus publicaciones. |
| `limpiar_indices` | Comprueba Elastic y muestra qué versiones se conservarían o borrarían. No importa ni reconstruye. |

La programación semanal sigue ejecutando `ingesta`. Los tres modos comparten el grupo de concurrencia existente, con `cancel-in-progress: false`: esperan su turno en lugar de ejecutarse simultáneamente. El bloqueo de Actions no alcanza comandos locales ni otros workflows. Un fallo previo de instalación o comprobación impide iniciar el mantenimiento.

Si la ingesta guardó datos pero falló la indexación, corregir la causa y elegir **`modo: reconstruir`**. No hace falta repetir scraping ni redesplegar Render. También puede ejecutarse localmente con un único entorno configurado contra Supabase y Elastic:

```powershell
.\.venv\Scripts\python.exe -X utf8 manage.py reconstruir_indice
```

La carga y el conteo deben completarse antes de cambiar atómicamente el alias. También se registra en `_meta.grupo7` el alias, la finalización, la cantidad y el nombre del índice que atendía antes. Si falla ese registro, no se activa la nueva versión. Si se pierde la respuesta de red durante el cambio del alias, consultar su estado antes de repetir: el servidor podría haberlo aplicado.

No se implementó indexación incremental, reintento automático ni restauración automática de versiones anteriores. La recuperación disponible sigue siendo una reconstrucción completa desde PostgreSQL.

## Limpiar índices: revisar primero

```powershell
# Solo lectura: muestra el plan.
.\.venv\Scripts\python.exe -X utf8 manage.py limpiar_indices

# Ejecuta los borrados elegibles después de revisar la vista previa.
.\.venv\Scripts\python.exe -X utf8 manage.py limpiar_indices --aplicar
```

En Actions elegir `modo: limpiar_indices` y dejar **`aplicar_limpieza` desmarcado** para la vista previa. Para ejecutar los borrados, volver a lanzarlo con esa opción marcada. La opción se ignora en los otros modos. No hay limpieza destructiva semanal automática.

La limpieza conserva el índice activo y su versión anterior registrada. También conserva cualquier índice con otro alias, nombres ajenos al formato estricto del proyecto y versiones posteriores o del mismo segundo que el activo. Solo propone índices más antiguos y sin aliases. Versiones incompletas antiguas también pueden ser candidatas; no se necesitan para recuperar los datos de PostgreSQL.

Antes de cada borrado vuelve a consultar el alias, los metadatos y las protecciones. Si cambió el activo o un candidato dejó de ser elegible, se detiene. Se elimina por nombre concreto, nunca mediante un comodín. Los borrados ya completados no se revierten si falla uno posterior; consultar el inventario y repetir la vista previa. No ejecutar reconstrucción y limpieza simultáneamente fuera de Actions: la revisión no es un bloqueo distribuido.

Si falta una versión anterior registrada en el inventario, también se conserva todo y se pide revisar el estado antes de aplicar borrados.

**Compatibilidad con los índices existentes:** las versiones anteriores a este cambio no registran cuál fue su antecesora. Si el activo no tiene esos metadatos, la vista previa conserva todo y pide reconstruir con el código nuevo; `--aplicar` falla sin borrar. Después de una reconstrucción exitosa, la versión que estaba activa queda identificada y protegida aunque sea antigua. No se deduce una versión de respaldo a partir de la fecha o del conteo.

La API key de reconstrucción requiere crear/escribir/refrescar/contar, gestionar aliases y actualizar mappings. La limpieza requiere consultar mappings/aliases y eliminar índices. Si faltan permisos, falla explícitamente; no modificar las credenciales de lectura del frontend, que nunca se conecta directamente a Elastic.

## Publicación y comprobaciones

1. Publicar el código junto con filtros/paginación/API pendientes. No requiere migraciones ni Secrets nuevos; verificar los permisos de la key usada en Actions.
2. Ejecutar `modo: ingesta` para aplicar las bajas con listados actuales y reconstruir. Revisar por fuente `Bajas venta`, `Bajas alquiler`, `Bajas omitidas` y los errores de detalle. Los registros históricos permanecen en Supabase.
3. Comprobar HTML y JSON, operaciones y filtros. El índice debe coincidir con las publicaciones de PostgreSQL vigentes en alguna operación, no con todas las filas históricas.
4. Probar `modo: reconstruir` cuando se necesite recuperación; no provoca scraping.
5. Ejecutar la vista previa de limpieza. Después de revisar el plan, ejecutar su modo de aplicación si se desea liberar versiones antiguas. Conservar el activo y la versión anterior.

El historial de cron-job.org y la fecha/hora exactas de vencimiento de Elastic siguen requiriendo verificación en sus paneles. La continuidad comercial del servicio después de la prueba sigue sin decidirse; este mantenimiento no extiende su vigencia.

## Validación del 12 de octubre

- Suite local: 164 pruebas, 162 aprobadas y dos integraciones PostGIS omitidas con SQLite. Bases de prueba efímeras; no crear una base de pruebas en Supabase.
- Bajas independientes, reaparición sin duplicados, conservación de precios/ficha/coordenadas, listado vacío confirmado, error de listado, persistencia parcial, fallo de conciliación con rollback, tarjetas omitidas y errores de detalle.
- Exclusión en HTML/JSON aun con IDs antiguos de Elastic; reconstrucción solo de vigentes; base vacía protegida y base histórica totalmente inactiva.
- Vista previa sin borrados, aplicación por nombre, protección de aliases/antecesor/formatos/nuevas versiones, cambio de alias o protecciones durante la limpieza, metadatos ausentes, antecesor perdido y fallos de red/respuesta.
- `actionlint` 1.7.12 validó el workflow. Sin migraciones pendientes ni dependencias rotas.
- Lectura real de Brega: 136 ventas y 38 alquileres; Avantix: 250 y 35. Los recorridos completos pasaron el parser endurecido. Comparación en transacciones PostgreSQL de solo lectura: dos alquileres Brega candidatos a baja; cero candidatos en las demás operaciones consultadas. No se aplicaron cambios ni se solicitaron fichas.
- Vista previa real de Elastic: siete índices, activo `propiedades-20261012101143-5ac7ed47`; falta el metadato de antecesor, por lo que conservó todo sin candidatos ni borrados. No se ejecutaron reconstrucciones ni se escribieron metadatos en el servicio real. La aplicación de limpieza y los modos de Actions quedan pendientes de comprobar después de publicar.

Referencias: [metadatos del mapping de Elasticsearch](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/mapping-meta-field), [actualizar mappings](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-indices-put-mapping) y [entradas de ejecución manual de Actions](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onworkflow_dispatchinputs).
