# Despliegue básico y continuidad

Actualización del 10 de octubre: el equipo desplegó las correcciones de health/plantilla/PostGIS y se verificaron los endpoints públicos. Elasticsearch ya está conectado y cargado localmente con 173 documentos; falta desplegar esta nueva integración. El ping de cron-job.org fue creado, con historial aún pendiente de comprobación.

Para publicar Elasticsearch, agregar en **Environment** del servicio Render `ELASTICSEARCH_URL`, `ELASTICSEARCH_API_KEY` y `ELASTICSEARCH_INDEX=propiedades`, usando los mismos valores locales, sin comillas adicionales. Nunca subir `.env`. Después publicar el código nuevo y verificar `/propiedades/?operacion=alquiler&q=departamento%20con%20cochera`; esta instantánea devuelve cinco avisos en local. No ejecutar reconstrucción en el build ni desde una visita: el alias ya está cargado. Ver [comandos y próximos pasos](elasticsearch.md). Sin las variables, el listado normal sigue funcionando y las búsquedas textuales devuelven 503.

Para continuar desde la cuenta propietaria de Render, seguir la [guía de entrega al compañero](continuidad.md): variables, publicación, URLs de prueba, resolución de problemas y lista de pendientes. Actualizar el `.env` local no actualiza Render; el archivo no se comparte mediante Git.

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

El sitio consulta las propiedades ya guardadas en Supabase. Una visita o un cambio de filtro no ejecuta scraping. El scraper todavía se ejecuta manualmente, desde una computadora con el entorno configurado:

```powershell
.\.venv\Scripts\python.exe manage.py importar_propiedades brega
```

Después de esa ingesta, el sitio puede consultar los datos actualizados en la misma base. Para actualizar también las búsquedas textuales, ejecutar por separado `python manage.py reconstruir_indice` al terminar la ingesta: la sincronización automática todavía no existe. No hace falta volver a desplegar para ver cambios de datos. `--completar-ubicacion` sigue siendo opcional; consultar [la guía de bases y enriquecimiento](base_de_datos.md). Evitar ejecuciones simultáneas que usen Nominatim y escrituras durante una reconstrucción.

La versión final tendrá un solo comando general para todas las fuentes registradas, pero hoy `brega` es obligatorio y es la única fuente disponible. GitHub Actions todavía no está configurado. PostGIS y los filtros por radio/rectángulo están desplegados. Elasticsearch está implementado y probado localmente contra Elastic Cloud; faltan las variables y la publicación en Render. Otras inmobiliarias, sincronización automática del índice, filtros de tipo/precio, API de búsqueda, frontend definitivo y mapa siguen pendientes.

## Elasticsearch en Elastic Cloud

El 10 de octubre se completaron creación del servicio, conexión desde Django, carga inicial y reconstrucción del índice, análisis en español y búsquedas locales por relevancia. El alias `propiedades` contiene 173 documentos; se verificó una segunda reconstrucción sin duplicar resultados. Los detalles de comandos, ranking y recuperación están en [Elasticsearch](elasticsearch.md).

La búsqueda acepta `q` en `/propiedades/`, devuelve resultados ordenados por relevancia y conserva filtros de operación y PostGIS. Supabase mantiene la autoridad sobre los datos. Sin `q`, el listado no consulta Elasticsearch. No se agregó un formulario ni mapa: se prueba por URL.

El siguiente paso es publicar desde la cuenta propietaria de Render según [continuidad](continuidad.md). Luego integrar actualización del índice posterior al guardado y recuperación de fallos. La prueba ya está activa; registrar en el panel su fecha/hora exactas de vencimiento y confirmar la cobertura de la evaluación del martes 13. La continuidad posterior sigue pendiente.

Después se prepararán el comando general y GitHub Actions para automatizar la ingesta, además de completar las demás features. La lista ordenada está en [trabajo que sigue](continuidad.md#trabajo-que-sigue).
