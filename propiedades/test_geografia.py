from decimal import Decimal
from unittest import skipUnless

from django.db import connection, NotSupportedError
from django.test import SimpleTestCase, TestCase, override_settings
from django.template.loader import render_to_string

from .geografia import aplicar_filtros_geograficos, filtrar_radio, filtrar_area
from .models import Propiedad


class EntradasGeograficasTests(SimpleTestCase):
    def test_rechaza_incompletos_no_finitos_y_areas_invalidas(self):
        casos = [
            {"latitud": "-31"},
            {"latitud": "nan", "longitud": "-61", "radio_m": "100"},
            {"latitud": "0", "longitud": "0", "radio_m": "-1"},
            {"oeste": "10", "este": "-10", "sur": "0", "norte": "1"},
            {"incluir_aproximadas": "true"},
            {"latitud": "0", "oeste": "0"},
        ]
        for parametros in casos:
            with self.subTest(parametros=parametros), self.assertRaises(ValueError):
                aplicar_filtros_geograficos(Propiedad.objects.all(), parametros)

    @skipUnless(connection.vendor == "sqlite", "Solo verifica el respaldo SQLite")
    def test_sqlite_no_simula_calculos_geograficos(self):
        with self.assertRaises(NotSupportedError):
            filtrar_radio(Propiedad.objects.all(), 0, 0, 100)

    def test_ceros_y_ausencias_se_muestran_distintos(self):
        cero = Propiedad(dormitorios=0, latitud=0, longitud=0,
                         precio_venta=Decimal("0"), precio_alquiler=Decimal("0"))
        for operacion in ("venta", "alquiler"):
            with self.subTest(operacion=operacion):
                html = render_to_string("propiedades/lista.html", {"propiedades": [cero], "operacion": operacion})
                self.assertIn("Dormitorios: 0", html)
                self.assertIn("Coordenadas:", html)
                self.assertNotIn("Consultar precio", html)
                html = render_to_string("propiedades/lista.html", {"propiedades": [Propiedad()], "operacion": operacion})
                self.assertIn("Dormitorios: no informado", html)
                self.assertNotIn("Coordenadas:", html)
                self.assertIn("Consultar precio", html)


@skipUnless(connection.vendor == "postgresql", "Requiere una base de pruebas con PostGIS")
@override_settings(SECURE_SSL_REDIRECT=False)
class PostGISIntegracionTests(TestCase):
    def test_puntos_limites_precision_y_actualizacion(self):
        exacta = Propiedad.objects.create(fuente="test", identificador_fuente="1",
            latitud=0, longitud=0, ubicacion_aproximada=False, en_alquiler=True)
        aproximada = Propiedad.objects.create(fuente="test", identificador_fuente="2",
            latitud=0, longitud=0, ubicacion_aproximada=True, radio_ubicacion_m=400)
        desconocida = Propiedad.objects.create(fuente="test", identificador_fuente="3", latitud=0, longitud=0)
        Propiedad.objects.create(fuente="test", identificador_fuente="4", latitud=None, longitud=0)
        q = Propiedad.objects.all()
        self.assertEqual(set(filtrar_radio(q, 0, 0, 0).values_list("pk", flat=True)), {exacta.pk})
        self.assertEqual(set(filtrar_radio(q, 0, 0, 0, incluir_aproximadas=True).values_list("pk", flat=True)),
                         {exacta.pk, aproximada.pk, desconocida.pk})
        # El punto situado exactamente en el borde está incluido.
        self.assertEqual(list(filtrar_area(q, 0, 0, 1, 1)), [exacta])
        Propiedad.objects.filter(pk=exacta.pk).update(latitud=10, longitud=10)
        self.assertFalse(filtrar_radio(q, 0, 0, 1000).exists())
        self.assertEqual(self.client.get("/propiedades/?latitud=10&longitud=10&radio_m=0").status_code, 200)
