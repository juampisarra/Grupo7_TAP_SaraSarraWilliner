# Diagnóstico y enriquecimiento de coordenadas

Implementación local del 12 de octubre de 2026, pendiente de publicar y aplicar `0013_evidencia_coordenadas`. No se corrigieron publicaciones productivas ni se escribió en Supabase/Elasticsearch. El usuario aprobó la propuesta de diagnóstico, validación conservadora, conservación del original y representación honesta en el mapa.

## Plan ejecutado

1. Revisar ingesta, fuentes, PostGIS y mapa; auditar los datos actuales sin escribir.
2. Separar punto original y mejora por dirección, con procedencia y caché.
3. Agregar diagnóstico y comandos explícitos de vista previa, consulta, aplicación y reversión.
4. Conservar las mejoras entre ingestas y descartarlas cuando cambia la evidencia.
5. Agrupar avisos con el mismo punto en el mapa, mostrar precisión y verificar/documentar.

## Qué se considera sospechoso

El diagnóstico recorre todas las publicaciones vigentes en venta o alquiler, sin depender de las páginas cargadas por el mapa. Agrupa por fuente, ciudad, provincia y coordenadas **idénticas**, sin redondear. Por defecto exige al menos cinco publicaciones y cinco puertas diferentes reconocibles (calle + altura). Varias unidades de un edificio con la misma puerta cuentan como una dirección. `--umbral` permite ajustar ambos mínimos; no se admite menos de dos.

También marca puntos cuyo método publicado es `APPROXIMATE` o `GEOMETRIC_CENTER`, aunque no estén repetidos. Gaggiotti ahora conserva `gmLocationType` en `metodo_ubicacion_fuente`; los otros valores no prueban exactitud ni disparan por sí solos una corrección. Después del despliegue, una ingesta obtiene esta evidencia para las filas anteriores. El diagnóstico puede ejecutarse antes usando únicamente las repeticiones históricas.

Un punto sospechoso no se declara incorrecto automáticamente. Las coordenadas originales permanecen disponibles incluso después de mejorar el punto efectivo.

## Dirección y aceptación

Solo se consulta con ciudad explícita y calle/altura inequívocas. No se usan ciudades o provincias obtenidas por enriquecimiento inverso para justificar la nueva consulta. Se reconocen unidades separadas por Piso/Dpto/Oficina y algunos ordinales; se rechazan esquinas, referencias, rutas, lotes, edificios sin calle, rangos, alturas aproximadas y sufijos no reconocidos. `9 de Julio` no es una altura; `9 de Julio 829` sí. El criterio es conservador: algunas direcciones válidas necesitarán revisión manual.

La consulta estructurada pide hasta cinco candidatos, Argentina y detalles de dirección. Para aceptar exige:

- Resultado de casa/edificio o altura, nunca solamente calle, barrio o ciudad.
- País, localidad, calle y altura coincidentes; provincia también si se conoce.
- Coordenadas finitas dentro de rango.
- Una única coincidencia válida. Si se satura el límite de cinco candidatos, se rechaza por ambigüedad.

Se normalizan mayúsculas, tildes y abreviaturas controladas (Av., Bv., Gral., Sta., Sto.). **No se equipara automáticamente Brown con Almirante Brown**, ni se usan coincidencias parciales o fuzzy. Una respuesta insuficiente o un error conserva el punto anterior y permite continuar con otros avisos.

Incluso una altura coincidente puede ser interpolada. El resultado se identifica como `geocodificada_direccion`, con `ubicacion_aproximada=NULL` y sin radio inventado. No se promueve a exacto ni se garantiza la puerta real. Ver [formato de resultados de Nominatim](https://nominatim.org/release-docs/latest/api/Output/) y [búsqueda estructurada](https://nominatim.org/release-docs/latest/api/Search/).

## Persistencia y sincronización

La migración `0013` agrega:

| Elemento | Función |
| --- | --- |
| `Propiedad.coordenadas_fuente` | Punto original, precisión, radio y método publicado; las filas históricas comienzan con `{}`. |
| `Propiedad.metodo_ubicacion_fuente` | Evidencia de cómo obtuvo la fuente su marcador, cuando la publica. |
| `Propiedad.geocodificacion` | Resultado aplicado, referencia OSM, proveedor, firma de dirección, original, versión y fecha. |
| `ConsultaDireccion` | Caché persistente por consulta, proveedor y versión del validador, incluidos negativos y errores. |

`latitud`/`longitud` siguen siendo el punto efectivo. PostgreSQL deriva de ellos la columna PostGIS existente; todos los filtros espaciales continúan en PostGIS. Las mejoras requieren `incluir_aproximadas=1` en filtros geográficos, igual que otros puntos de precisión desconocida. No se agregan coordenadas a Elasticsearch ni hace falta reconstruirlo por una corrección de ubicación.

Una ingesta conserva la mejora si dirección/ciudad/provincia/zona y punto/precisión/radio originales siguen iguales. Incorporar o actualizar solamente el método publicado no invalida una mejora: permite enriquecer filas históricas antes de la primera ingesta con 0013. Un cambio invalida la mejora y vuelve a la política de la fuente; si falta la nueva ubicación se aplican las reglas previas de invalidación/geocodificación. Un error de ficha mantiene lo guardado. No se geocodifican puntos sospechosos automáticamente durante la ingesta.

La aplicación revalida la fila después del HTTP y usa bloqueo de fila durante una escritura corta. La ingesta vuelve a leer y concilia bajo bloqueo antes de persistir, evitando pisar una mejora aplicada mientras descargaba la ficha. No se mantiene una transacción abierta durante llamadas externas. Estos bloqueos protegen los datos, **no coordinan las cuotas del proveedor entre procesos**.

## Uso responsable del proveedor

La [política del servidor público de Nominatim](https://operations.osmfoundation.org/policies/nominatim/) exige caché, identificación de la aplicación, atribución y un único proceso/máquina para lotes pequeños. Las tareas periódicas tienen máximo **cuatro consultas por minuto**; la geocodificación masiva regular está desaconsejada. El limitador compartido por geocodificación directa e inversa espera al menos 15,1 segundos entre comienzos de solicitudes y no realiza reintentos automáticos.

La caché del nuevo enriquecimiento dura 30 días para resultados/negativos y 24 horas para errores. El respaldo experimental de direcciones ausentes en la fuente también se cachea, con un contrato separado: su resultado no acredita una altura ni recibe la clasificación del validador estricto. No se consulta el proveedor desde visitas, filtros, health ni solicitudes de API.

No ejecutar ingesta y enriquecimiento locales simultáneamente, ni junto a Actions. Sus modos de Actions comparten el grupo de concurrencia existente. Para uso regular de mayor volumen, utilizar un proveedor compatible o instancia propia, configurable sin cambiar código mediante `NOMINATIM_DOMAIN` (solo hostname, HTTPS) y `NOMINATIM_USER_AGENT`. En Actions son Repository Variables opcionales del mismo nombre; en Render/local son variables de entorno. Los valores predeterminados identifican este repositorio; no se necesitan nuevos Secrets ni dependencias.

## Comandos

Ejemplos con el entorno Django configurado. Verificar primero `python manage.py migrate --check`; el comando no aplica migraciones.

```powershell
# Diagnóstico: solo lectura, sin HTTP ni caché nueva.
python manage.py diagnosticar_coordenadas --fuente Gaggiotti

# Vista previa de un lote: tampoco consulta ni escribe.
python manage.py enriquecer_coordenadas --fuente Gaggiotti --limite 10

# Consultar y guardar caché; NO modifica publicaciones.
python manage.py enriquecer_coordenadas --fuente Gaggiotti --limite 10 --consultar

# Consultar/reutilizar caché y aplicar exclusivamente resultados aceptados.
python manage.py enriquecer_coordenadas --fuente Gaggiotti --limite 10 --aplicar

# Continuar otro lote con IDs mayores al último procesado, incluso si fue rechazado.
python manage.py enriquecer_coordenadas --fuente Gaggiotti --desde-id 664 --limite 10 --consultar

# Ver original y mejora antes de revertir un aviso; usar el ID real deseado.
python manage.py restaurar_coordenadas --id 625
python manage.py restaurar_coordenadas --id 625 --aplicar
```

Omitir `--fuente` incluye todas las fuentes. Los IDs son ejemplos: revisar el diagnóstico actual. `--limite` admite 1–100; por defecto 10. La consulta y la aplicación son alternativas excluyentes; aplicar ya implica consultar. Las filas ya enriquecidas se omiten. Restaurar conserva la evidencia original y la caché: otro enriquecimiento puede volver a proponer el resultado.

Cada candidato informa ID, motivo, estado, resultado propuesto y si se aplicó. Un job exitoso **no significa que todos se corrigieron**: `ambiguo`, `sin_resultado`, `error` y `aplicado: false` requieren revisar el resumen. El cursor evita que los primeros casos no resueltos impidan procesar lotes posteriores.

## Publicación y Actions

1. Publicar el código y esperar Render. Su build debe aplicar `0013_evidencia_coordenadas` y ejecutar `collectstatic`.
2. Verificar health, API y mapa; `ubicacion_info` debe aparecer en cada resultado JSON.
3. Ejecutar el workflow con `modo=diagnosticar_coordenadas`, `fuente_coordenadas=Gaggiotti`.
4. Para cargar también métodos originales, ejecutar primero la ingesta normal y esperar su finalización.
5. Ejecutar `modo=enriquecer_coordenadas`, límite 10, `consultar_coordenadas=true`, `aplicar_coordenadas=false`. Revisar coincidencias y rechazos; solo escribe caché.
6. Ejecutar ese mismo lote con `aplicar_coordenadas=true`. Reutiliza caché y aplica resultados válidos; esta opción tiene prioridad sobre consultar.
7. Verificar punto efectivo, original, etiqueta de precisión y filtros PostGIS con aproximadas. Luego continuar lotes con `desde_id_coordenadas` si corresponde.

En ambos modos las opciones de limpieza no tienen efecto. Con consultar/aplicar desmarcados, enriquecimiento es una vista previa sin HTTP/escrituras. La programación semanal sigue haciendo solamente ingesta/reconstrucción: no agrega consultas de enriquecimiento ni correcciones automáticas. Los modos de coordenadas comprueban migraciones y no dependen de Elasticsearch.

## API y mapa

La API agrega `ubicacion_info` con `origen`, `precision`, `metodo_fuente`, `punto_original` y `atribucion`. Las referencias OSM, firma interna y caché quedan en el backend. Los campos anteriores de coordenadas y precisión se conservan.

El mapa agrupa coordenadas exactamente iguales entre los avisos cargados y permite elegir uno mediante una lista. No desplaza los puntos ni redondea para agrupar. La tarjeta distingue ubicación desconocida, aproximada, tratada como exacta según la política de la fuente y geocodificada por dirección; incluye atribución OSM. La agrupación no corrige coordenadas y opera sobre los resultados cargados por el frontend, que todavía tiene sus límites de paginación anteriores.

## Evidencia y validación

Revisión productiva de solo lectura del 12 de octubre: Supabase tiene `0012` aplicada, 754 filas históricas y 752 vigentes (Brega 171, Avantix 275, Gaggiotti 306). Health, API paginada con fotos y mapa públicos responden 200; el nuevo `ubicacion_info` aún no está desplegado. Código anterior en `1f45fc6` y `fdca4d2`; estos cambios de coordenadas siguen locales.

El primer relevamiento por direcciones textuales encontró un punto Gaggiotti compartido por 18 avisos y otro por cinco. La reproducción del diagnóstico final sobre las 754 filas, en SQLite en memoria, detectó el primer grupo con **12 puertas inequívocas y seis avisos no elegibles**. El segundo grupo no alcanza cinco puertas reconocibles; referencias como “Edificio Mayo Piso 1º Ofic. 9” no justifican corrección automática. Todavía no hay métodos `gmLocationType` persistidos: una ingesta con el código nuevo puede ampliar el diagnóstico.

Se hicieron seis consultas reales pequeñas, respetando el ritmo, sin aplicar resultados:

| Dirección publicada | Resultado |
| --- | --- |
| Brown 30 Piso 8 Departamento 2 | Rechazada: calle devuelta Almirante Brown, equivalencia no acreditada por el validador. |
| Lotufo 348 | Rechazada: devuelve tramos de calle sin altura. |
| Geuna 2507 | Rechazada: devuelve tramos de calle sin altura. |
| 14 de Julio 829 | Aceptada: `-31.24396, -61.4800736`, altura coincidente. |
| Belgrano 269 | Aceptada: `-31.2539523, -61.4891813`, altura coincidente. |
| 25 de Mayo 575 | Aceptada: `-31.2470656, -61.4914994`, altura coincidente. |

Las tres aceptadas compartían `-31.2525979, -61.4916422` en la fuente. Encontrar alturas coincidentes no prueba sus puertas reales ni resuelve todas las propiedades. No se verificó el comportamiento productivo posterior a migrar/aplicar porque esa publicación sigue pendiente.

Validación local: 212 pruebas Django, 210 aprobadas y dos integraciones PostGIS omitidas con SQLite; migración `0012→0013` en memoria conservando fila, punto y fotos, diagnóstico sobre copia efímera, caché, ambigüedad, reingesta, invalidación, cambio durante HTTP y reversión. JavaScript se verifica con `node scripts/test_mapa_coordenadas.cjs` (DOM/Leaflet simulados) y `node --check`; no se presenta como inspección visual de navegador. Actions se valida con actionlint. Las integraciones PostGIS se omiten al usar SQLite; no se modificaron sus consultas SQL.
