from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase
from django.db.utils import load_backend

from config.database import configurar_base


class ConfiguracionBaseTests(SimpleTestCase):
    def test_sin_configuracion_usa_sqlite(self):
        base = configurar_base(Path("proyecto"), {})
        self.assertEqual(base["ENGINE"], "django.db.backends.sqlite3")
        self.assertEqual(base["NAME"], Path("proyecto/db.sqlite3"))

    def test_supabase_conserva_credenciales_sin_parsear_url_y_carga_driver(self):
        base = configurar_base(Path("proyecto"), {
            "DB_ENGINE": "postgresql", "PGHOST": "host.ejemplo",
            "PGDATABASE": "postgres", "PGUSER": "postgres.proyecto",
            "PGPASSWORD": "clave@con#simbolos", "PGPORT": "5432",
        })
        self.assertEqual(base["PASSWORD"], "clave@con#simbolos")
        self.assertEqual(base["OPTIONS"]["sslmode"], "require")
        self.assertEqual(base["USER"], "postgres.proyecto")
        self.assertIsNotNone(load_backend(base["ENGINE"]).DatabaseWrapper)

    def test_postgres_incompleto_falla_sin_mostrar_secretos(self):
        with self.assertRaises(ImproperlyConfigured) as error:
            configurar_base(Path("proyecto"), {
                "DB_ENGINE": "postgresql", "PGPASSWORD": "secreto",
            })
        self.assertIn("PGHOST", str(error.exception))
        self.assertNotIn("secreto", str(error.exception))

    def test_motor_incorrecto_no_cae_silenciosamente_a_sqlite(self):
        with self.assertRaises(ImproperlyConfigured):
            configurar_base(Path("proyecto"), {"DB_ENGINE": "postgre"})
