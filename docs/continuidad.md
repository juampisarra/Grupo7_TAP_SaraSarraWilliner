# Continuidad del proyecto y entrega al compañero

Estado al 12 de octubre de 2026. Elasticsearch, GitHub Actions y las tres inmobiliarias están publicados y verificados. Esta guía conserva el procedimiento de configuración como referencia de recuperación. Gaggiotti y la tolerancia por fuente se publicaron en `a390093`; el [workflow manual](https://github.com/juampisarra/Grupo7_TAP_SaraSarraWilliner/actions/runs/38213432407) terminó correctamente. Ver [Gaggiotti](gaggiotti.md) e [ingesta](ingesta.md). El equipo indicó que la evaluación es el martes 13 de octubre.

**Esta etapa está publicada:** el agente hizo commit/push y ejecutó **Ingesta Semanal de Propiedades** con autorización explícita del usuario. Supabase tiene 306 registros de Gaggiotti y 754 publicaciones totales; el índice coincide con la base y las búsquedas públicas conservan relevancia. No hubo variables, Secrets, dependencias ni migraciones nuevas. Las instrucciones siguientes son referencias para configuración y recuperación, no tareas de despliegue todavía pendientes.

## Estado comprobado

| Componente | Estado actual |
| --- | --- |
| Django / Render | Sitio público funcionando con Supabase, HTTPS y estáticos. |
| `/health/` | Desplegado; HTTP 200 con `{"status":"ok"}`, sin consultar servicios externos. |
| Plantilla | Desplegada la corrección que distingue cero de datos ausentes. |
| PostgreSQL / Supabase | 754 publicaciones en la revisión del 12 de octubre; migraciones hasta `0011` aplicadas. |
| PostGIS | Instalado; almacenamiento espacial e índices GiST. Filtros por radio y rectángulo desplegados, mediante parámetros de URL. |
| Elastic Cloud | Alias `propiedades` con 754 documentos; IDs y contenido coinciden íntegramente con Supabase. |
| Django + Elasticsearch | Desplegado en Render; búsqueda por `q`, relevancia y formulario mínimo verificados públicamente. |
| Scraper | Brega y Avantix desplegadas; el equipo confirmó 275 registros de Avantix en Supabase y búsquedas públicas de ambas fuentes. |
| Gaggiotti | Publicada y verificada: 306 publicaciones, detalles y puntos PostGIS; búsqueda textual y geográfica públicas comprobadas. |
| cron-job.org | Job creado; falta comprobar una ejecución programada exitosa en su historial. |
| GitHub Actions | Workflow general, Secrets, concurrencia, ejecución manual y programación semanal verificados. Reconstruye Elasticsearch después de la ingesta. |

Los conteos son una instantánea, no valores esperados permanentes. Elastic Cloud es remoto: el índice ya cargado se puede usar desde Render sin mantener una computadora encendida.

## 1. Publicar el código y actualizar el entorno local

Esta etapa ya se publicó con autorización del usuario. Para publicaciones futuras, quien tenga los cambios revisa y hace commit/push; el procedimiento siguiente también sirve para actualizar otra computadora del equipo.

El compañero actualiza su copia con `git pull` y, desde la raíz del proyecto, instala las dependencias:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Agregar a su `.env` las tres variables de Elasticsearch usando los valores reales compartidos por un canal privado:

```dotenv
ELASTICSEARCH_URL=https://TU_ENDPOINT.elastic.cloud:443
ELASTICSEARCH_API_KEY='TU_API_KEY_ENCODED'
ELASTICSEARCH_INDEX=propiedades
```

La API key encoded se copia completa tal como la entrega Elastic: no decodificar, no volver a codificar y no agregar `ApiKey ` al comienzo. Guardar `.env` en UTF-8 sin BOM. `.env.example` solo contiene ejemplos; `.env` está ignorado por Git y **no llega a la computadora del compañero ni a Render mediante un push**. Conservar su configuración existente de Django y Supabase.

Si desea comprobar su entorno local, con `DB_ENGINE=postgresql` apuntando a la Supabase del proyecto:

```powershell
.\.venv\Scripts\python.exe -X utf8 manage.py comprobar_elasticsearch
.\.venv\Scripts\python.exe -X utf8 manage.py buscar_propiedades "departamento con cochera" --limite 5
```

El índice existente permite probar el entorno anterior. Para incorporar Gaggiotti hay que ejecutar la nueva ingesta y reconstrucción, preferentemente mediante el workflow; no basta con publicar Django.

## 2. Configurar Render desde la cuenta propietaria

1. Abrir el servicio **observatorio-grupo7** y entrar a **Environment**.
2. Agregar estas variables, con los mismos valores reales del `.env` que se probó:

   | Variable | Valor |
   | --- | --- |
   | `ELASTICSEARCH_URL` | Endpoint HTTPS completo del proyecto Elastic. |
   | `ELASTICSEARCH_API_KEY` | API key encoded completa. |
   | `ELASTICSEARCH_INDEX` | `propiedades` |

3. En los campos de Render pegar los valores **sin las comillas** del ejemplo `.env`. Conservar `DJANGO_DEBUG=False`, `DB_ENGINE=postgresql` y las variables de Supabase y Django existentes.
4. Guardar los cambios y desplegar el último commit de `main`. Revisar en el panel qué commit se está desplegando y esperar a que termine correctamente.
5. Si el despliegue automático está habilitado para `main`, el push puede iniciar el build. Si está deshabilitado, usar la opción de despliegue manual del último commit. En ambos casos deben quedar publicados el código nuevo y las tres variables.

Cambiar el `.env` de una computadora no modifica las variables de Render. Si el código se publica antes de configurar las variables, el listado sin texto y `/health/` siguen funcionando, pero una búsqueda con `q` devuelve 503 hasta completar la configuración.

Conservar los comandos de build y arranque de [despliegue](despliegue.md). El build instala `elasticsearch==9.5.1` desde `requirements.txt`. **No agregar scraping ni reconstrucción del índice al build, al arranque o a `/health/`.** Esta integración no agrega migraciones; `0011` ya está aplicada en la Supabase actual.

## 3. Comprobar la versión publicada

Abrir estas URLs después del despliegue:

| Prueba | Resultado esperado |
| --- | --- |
| [Health](https://observatorio-grupo7.onrender.com/health/) | HTTP 200 y `{"status":"ok"}`. |
| [Listado de alquileres](https://observatorio-grupo7.onrender.com/propiedades/) | HTTP 200; 40 avisos en la revisión. |
| [Listado de ventas](https://observatorio-grupo7.onrender.com/propiedades/?operacion=venta) | HTTP 200; 136 avisos en la revisión. |
| [Texto en alquileres](https://observatorio-grupo7.onrender.com/propiedades/?operacion=alquiler&q=departamento%20con%20cochera) | HTTP 200, indicación de relevancia y 5 avisos en la prueba local. |
| [Texto en ventas](https://observatorio-grupo7.onrender.com/propiedades/?operacion=venta&q=departamento%20con%20cochera) | HTTP 200 y 11 avisos en la prueba local. |
| [Radio de 2 km](https://observatorio-grupo7.onrender.com/propiedades/?operacion=alquiler&latitud=-31.25&longitud=-61.49&radio_m=2000&incluir_aproximadas=1) | HTTP 200 y 32 avisos en la revisión pública anterior. |

Las cantidades pueden cambiar al actualizar datos. Para verificar Elasticsearch, comprobar también que aparezca el texto de resultados por relevancia y que cambiar venta/alquiler conserve `q`. Un HTTP 200 por sí solo no prueba la integración: la versión anterior puede ignorar `q` y mostrar todos los avisos.

Hay un formulario textual mínimo para probar `q`, pero no un frontend definitivo ni un mapa. La geografía se prueba por parámetros de URL en el listado existente, de acuerdo con la prioridad de backend. Por defecto los filtros geográficos solo aceptan `ubicacion_aproximada=False`; los datos de Brega son aproximados. `incluir_aproximadas=1` permite consultar sus centros publicados, sin garantizar la ubicación real dentro del radio. Los puntos de Avantix entran en el filtro predeterminado porque el equipo decidió guardarlos como exactos y sin radio, aunque la fuente no declare esa precisión. Ver [precisión y parámetros](postgis.md).

## 4. Resolver problemas de publicación

| Síntoma | Revisar |
| --- | --- |
| `q` devuelve 503 | Las tres variables en Render, key completa y vigente, permisos de lectura/PIT, servicio Elastic activo y alias `propiedades`. No reemplazar el error por una lista vacía. |
| `q` muestra todo sin indicar relevancia | Commit realmente desplegado; confirmar que contiene la integración textual y que terminó el despliegue. |
| Build falla instalando el cliente | Build Command y `requirements.txt` del commit nuevo; consultar el error en logs. |
| HTTP 500 | Logs de Render y configuración de Django/Supabase. No activar DEBUG en el sitio público. |
| Radio devuelve cero avisos | Precisión predeterminada, operación y parámetros; revisar si corresponde incluir ubicaciones aproximadas. |
| Primera respuesta tarda después de inactividad | Comprobar estado del servicio y logs; Render Free puede reactivarse tras reposo. El ping no garantiza disponibilidad continua. |

No compartir capturas que muestren credenciales. Registrar en el equipo el commit desplegado, el resultado de las pruebas y la fecha/hora exactas de vencimiento de Elastic que muestra su panel.

## 5. Comprobar el ping

En cron-job.org, revisar **Ping Observatorio Grupo 7**: habilitado, método GET y URL `https://observatorio-grupo7.onrender.com/health/`. El intervalo propuesto es cada diez minutos (`*/10 * * * *`); comprobar el valor efectivamente guardado y la zona horaria mostrada.

Una prueba manual verifica la URL, pero no demuestra que funcione la programación. Esperar una ejecución programada y abrir **Historial**: comprobar fecha/hora y respuesta HTTP 200. Registrar ese resultado. Un guion en «Última ejecución» no confirma que se haya realizado el ping. Este job mantiene tráfico al servicio; no ejecuta el scraper ni actualiza el índice.

## Mantenimiento manual y recuperación

GitHub Actions ya ejecuta semanalmente la ingesta general y reconstruye el índice. Cuando sea necesario realizar mantenimiento manual, usar un único entorno configurado contra Supabase y Elastic, sin otra ingesta o reconstrucción simultánea:

```powershell
.\.venv\Scripts\python.exe -X utf8 manage.py importar_propiedades
.\.venv\Scripts\python.exe -X utf8 manage.py reconstruir_indice
```

Para aislar una fuente se puede agregar `brega`, `avantix` o `gaggiotti` al primer comando. Son dos pasos separados: ejecutar la reconstrucción después de comprobar que terminó la ingesta. Si falla Elasticsearch, los datos guardados en PostgreSQL se conservan; corregir el problema y reintentar la reconstrucción. Hasta completarla, las búsquedas textuales pueden reflejar el índice anterior. No es necesario redesplegar Render para publicar cambios de datos.

La reconstrucción crea una versión nueva y cambia el alias tras validar la carga. Conserva versiones anteriores; no borrarlas sin identificar el índice activo. Evitar escrituras durante la reconstrucción. Ver [procedimiento y límites de recuperación](elasticsearch.md).

El comando general procesa `avantix`, `brega` y `gaggiotti`, en ese orden. La tolerancia por fuente ya publicada permite continuar después de una fuente fallida. Devuelve `3` ante éxito parcial y `1` si todas fallan. El workflow reconstruye con `0` o `3`, manteniendo el job fallido ante fallo parcial; con fallo total omite el índice. Los errores recuperables de fichas individuales mantienen su comportamiento anterior. Ver [operación y recuperación](ingesta.md).

## Trabajo que sigue

1. **Tolerancia por fuente: completada y publicada.** Aislamiento probado localmente; workflow publicado y comprobado con las tres fuentes exitosas.
2. **Gaggiotti: completada y publicada.** Primera carga, reconstrucción y resultados públicos verificados el 12 de octubre. Ver [validación y límites](gaggiotti.md).
3. **Filtros estructurados:** agregar tipo, dormitorios y precio por operación/moneda.
4. **Paginación y API JSON:** preparar el acceso del futuro frontend.
5. **Frontend y mapa:** desarrollarlos después de completar el backend.

En paralelo quedan historial del ping, vencimiento/continuidad de Elastic, recuperación incremental, limpieza de versiones del índice y política de avisos retirados.

La suite local descubrió 117 pruebas: 116 aprobadas y una integración PostGIS omitida al usar SQLite. No hay cambios de modelo pendientes ni dependencias rotas. La validación efímera probó 306 altas y una segunda carga sin duplicados. Después, el workflow productivo del 12 de octubre creó 306 Gaggiotti y reconstruyó los 754 documentos sin errores. Las comprobaciones posteriores fueron de solo lectura: índice completo igual a PostgreSQL, orden público igual a Elasticsearch y filtros públicos iguales a PostGIS. Ver [Gaggiotti](gaggiotti.md) y [validación de tolerancia](ingesta.md).
