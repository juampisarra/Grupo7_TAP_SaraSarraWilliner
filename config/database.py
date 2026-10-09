"""Configuración de PostgreSQL/Supabase o SQLite, sin credenciales en el código."""

from django.core.exceptions import ImproperlyConfigured


def configurar_base(base_dir, entorno):
    motor = entorno.get("DB_ENGINE", "sqlite").strip().lower()
    if motor == "sqlite":
        return {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": base_dir / "db.sqlite3",
        }
    if motor != "postgresql":
        raise ImproperlyConfigured("DB_ENGINE debe ser sqlite o postgresql")
    requeridas = ("PGHOST", "PGDATABASE", "PGUSER", "PGPASSWORD")
    faltantes = [nombre for nombre in requeridas if not entorno.get(nombre)]
    if faltantes:
        raise ImproperlyConfigured("Faltan variables de PostgreSQL: " + ", ".join(faltantes))
    return {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": entorno["PGHOST"],
        "NAME": entorno["PGDATABASE"],
        "USER": entorno["PGUSER"],
        "PASSWORD": entorno["PGPASSWORD"],
        "PORT": entorno.get("PGPORT", "5432"),
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
        "DISABLE_SERVER_SIDE_CURSORS": True,
        "OPTIONS": {
            "sslmode": entorno.get("PGSSLMODE", "require"),
            "connect_timeout": 10,
            "prepare_threshold": None,
        },
    }
