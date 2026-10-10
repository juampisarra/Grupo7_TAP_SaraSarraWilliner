# Despliegue básico y continuidad

Estado actualizado el 9 de octubre de 2026. El equipo confirmó que el sitio desplegado en Render muestra las propiedades de Brega desde `/propiedades/`, consultando la base PostgreSQL de Supabase. La URL exacta debe copiarse del panel de Render; no se registra aquí un dominio supuesto.

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

No hace falta configurar `DJANGO_ALLOWED_HOSTS` para el dominio asignado por Render: el código agrega `RENDER_EXTERNAL_HOSTNAME`, que proporciona Render. Si se incorpora un dominio propio, agregarlo a `DJANGO_ALLOWED_HOSTS` como hostname, sin protocolo ni ruta. Localmente se utiliza `localhost,127.0.0.1`.

Para generar una clave localmente con las dependencias instaladas:

```powershell
.\.venv\Scripts\python.exe -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Copiar el resultado directamente al entorno correspondiente y conservarlo privado.

## Comprobaciones realizadas

- `collectstatic`: 130 archivos copiados y 390 procesados en la ejecución local registrada. Son los resultados de esa ejecución, no cantidades fijas esperadas.
- `python manage.py check`: `System check identified no issues (0 silenced)`.
- `python manage.py showmigrations propiedades`: migraciones `0001` a `0010` marcadas con `[X]` en Supabase.
- `git check-ignore .env`: confirmó que `.env` está ignorado.
- Commit y push de la preparación a `main` completados.
- El equipo abrió el sitio desplegado y confirmó que muestra propiedades de Brega. Esta es la comprobación funcional del despliegue; no se realizó una auditoría de seguridad ni una nueva ejecución de las 48 pruebas históricas.

Abrir la URL asignada por Render con `/propiedades/` al final. El proyecto no tiene una vista para `/`; un 404 en la raíz no demuestra que el despliegue haya fallado. Tampoco existe `/health/`: no configurar esa ruta como health check hasta implementarla.

Render Free puede entrar en reposo tras 15 minutos sin tráfico y la siguiente solicitud puede tardar aproximadamente un minuto en reactivarlo. Ver [límites oficiales](https://render.com/docs/free). Los pings externos siguen sin configurar y no garantizan disponibilidad continua.

## Cómo funcionan los datos hoy

El sitio consulta las propiedades ya guardadas en Supabase. Una visita o un cambio de filtro no ejecuta scraping. El scraper todavía se ejecuta manualmente, desde una computadora con el entorno configurado:

```powershell
.\.venv\Scripts\python.exe manage.py importar_propiedades brega
```

Después de esa ingesta, el sitio puede consultar los datos actualizados en la misma base. No hace falta volver a desplegar para ver cambios de datos. `--completar-ubicacion` sigue siendo opcional; consultar [la guía de bases y enriquecimiento](base_de_datos.md). Evitar ejecuciones simultáneas que usen Nominatim.

La versión final tendrá un solo comando general para todas las fuentes registradas, pero hoy `brega` es obligatorio y es la única fuente disponible. GitHub Actions todavía no está configurado. Elasticsearch, PostGIS, otras inmobiliarias, filtros adicionales, API de búsqueda, frontend definitivo y mapa siguen pendientes.

## Próximo paso: Elasticsearch en Elastic Cloud

Objetivo de la siguiente etapa: buscar textos como `departamento con cochera` y ordenar propiedades por relevancia, conservando Supabase como fuente de verdad.

1. **Crear el servicio.** Registrarse desde la [prueba oficial de Elastic Cloud](https://www.elastic.co/cloud/elasticsearch-service/signup), crear un despliegue de Elasticsearch y registrar la fecha de vencimiento. La prueba anunciada es de 14 días sin tarjeta; comprobar que cubra la evaluación. No es un plan gratuito permanente.
2. **Probar la conexión.** Elegir el cliente Python compatible con la versión del servicio, configurar credenciales en el entorno local y en Render y verificar que Django se conecta. Los nombres de estas variables y el cliente todavía no están implementados.
3. **Cargar el índice desde Supabase.** Definir campos de texto y análisis en español, crear un comando de reconstrucción y cargar las propiedades existentes. No es necesario repetir el scraping para este paso.
4. **Probar búsqueda y ranking.** Consultar ejemplos reales y revisar coincidencias, orden y resultados vacíos antes de conectar la búsqueda al sitio.
5. **Integrar y desplegar.** Incorporar búsqueda en Django, actualizar el índice después de persistir, definir recuperación de fallos y comprobar la función desde Render. Toda la lógica geográfica seguirá reservada a PostGIS.

Después se prepararán el comando general y GitHub Actions para automatizar la ingesta, además de completar las demás features. Las instrucciones concretas de integración se escribirán al implementarlas; esta sección describe trabajo pendiente.
