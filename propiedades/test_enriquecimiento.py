from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.test import TestCase, SimpleTestCase
from django.utils import timezone
from geopy.exc import GeocoderTimedOut

from propiedades.enriquecimiento import completar_localidad, leer_localidad, ORIGEN_INVERSA
from propiedades.ingesta import importar_fuente, ResumenIngesta
from propiedades.models import Propiedad, ConsultaLocalidad
from propiedades.scraping.contratos import PublicacionNormalizada, DetallesPropiedad


def respuesta(**direccion):
    return SimpleNamespace(raw={"address": {"country_code": "ar", **direccion}})


class LecturaLocalidadTests(SimpleTestCase):
    def test_no_interpreta_barrio_o_departamento_como_ciudad(self):
        estado, ciudad, provincia = leer_localidad(respuesta(
            suburb="Barrio", county="Castellanos", state="Santa Fe",
        ))
        self.assertEqual((estado, ciudad, provincia), ("resuelto", "", "Santa Fe"))

    def test_respuestas_ambiguas_o_de_otro_pais_se_descartan(self):
        for dato in (
            respuesta(city="Rafaela", town="Lehmann", state="Santa Fe"),
            respuesta(country_code="uy", city="Otro lugar"),
        ):
            self.assertEqual(leer_localidad(dato), ("ambiguo", "", ""))

    def test_acepta_localidad_y_provincia_o_ausencia_de_resultado(self):
        self.assertEqual(leer_localidad(respuesta(village="Bella Italia", state="Santa Fe")),
                         ("resuelto", "Bella Italia", "Santa Fe"))
        self.assertEqual(leer_localidad(None), ("sin_resultado", "", ""))


class EnriquecimientoTests(TestCase):
    def setUp(self):
        self.consultar = patch("propiedades.enriquecimiento.consultar_localidad").start()
        self.addCleanup(patch.stopall)
        self.consultar.return_value = respuesta(city="Rafaela", state="Santa Fe")
        self.valores = {"latitud": -31.25, "longitud": -61.49,
                        "ubicacion_aproximada": True, "radio_ubicacion_m": 400}

    def propiedad(self, **datos):
        return Propiedad.objects.create(
            fuente="Prueba", identificador_fuente="1", url_original="https://ejemplo.test/1",
            latitud=-31.25, longitud=-61.49, **datos,
        )

    def test_opcional_sin_consultas_ni_cache_si_esta_desactivado(self):
        self.assertFalse(completar_localidad(self.valores, None))
        self.consultar.assert_not_called()
        self.assertFalse(ConsultaLocalidad.objects.exists())

    def test_completa_origen_sin_alterar_coordenadas_ni_precision(self):
        originales = self.valores.copy()
        self.assertTrue(completar_localidad(self.valores, None, habilitado=True))
        self.assertEqual(self.valores["ciudad"], "Rafaela")
        self.assertEqual(self.valores["provincia_origen"], ORIGEN_INVERSA)
        for campo, valor in originales.items():
            self.assertEqual(self.valores[campo], valor)

    def test_fuente_tiene_prioridad_y_completa_solo_el_faltante(self):
        self.valores["ciudad"] = "Rafaela"
        completar_localidad(self.valores, None, habilitado=True)
        self.assertEqual(self.valores["ciudad_origen"], "fuente")
        self.assertEqual(self.valores["provincia_origen"], ORIGEN_INVERSA)

    def test_no_consulta_si_ambos_campos_ya_existen(self):
        existente = self.propiedad(ciudad="Rafaela", provincia="Santa Fe")
        completar_localidad(self.valores, existente, habilitado=True)
        self.consultar.assert_not_called()

    def test_resultado_que_contradice_fuente_no_completa_campos_faltantes(self):
        self.valores["ciudad"] = "Lehmann"
        with self.assertLogs("propiedades.enriquecimiento", level="WARNING"):
            self.assertFalse(completar_localidad(self.valores, None, habilitado=True))
        self.assertNotIn("provincia", self.valores)
        self.assertEqual(self.valores["ciudad"], "Lehmann")

    def test_cache_persistente_se_reutiliza_entre_publicaciones(self):
        completar_localidad(self.valores.copy(), None, habilitado=True)
        completar_localidad(self.valores.copy(), None, habilitado=True)
        self.consultar.assert_called_once_with(-31.25, -61.49)
        self.assertEqual(ConsultaLocalidad.objects.count(), 1)

    def test_cache_de_resultado_vacio_y_ambiguo_no_repite_consultas(self):
        for dato in (None, respuesta(city="Rafaela", town="Lehmann")):
            ConsultaLocalidad.objects.all().delete()
            self.consultar.reset_mock()
            self.consultar.return_value = dato
            completar_localidad(self.valores.copy(), None, habilitado=True)
            completar_localidad(self.valores.copy(), None, habilitado=True)
            self.consultar.assert_called_once()

    def test_error_se_conserva_24_horas_y_luego_se_reintenta(self):
        self.consultar.side_effect = GeocoderTimedOut("timeout")
        with self.assertLogs("propiedades.enriquecimiento", level="WARNING"):
            self.assertFalse(completar_localidad(self.valores.copy(), None, habilitado=True))
        completar_localidad(self.valores.copy(), None, habilitado=True)
        self.assertEqual(self.consultar.call_count, 1)
        ConsultaLocalidad.objects.update(consultada_en=timezone.now() - timedelta(hours=25))
        self.consultar.side_effect = None
        self.assertTrue(completar_localidad(self.valores.copy(), None, habilitado=True))
        self.assertEqual(self.consultar.call_count, 2)

    def test_cambio_coordenadas_limpia_solo_datos_inferidos_incluso_desactivado(self):
        existente = self.propiedad(ciudad="Rafaela", ciudad_origen="fuente",
                                   provincia="Santa Fe", provincia_origen=ORIGEN_INVERSA)
        self.valores["latitud"] = -32
        completar_localidad(self.valores, existente, habilitado=False)
        self.assertNotIn("ciudad", self.valores)
        self.assertEqual(self.valores["provincia"], "")
        self.assertEqual(self.valores["provincia_origen"], "")
        self.consultar.assert_not_called()

    def test_cambio_coordenadas_recalcula_y_prioriza_nuevos_datos_explicitos(self):
        existente = self.propiedad(ciudad="Rafaela", ciudad_origen=ORIGEN_INVERSA,
                                   provincia="Santa Fe", provincia_origen=ORIGEN_INVERSA)
        self.valores.update(latitud=-32, ciudad="Bella Italia")
        self.consultar.return_value = respuesta(village="Bella Italia", state="Santa Fe")
        completar_localidad(self.valores, existente, habilitado=True)
        self.assertEqual(self.valores["ciudad_origen"], "fuente")
        self.assertEqual(self.valores["provincia_origen"], ORIGEN_INVERSA)
        self.consultar.assert_called_once_with(-32, -61.49)

    def test_no_consulta_sin_par_valido(self):
        for par in ((None, -61), (91, -61), (float("nan"), -61)):
            completar_localidad(dict(zip(("latitud", "longitud"), par)), None, habilitado=True)
        self.consultar.assert_not_called()

    @patch("propiedades.ingesta.time.sleep")
    def test_error_del_proveedor_no_interrumpe_ingesta_y_reintenta_desde_cache(self, sleep):
        adaptador = Mock(nombre="Prueba", operaciones=("venta",))
        adaptador.extraer.return_value = [PublicacionNormalizada("1", "https://ejemplo.test/1")]
        adaptador.extraer_detalles.return_value = DetallesPropiedad(**self.valores)
        self.consultar.side_effect = GeocoderTimedOut("timeout")
        with self.assertLogs("propiedades.enriquecimiento", level="WARNING"):
            resumen = importar_fuente(adaptador, completar_ubicacion=True)
        propiedad = Propiedad.objects.get()
        self.assertEqual(resumen.creadas, 1)
        self.assertEqual(propiedad.ciudad, "")
        self.assertEqual(propiedad.latitud, -31.25)
        importar_fuente(adaptador, completar_ubicacion=True)
        self.consultar.assert_called_once()

    @patch("propiedades.management.commands.importar_propiedades.importar_fuente")
    def test_ambos_comandos_aceptan_opcion(self, importar):
        importar.return_value = ResumenIngesta()
        for argumentos in (("importar_propiedades", "brega"), ("importar_brega",)):
            call_command(*argumentos, completar_ubicacion=True)
            self.assertTrue(importar.call_args.kwargs["completar_ubicacion"])
