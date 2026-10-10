# Continuidad del proyecto y entrega al compañero

Estado al 10 de octubre de 2026. Esta guía permite publicar la integración de Elasticsearch desde la cuenta propietaria de Render. El equipo indicó que la evaluación es el martes 13 de octubre.

## Estado comprobado

| Componente | Estado actual |
| --- | --- |
| Django / Render | Sitio público funcionando con Supabase, HTTPS y estáticos. |
| `/health/` | Desplegado; HTTP 200 con `{"status":"ok"}`, sin consultar servicios externos. |
| Plantilla | Desplegada la corrección que distingue cero de datos ausentes. |
| PostgreSQL / Supabase | 173 publicaciones en la revisión; migraciones hasta `0011` aplicadas. |
| PostGIS | Instalado; almacenamiento espacial e índices GiST. Filtros por radio y rectángulo desplegados, mediante parámetros de URL. |
| Elastic Cloud | Proyecto creado y conexión real comprobada. Alias `propiedades` cargado con 173 documentos desde Supabase. |
| Django + Elasticsearch | Código, comandos y búsqueda por `q` probados localmente contra Elastic Cloud. Pendiente publicar este código y configurar Render. |
| Scraper | Solo Brega, por comando manual. No actualiza automáticamente Elasticsearch. |
| cron-job.org | Job creado; falta comprobar una ejecución programada exitosa en su historial. |
| GitHub Actions | Workflow y programación pendientes. |

Los conteos son una instantánea, no valores esperados permanentes. Elastic Cloud es remoto: el índice ya cargado se puede usar desde Render sin mantener una computadora encendida.

## 1. Publicar el código y actualizar el entorno local

Quien tiene los cambios revisa y hace commit/push de esta etapa. Esta documentación no implica que ese push ya haya ocurrido.

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

No necesita reconstruir el índice para este despliegue: ya está cargado.

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

No hay un formulario nuevo de búsqueda ni un mapa. Texto y geografía se prueban por URL en el listado existente, de acuerdo con la prioridad de backend. Por defecto los filtros geográficos solo aceptan ubicaciones declaradas exactas; los datos actuales de Brega son aproximados. `incluir_aproximadas=1` permite consultar sus centros publicados, sin garantizar la ubicación real dentro del radio. Ver [precisión y parámetros](postgis.md).

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

## Mantenimiento manual mientras no haya automatización

Cuando se necesite refrescar Brega, ejecutar en un único entorno configurado contra Supabase y Elastic, sin otra ingesta o reconstrucción simultánea:

```powershell
.\.venv\Scripts\python.exe -X utf8 manage.py importar_propiedades brega
.\.venv\Scripts\python.exe -X utf8 manage.py reconstruir_indice
```

Son dos pasos separados. Ejecutar la reconstrucción después de comprobar que terminó la ingesta. Si falla Elasticsearch, los datos guardados en PostgreSQL se conservan; corregir el problema y reintentar la reconstrucción. Hasta completarla, las búsquedas textuales pueden reflejar el índice anterior. No es necesario redesplegar Render para publicar cambios de datos.

La reconstrucción crea una versión nueva y cambia el alias tras validar la carga. Conserva versiones anteriores; no borrarlas sin identificar el índice activo. Evitar escrituras durante la reconstrucción. Ver [procedimiento y límites de recuperación](elasticsearch.md).

## Trabajo que sigue

1. **Cerrar esta publicación:** variables y código en Render, pruebas públicas, historial del ping y vencimiento exacto de Elastic. La continuidad después de la prueba sigue pendiente.
2. **Sincronizar ingesta e índice:** persistir primero en PostgreSQL, actualizar Elasticsearch después y definir reintentos/recuperación ante fallos. La reconstrucción completa ya existe, pero la sincronización automática todavía no.
3. **Preparar el comando general de ingesta** para todas las fuentes registradas. Hoy `brega` es obligatorio; no configurar un comando sin argumentos antes de implementar esa ampliación.
4. **Automatizar con GitHub Actions:** Secrets, ejecución manual inicial, horario acordado, exclusión de ejecuciones simultáneas y actualización del índice. Actualmente no hay workflow. El repositorio se comprobó público el 9 de octubre; revisar esa condición al configurarlo.
5. **Completar las fuentes:** verificar Avantix, reutilizar el adaptador cuando sea compatible y elegir/implementar la tercera inmobiliaria. Definir también el tratamiento de avisos retirados.
6. **Completar búsquedas del backend:** filtros de tipo y precio con moneda/operación, paginación y API; ampliar geografía a polígonos y definir el tratamiento de áreas aproximadas cuando corresponda.
7. **Frontend y mapa:** definirlos e implementarlos después del backend. No están incluidos en esta etapa.

La suite registrada para esta integración descubrió 72 pruebas: 71 aprobadas y una integración PostGIS omitida al usar SQLite. También pasaron la comprobación de migraciones pendientes y dependencias. Las pruebas reales de Elastic y PostGIS se describen en sus respectivas guías; la búsqueda desde Render queda pendiente del compañero.
