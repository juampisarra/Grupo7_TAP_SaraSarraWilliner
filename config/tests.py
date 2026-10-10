from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase
from django.db.utils import load_backend

from config.database import configurar_base
from django.test import override_settings
from unittest.mock import patch
from config.mail import CorreoDeshabilitado


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


@override_settings(SECURE_SSL_REDIRECT=False)
class HealthTests(SimpleTestCase):
    def test_health_responde_sin_base_ni_servicios_externos(self):
        # SimpleTestCase prohíbe las consultas a la base de datos.
        with patch("requests.sessions.Session.request", side_effect=AssertionError("HTTP externo")):
            respuesta = self.client.get("/health/")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json(), {"status": "ok"})
        self.assertIn("no-store", respuesta.headers["Cache-Control"])
        self.assertEqual(self.client.head("/health/").content, b"")
        self.assertEqual(self.client.post("/health/").status_code, 405)

    @override_settings(SECURE_SSL_REDIRECT=True, SECURE_HSTS_SECONDS=3600,
                       SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"))
    def test_https_detras_de_render_no_redirige_en_bucle(self):
        self.assertEqual(self.client.get("/health/").status_code, 301)
        respuesta = self.client.get("/health/", HTTP_X_FORWARDED_PROTO="https")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.headers["Strict-Transport-Security"], "max-age=3600")

    def test_correo_desactivado_falla_explicitamente_sin_simular_entrega(self):
        with self.assertRaises(ImproperlyConfigured):
            CorreoDeshabilitado().send_messages([object()])
