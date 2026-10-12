# Despliegue básico y continuidad

**Fotos (última etapa local): requiere `0012_propiedad_fotos` antes de ingerir.** El build existente aplica migrate y collectstatic; esperar su finalización antes de ejecutar Actions para cargar las galerías. Actions valida migraciones pendientes sin aplicarlas. Sin variables, Secrets ni dependencias nuevas. Ver [fotos y publicación](fotos.md).

Filtros estructurados, paginación y API JSON implementados localmente el 12 de octubre: pendientes de publicar. Esta etapa solo necesita desplegar el código en Render; no cambia variables, migraciones ni dependencias y no exige ingesta o reconstrucción del índice. Comprobar luego `/api/propiedades/`, sus enlaces, búsquedas filtradas y navegación HTML; ver [guía de la API](api_propiedades.md).

Actualización del 12 de octubre: health, plantilla, PostGIS y Elasticsearch están desplegados; las tres inmobiliarias y la tolerancia por fuente están publicadas. GitHub Actions completó la ingesta general sin errores de detalle y reconstruyó los 754 documentos. Se verificaron Supabase, igualdad del índice, búsqueda pública por relevancia y filtros espaciales. Ver [Gaggiotti](gaggiotti.md) e [ingesta](ingesta.md). El ping de cron-job.org fue creado, con historial aún pendiente de comprobación.

Render ya tiene `ELASTICSEARCH_URL`, `ELASTICSEARCH_API_KEY` y `ELASTICSEARCH_INDEX=propiedades` en **Environment**. Nunca subir `.env`. Ante una nueva configuración, copiar los valores sin comillas adicionales y verificar `/propiedades/?operacion=alquiler&q=departamento%20con%20cochera`. No ejecutar reconstrucción en el build ni desde una visita; la actualización corresponde al workflow o a un comando de mantenimiento explícito. Ver [comandos y próximos pasos](elasticsearch.md). Sin las variables, el listado normal sigue funcionando y las búsquedas textuales devuelven 503.

Para continuar desde la cuenta propietaria de Render, seguir la [guía de entrega al compañero](continuidad.md): variables, publicación, URLs de prueba, resolución de problemas y lista de pendientes. Actualizar el `.env` local no actualiza Render; el archivo no se comparte mediante Git.

Bajas por operación y mantenimiento también están implementados localmente: después de publicar, ejecutar ingesta para conciliar listados y reconstruir; comprobar el resumen antes de usar la vista previa de limpieza. No requieren cambios de esquema ni Secrets nuevos. Ver [procedimiento de mantenimiento](mantenimiento.md).

## Qué se completó

- Preparación de Django para ejecución desplegada, publicada en `main` mediante el commit `5f61bf9` (`Preparar Django para despliegue en Render`).
- Instalación y registro de Gunicorn `26.2.0` y WhiteNoise `6.12.0` en `requirements.txt`. Gunicorn ejecuta Django en Render y WhiteNoise sirve los archivos estáticos.
- Clave secreta obligatoria desde `DJANGO_SECRET_KEY`, modo de depuración desde `DJANGO_DEBUG` y hosts permitidos desde `DJANGO_ALLOWED_HOSTS`. El dominio de Render se agrega automáticamente mediante `RENDER_EXTERNAL_HOSTNAME`.
- Configuración del proxy HTTPS y cookies de sesión/CSRF seguras cuando se ejecuta en Render.
- `STATIC_ROOT=BASE_DIR / 'staticfiles'`, almacenamiento de estáticos comprimidos con manifiesto y middleware WhiteNoise después de `SecurityMiddleware`.
- `.python-version` con `3.14`. Render selecciona el parche correspondiente según [su documentación](https://render.com/docs/python-version).
- `.env` y `staticfiles/` excluidos de Git. `.env.example` incluye nombres y ejemplos de configuración, sin credenciales reales.
- Creación del servicio web en Render Free, conectado al repositorio y a Supabase mediante variables de entorno.

## Configuración del servicio web

| Campo | Configuración |
| --- | --- |
| Repositorio | `juampisarra/Grupo7_TAP_SaraSarraWilliner` |
| Nombre indicado durante la configuración | `observatorio-grupo7` |
| Lenguaje | Python 3 |
| Rama | `main` |
| Root Directory | Vacío: ejecutar desde la raíz del repositorio. |
| Instancia | Free |

La región efectiva y la URL asignada se consultan en el panel de Render. Se recomendó una región cercana a Supabase; no se confirmó en la conversación cuál se seleccionó.

**Build Command:**

```bash
python -m pip install -r requirements.txt && python manage.py collectstatic --noinput && python manage.py migrate --noinput
```

Instala dependencias, reúne los estáticos y aplica las migraciones en Supabase. Esta es la configuración del despliegue básico: las migraciones se ejecutan durante la construcción.

**Start Command:**

```bash
python -m gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 1
```

Gunicorn escucha en el puerto que asigna Render. El `$` que muestra la interfaz al inicio de un campo no se escribe; el `$` de `$PORT` sí pertenece al comando. Estos comandos se colocan en Render, no en PowerShell. La [guía oficial de Django en Render](https://render.com/docs/deploy-django) sirve de referencia; en este proyecto se conserva Supabase como base.

## Variables de entorno

Completar las variables en el panel de Render. No subir `.env` al repositorio ni incluir valores secretos en documentación o capturas.

| Variable | Valor o procedencia |
| --- | --- |
| `DJANGO_SECRET_KEY` | Clave privada generada para el entorno desplegado. |
| `DJANGO_DEBUG` | `False`. Evita mostrar detalles internos de errores a visitantes; los errores siguen disponibles en los logs. |
| `DB_ENGINE` | `postgresql` |
| `PGHOST` | Host exacto de la conexión de Supabase. |
| `PGPORT` | `5432` para la conexión Session pooler utilizada. |
| `PGDATABASE` | `postgres` |
| `PGUSER` | Usuario exacto del panel de Supabase. |
| `PGPASSWORD` | Contraseña de PostgreSQL, sin comillas adicionales en el campo de Render. |
| `PGSSLMODE` | `require` |
| `ELASTICSEARCH_URL` | Endpoint HTTPS del proyecto Elastic Cloud. |
| `ELASTICSEARCH_API_KEY` | API key encoded completa, sin prefijo `ApiKey ` ni comillas adicionales. |
| `ELASTICSEARCH_INDEX` | `propiedades`, alias ya cargado desde Supabase. |

No hace falta configurar `DJANGO_ALLOWED_HOSTS` para el dominio asignado por Render: el código agrega `RENDER_EXTERNAL_HOSTNAME`, que proporciona Render. Si se incorpora un dominio propio, agregarlo a `DJANGO_ALLOWED_HOSTS` como hostname, sin protocolo ni ruta. Localmente se utiliza `localhost,127.0.0.1`.

Para generar una clave localmente con las dependencias instaladas:

```powershell
.\.venv\Scripts\python.exe -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Copiar el resultado directamente al entorno correspondiente y conservarlo privado.

## Comprobaciones del primer despliegue

Esta lista registra la preparación inicial. Las verificaciones posteriores y el estado actual se indican más abajo y en [continuidad](continuidad.md).

- `collectstatic`: 130 archivos copiados y 390 procesados en la ejecución local registrada. Son los resultados de esa ejecución, no cantidades fijas esperadas.
- `python manage.py check`: `System check identified no issues (0 silenced)`.
- `python manage.py showmigrations propiedades`: migraciones `0001` a `0010` marcadas con `[X]` en Supabase.
- `git check-ignore .env`: confirmó que `.env` está ignorado.
- Commit y push de la preparación a `main` completados.
- El equipo abrió el sitio desplegado y confirmó que muestra propiedades de Brega. Esta es la comprobación funcional del despliegue; no se realizó una auditoría de seguridad ni una nueva ejecución de las 48 pruebas históricas.

Abrir la URL asignada por Render con `/propiedades/` al final. El proyecto no tiene una vista para `/`; un 404 en la raíz no demuestra que el despliegue haya fallado. `/health/` ya está desplegado y responde `{"status":"ok"}` con HTTP 200, sin base de datos, scraping ni otros servicios. Admite GET y HEAD, no se almacena en caché y solo comprueba que Django responde.

## Correcciones ya desplegadas

Con `DJANGO_DEBUG=False`, Django redirige a HTTPS, utiliza cookies seguras y agrega HSTS durante una hora. En Render reconoce HTTPS mediante `X-Forwarded-Proto`, evitando un bucle de redirección. En desarrollo local conservar `DJANGO_DEBUG=True` para poder utilizar HTTP con `runserver`.

`check --deploy` ya no informa el error de correo de consola ni las advertencias de HSTS ausente o redirección. **El proyecto no envía emails en producción**: el backend `config.mail.CorreoDeshabilitado` falla explícitamente si alguien intenta enviar. Esto no configura SMTP ni certifica entrega. Antes de agregar una funcionalidad de correo habrá que integrar un proveedor en `MAILERS`. En desarrollo se conserva la consola.

Persisten dos recomendaciones del check, `security.W005` y `security.W021`: subdominios HSTS y preload están desactivados expresamente. No se amplía la política a otros hosts ni se anuncia preload con una configuración de una hora. No se silencian estas advertencias.

La plantilla distingue cero de NULL para dormitorios, precios y coordenadas. También indica si las coordenadas representan una ubicación aproximada o de precisión desconocida.

El 10 de octubre se comprobaron públicamente `/health/`, el listado, filtros geográficos y errores 400 ante parámetros inválidos. El equipo creó el ping en cron-job.org; queda comprobar una ejecución programada exitosa en **Historial**, con GET a `/health/` y el intervalo propuesto de diez minutos. Ver el procedimiento en [continuidad](continuidad.md).

Health y PostGIS no requieren nuevas variables. Elasticsearch sí necesita las tres variables agregadas a la tabla anterior. No hace falta repetir scraping para publicar esta etapa. El build documentado ejecuta `migrate`; en la Supabase actual `0011` ya está aplicada. En una base nueva instalará PostGIS si el usuario tiene los permisos correspondientes.

Render Free puede entrar en reposo tras 15 minutos sin tráfico y la siguiente solicitud puede tardar aproximadamente un minuto en reactivarlo. Ver [límites oficiales](https://render.com/docs/free). El job externo está creado, pero su ejecución automática sigue sin comprobarse; los pings no garantizan disponibilidad continua.

## Cómo funcionan los datos hoy

El sitio consulta las propiedades ya guardadas en Supabase. Una visita o un cambio de filtro no ejecuta scraping. GitHub Actions ejecuta semanalmente el comando general de ingesta y luego reconstruye Elasticsearch; también admite ejecución manual. Para mantenimiento desde una computadora con el entorno configurado se puede importar todo o una fuente específica:

```powershell
.\.venv\Scripts\python.exe manage.py importar_propiedades
.\.venv\Scripts\python.exe manage.py importar_propiedades brega
.\.venv\Scripts\python.exe manage.py importar_propiedades avantix
.\.venv\Scripts\python.exe manage.py importar_propiedades gaggiotti
```

Después de una ingesta manual, ejecutar `python manage.py reconstruir_indice` para actualizar las búsquedas textuales. El workflow ya realiza ambos pasos automáticamente y conserva el alias anterior si falla la reconstrucción. No hace falta volver a desplegar para ver cambios de datos. `--completar-ubicacion` sigue siendo opcional; consultar [la guía de bases y enriquecimiento](base_de_datos.md). Evitar ejecuciones simultáneas que usen Nominatim y escrituras durante una reconstrucción.

El comando general y GitHub Actions están publicados y verificados con Brega, Avantix y Gaggiotti. El workflow manual del 12 de octubre creó 306 Gaggiotti y reconstruyó los 754 documentos de la base. No requiere migraciones, dependencias, variables ni Secrets nuevos. Ver [datos, validación y publicación](gaggiotti.md).

La tolerancia por fuente ya publicada continúa con las restantes ante un fallo, informa el resultado final y permite reconstruir el índice ante éxito parcial, conservando el job fallido. Si ninguna fuente termina bien, omite reconstrucción. El aislamiento está cubierto por pruebas locales; la ejecución productiva completó las tres fuentes. Ver [códigos de salida y recuperación](ingesta.md). PostGIS, Elasticsearch y los filtros por radio/rectángulo están desplegados. Filtros estructurados/paginación/API están implementados localmente, pendientes de publicación. Recuperación incremental, frontend definitivo y mapa siguen pendientes de implementar.

## Elasticsearch en Elastic Cloud

El 10 de octubre se completaron creación del servicio, conexión desde Django, carga inicial y reconstrucción del índice, análisis en español y búsquedas por relevancia. El alias `propiedades` contenía 173 documentos en esa revisión; se verificó una segunda reconstrucción sin duplicar resultados. Los detalles de comandos, ranking y recuperación están en [Elasticsearch](elasticsearch.md).

La búsqueda acepta `q` en `/propiedades/`, dispone de un formulario mínimo, devuelve resultados ordenados por relevancia y conserva filtros de operación y PostGIS. Supabase mantiene la autoridad sobre los datos. Sin `q`, el listado no consulta Elasticsearch. No hay mapa ni frontend definitivo.

Gaggiotti y la tolerancia por fuente ya están publicadas y verificadas. El siguiente paso operativo es publicar y comprobar filtros estructurados/paginación/API implementados localmente; la próxima feature es frontend/mapa. Bajas por operación, reconstrucción independiente y limpieza con vista previa también están implementadas localmente y pendientes de publicar; ver [mantenimiento](mantenimiento.md). La indexación/recuperación incremental sigue pendiente. Registrar también la fecha/hora exactas de vencimiento de Elastic y su continuidad posterior. La lista ordenada está en [trabajo que sigue](continuidad.md#trabajo-que-sigue).
