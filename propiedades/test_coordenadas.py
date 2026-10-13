from datetime import timedelta
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

import requests
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from geopy.exc import GeocoderTimedOut

from propiedades.coordenadas import diagnosticar, direccion_completa, punto_publicado
from propiedades.geocodificacion import aplicar_resultado, resolver_direccion, validar_resultados
from propiedades.ingesta import importar_fuente
from propiedades.models import ConsultaDireccion, Propiedad
from propiedades.scraping.contratos import DetallesPropiedad, PublicacionNormalizada
from propiedades.scraping.gaggiotti import leer_detalles
from propiedades.views import serializar_propiedad


def propiedad(**datos):
    valores = dict(fuente="Gaggiotti", identificador_fuente="1", direccion="Necochea 142",
                   ciudad="Rafaela", provincia="Santa Fe", ciudad_origen="fuente",
                   provincia_origen="fuente", en_venta=True,
                   latitud=-31.25, longitud=-61.49, url_original="https://ejemplo.test/1")
    valores.update(datos)
    return Propiedad(**valores)


def resultado(**datos):
    raw = dict(lat="-31.251", lon="-61.491", type="house", addresstype="house",
               osm_type="node", osm_id=123,
               address=dict(country_code="ar", city="Rafaela", state="Santa Fe",
                            road="Necochea", house_number="142"))
    raw.update(datos)
    return SimpleNamespace(raw=raw)


class ValidacionCoordenadasTests(SimpleTestCase):
    def test_direcciones_con_altura_y_unidad_separada(self):
        for texto, calle, altura in (("Necochea 142", "Necochea", "142"),
                                    ("9 de Julio 829", "9 de Julio", "829"),
                                    ("Bv. Sta. Fe 202 1º", "Bv. Sta. Fe", "202"),
                                    ("Necochea 142 Piso 2 Dpto 5", "Necochea", "142")):
            with self.subTest(texto=texto):
                direccion = direccion_completa(propiedad(direccion=texto))
                self.assertEqual((direccion["calle"], direccion["altura"]), (calle, altura))

    def test_no_inventa_altura_ni_localidad(self):
        for texto in ("9 de Julio", "San Martín al 100", "Ruta 70", "Necochea s/n",
                      "Necochea esq. Alvear", "Lote 142", "Edificio Mayo Piso 1º Ofic. 9",
                      "Necochea 142-144", "Necochea 142/144", "Necochea 142 A", "142",
                      "Necochea 142 y 144", "Necochea 142 - 144", "Edificio Mayo Cochera 4"):
            with self.subTest(texto=texto):
                self.assertIsNone(direccion_completa(propiedad(direccion=texto)))
        for datos in ({"ciudad": ""}, {"ciudad_origen": "nominatim_inversa"},
                      {"provincia_origen": "nominatim_inversa"}):
            self.assertIsNone(direccion_completa(propiedad(**datos)))

    def test_acepta_solo_direccion_completa_univoca_sin_promover_exactitud(self):
        estado, datos = validar_resultados([resultado()], direccion_completa(propiedad()))
        self.assertEqual(estado, "aceptado")
        self.assertEqual(datos["precision"], "geocodificada_direccion")
        self.assertEqual(datos["latitud"], -31.251)

    def test_rechaza_ciudad_calle_altura_pais_y_provincia_distintas(self):
        for campo, valor in (("city", "Lehmann"), ("road", "Alvear"), ("house_number", "143"),
                             ("country_code", "uy"), ("state", "Córdoba"), ("town", "Lehmann")):
            raw = resultado().raw
            raw["address"][campo] = valor
            with self.subTest(campo=campo):
                self.assertEqual(validar_resultados([SimpleNamespace(raw=raw)], direccion_completa(propiedad()))[0], "ambiguo")

    def test_ausencias_centros_y_coordenadas_invalidas_no_se_aceptan(self):
        malos = [resultado(type="city", addresstype="city"), resultado(address={}),
                 resultado(lat="nan"), resultado(lon=181), resultado(lat=True),
                 SimpleNamespace(raw=[]), resultado(lat=None)]
        for dato in malos:
            self.assertEqual(validar_resultados([dato], direccion_completa(propiedad()))[0], "ambiguo")
        self.assertEqual(validar_resultados(None, direccion_completa(propiedad()))[0], "sin_resultado")

    def test_multiples_coincidencias_y_limite_saturado_son_ambiguos(self):
        for datos in ([resultado(), resultado(lon=-61.492)], [resultado()] * 5):
            self.assertEqual(validar_resultados(datos, direccion_completa(propiedad()))[0], "ambiguo")

    def test_abreviaturas_controladas_y_numeracion_de_calle(self):
        p = propiedad(direccion="Bv. Sta. Fe 202")
        raw = resultado().raw
        raw["address"].update(road="Bulevar Santa Fe", house_number="202")
        self.assertEqual(validar_resultados([SimpleNamespace(raw=raw)], direccion_completa(p))[0], "aceptado")

    def test_gaggiotti_conserva_metodo_sin_tratar_rooftop_como_exactitud(self):
        for metodo in ("ROOFTOP", "APPROXIMATE", "GEOMETRIC_CENTER", "RANGE_INTERPOLATED"):
            detalle = leer_detalles({"id": 1, "geoLatitude": -31.25, "geoLongitude": -61.49, "gmLocationType": metodo})
            self.assertEqual(detalle.metodo_ubicacion_fuente, metodo)
            self.assertIsNone(detalle.ubicacion_aproximada)


class DiagnosticoTests(TestCase):
    def crear(self, **datos):
        p = propiedad(**datos)
        p.save()
        return p

    def test_detecta_cinco_puertas_diferentes_no_cinco_unidades(self):
        for i in range(5):
            self.crear(identificador_fuente=str(i), direccion=f"Necochea {140+i}")
        informe = diagnosticar()
        self.assertEqual(len(informe["grupos"]), 1)
        self.assertEqual(len(informe["candidatos"]), 5)
        Propiedad.objects.all().delete()
        for i in range(5):
            self.crear(identificador_fuente=str(i), direccion=f"Necochea 142 Piso {i}")
        self.assertEqual(diagnosticar()["candidatos"], [])

    def test_separa_fuentes_ciudades_y_publicaciones_inactivas(self):
        for i in range(4):
            self.crear(identificador_fuente=str(i), direccion=f"Necochea {140+i}")
        self.crear(identificador_fuente="5", direccion="Necochea 155", en_venta=False)
        self.crear(identificador_fuente="6", direccion="Necochea 156", ciudad="Lehmann")
        self.crear(identificador_fuente="7", direccion="Necochea 157", fuente="Avantix")
        self.assertEqual(diagnosticar()["candidatos"], [])

    def test_metodo_aproximado_se_detecta_sin_repeticiones_no_rooftop(self):
        self.crear(metodo_ubicacion_fuente="GEOMETRIC_CENTER")
        self.crear(identificador_fuente="2", metodo_ubicacion_fuente="ROOFTOP")
        self.assertEqual(len(diagnosticar()["candidatos"]), 1)

    def test_diagnostico_y_vista_previa_no_consultan_ni_escriben(self):
        p = self.crear(metodo_ubicacion_fuente="APPROXIMATE")
        with patch("propiedades.geocodificacion.consultar_direccion") as consultar:
            call_command("diagnosticar_coordenadas", stdout=StringIO())
            salida = StringIO()
            call_command("enriquecer_coordenadas", stdout=salida)
        consultar.assert_not_called()
        self.assertIn("Sin HTTP ni escrituras", salida.getvalue())
        self.assertFalse(ConsultaDireccion.objects.exists())
        p.refresh_from_db()
        self.assertEqual(p.geocodificacion, {})

    def test_limites_invalidos_son_error(self):
        for kwargs in ({"umbral": 1}, {"limite": 0}, {"limite": 101}, {"desde_id": -1}):
            with self.assertRaises(CommandError):
                call_command("enriquecer_coordenadas", stdout=StringIO(), **kwargs)

    def test_cursor_permite_continuar_despues_de_candidatos_no_resueltos(self):
        a = self.crear(metodo_ubicacion_fuente="APPROXIMATE")
        b = self.crear(identificador_fuente="2", metodo_ubicacion_fuente="APPROXIMATE")
        salida = StringIO()
        call_command("enriquecer_coordenadas", desde_id=a.pk, stdout=salida)
        self.assertNotIn(f'"id": {a.pk},', salida.getvalue())
        self.assertIn(f'"id": {b.pk},', salida.getvalue())


class EnriquecerCoordenadasTests(TestCase):
    def setUp(self):
        self.p = propiedad(metodo_ubicacion_fuente="APPROXIMATE")
        self.p.save()
        self.consultar = patch("propiedades.geocodificacion.consultar_direccion").start()
        self.addCleanup(patch.stopall)
        self.consultar.return_value = [resultado()]

    def test_cache_positivo_negativo_errores_y_proveedor(self):
        cache = resolver_direccion(self.p)
        self.assertEqual(cache.estado, "aceptado")
        self.assertEqual(resolver_direccion(self.p).pk, cache.pk)
        self.assertEqual(self.consultar.call_count, 1)
        parametros = self.consultar.call_args.kwargs
        self.assertFalse(parametros["exactly_one"])
        self.assertEqual(parametros["country_codes"], "ar")
        with override_settings(NOMINATIM_DOMAIN="otro.example"):
            resolver_direccion(self.p)
        self.assertEqual(self.consultar.call_count, 2)
        ConsultaDireccion.objects.all().delete()
        self.consultar.return_value = []
        self.assertEqual(resolver_direccion(self.p).estado, "sin_resultado")
        resolver_direccion(self.p)
        self.assertEqual(self.consultar.call_count, 3)
        ConsultaDireccion.objects.all().delete()
        self.consultar.side_effect = GeocoderTimedOut("timeout")
        error = resolver_direccion(self.p)
        self.assertEqual(error.estado, "error")
        resolver_direccion(self.p)
        self.assertEqual(self.consultar.call_count, 4)
        ConsultaDireccion.objects.filter(pk=error.pk).update(consultada_en=timezone.now()-timedelta(days=2))
        resolver_direccion(self.p)
        self.assertEqual(self.consultar.call_count, 5)

    def test_caduca_cache_normal_sin_reconsultar_cada_ingesta(self):
        cache = resolver_direccion(self.p)
        ConsultaDireccion.objects.filter(pk=cache.pk).update(consultada_en=timezone.now()-timedelta(days=31))
        resolver_direccion(self.p)
        self.assertEqual(self.consultar.call_count, 2)

    def test_sin_direccion_no_consulta(self):
        self.p.ciudad = ""
        self.assertIsNone(resolver_direccion(self.p))
        self.consultar.assert_not_called()

    def test_consultar_no_modifica_publicacion_aplicar_conserva_original_y_api(self):
        call_command("enriquecer_coordenadas", consultar=True, stdout=StringIO())
        self.p.refresh_from_db()
        self.assertFalse(self.p.geocodificacion)
        original = punto_publicado(self.p)
        call_command("enriquecer_coordenadas", aplicar=True, stdout=StringIO())
        self.p.refresh_from_db()
        self.assertEqual(self.p.latitud, -31.251)
        self.assertEqual(self.p.coordenadas_fuente, original)
        self.assertIsNone(self.p.ubicacion_aproximada)
        self.assertEqual(self.p.geocodificacion["original"], original)
        api = serializar_propiedad(self.p, None)
        self.assertEqual(api["ubicacion_info"]["precision"], "geocodificada_direccion")
        self.assertEqual(api["ubicacion_info"]["punto_original"]["latitud"], -31.25)
        self.assertEqual(len(diagnosticar()["candidatos"]), 1)
        self.assertTrue(diagnosticar()["candidatos"][0]["ya_enriquecida"])
        call_command("enriquecer_coordenadas", aplicar=True, stdout=StringIO())
        self.assertEqual(self.consultar.call_count, 1)

    def test_no_aplica_ambiguos_ni_sobre_fila_modificada_durante_http(self):
        cache = resolver_direccion(self.p)
        Propiedad.objects.filter(pk=self.p.pk).update(direccion="Alvear 200")
        self.assertFalse(aplicar_resultado(self.p, cache))
        self.p.refresh_from_db()
        cache.estado = "ambiguo"
        self.assertFalse(aplicar_resultado(self.p, cache))
        self.assertFalse(self.p.geocodificacion)

    def test_no_aplica_a_fila_retirada(self):
        cache = resolver_direccion(self.p)
        Propiedad.objects.filter(pk=self.p.pk).update(en_venta=False)
        self.assertFalse(aplicar_resultado(self.p, cache))

    def test_no_acepta_cache_de_otra_direccion(self):
        cache = resolver_direccion(self.p)
        cache.consulta["direccion"]["altura"] = "143"
        self.assertFalse(aplicar_resultado(self.p, cache))

    def test_restauracion_tiene_vista_previa_y_recupera_original(self):
        self.assertTrue(aplicar_resultado(self.p, resolver_direccion(self.p)))
        call_command("restaurar_coordenadas", id=self.p.pk, stdout=StringIO())
        self.p.refresh_from_db()
        self.assertEqual(self.p.latitud, -31.251)
        call_command("restaurar_coordenadas", id=self.p.pk, aplicar=True, stdout=StringIO())
        self.p.refresh_from_db()
        self.assertEqual((self.p.latitud, self.p.longitud), (-31.25, -61.49))
        self.assertFalse(self.p.geocodificacion)
        self.assertTrue(self.p.coordenadas_fuente)

    def test_error_del_proveedor_no_impide_continuar_otras_publicaciones(self):
        otra = propiedad(identificador_fuente="2", direccion="Necochea 143", metodo_ubicacion_fuente="APPROXIMATE")
        otra.save()
        respuesta = resultado()
        respuesta.raw["address"]["house_number"] = "143"
        self.consultar.side_effect = [GeocoderTimedOut("timeout"), [respuesta]]
        call_command("enriquecer_coordenadas", aplicar=True, stdout=StringIO())
        self.p.refresh_from_db()
        self.assertEqual(self.p.latitud, -31.25)
        self.assertFalse(self.p.geocodificacion)
        self.assertEqual(ConsultaDireccion.objects.filter(estado="error").count(), 1)
        otra.refresh_from_db()
        self.assertTrue(otra.geocodificacion)

    def ingestar(self, **detalles):
        ficha = dict(ciudad="Rafaela", provincia="Santa Fe", latitud=-31.25, longitud=-61.49,
                     metodo_ubicacion_fuente="APPROXIMATE")
        ficha.update(detalles)
        adaptador = SimpleNamespace(nombre="Gaggiotti", operaciones=("venta",),
            extraer=lambda op: [PublicacionNormalizada(identificador_fuente="1", url_original=self.p.url_original,
                                                     direccion=self.p.direccion)],
            extraer_detalles=lambda url: DetallesPropiedad(**ficha))
        with patch("propiedades.ingesta.time.sleep"), patch("propiedades.ingesta.obtener_coordenadas") as geocodificar:
            importar_fuente(adaptador)
            geocodificar.assert_not_called()
        self.p.refresh_from_db()

    def test_ingesta_repetida_preserva_correccion_sin_http_adicional(self):
        self.assertTrue(aplicar_resultado(self.p, resolver_direccion(self.p)))
        for _ in range(2):
            self.ingestar()
            self.assertEqual(self.p.latitud, -31.251)
            self.assertTrue(self.p.geocodificacion)
            self.assertEqual(self.p.coordenadas_fuente["latitud"], -31.25)
        self.assertEqual(Propiedad.objects.count(), 1)

    def test_ingesta_refresca_mejora_aplicada_durante_descarga_de_ficha(self):
        cache = resolver_direccion(self.p)
        def descargar(url):
            self.assertTrue(aplicar_resultado(self.p, cache))
            return DetallesPropiedad(ciudad="Rafaela", provincia="Santa Fe", latitud=-31.25,
                                     longitud=-61.49, metodo_ubicacion_fuente="APPROXIMATE")
        adaptador = SimpleNamespace(nombre="Gaggiotti", operaciones=("venta",),
            extraer=lambda op: [PublicacionNormalizada(identificador_fuente="1", url_original=self.p.url_original,
                                                     direccion=self.p.direccion)], extraer_detalles=descargar)
        with patch("propiedades.ingesta.time.sleep"):
            importar_fuente(adaptador)
        self.p.refresh_from_db()
        self.assertEqual(self.p.latitud, -31.251)
        self.assertEqual(self.p.coordenadas_fuente["latitud"], -31.25)
        self.assertTrue(self.p.geocodificacion)

    def test_primera_ingesta_con_metodo_no_pisa_mejora_de_una_fila_historica(self):
        self.p.metodo_ubicacion_fuente = ""
        self.p.save()
        self.assertTrue(aplicar_resultado(self.p, resolver_direccion(self.p)))
        self.ingestar()
        self.assertEqual(self.p.latitud, -31.251)
        self.assertTrue(self.p.geocodificacion)
        self.assertEqual(self.p.coordenadas_fuente["metodo"], "APPROXIMATE")

    def test_cambio_de_coordenada_o_direccion_invalida_la_mejora(self):
        self.assertTrue(aplicar_resultado(self.p, resolver_direccion(self.p)))
        self.ingestar(latitud=-31.26)
        self.assertEqual(self.p.latitud, -31.26)
        self.assertEqual(self.p.geocodificacion, {})
        self.assertTrue(aplicar_resultado(self.p, resolver_direccion(self.p)))
        # La siguiente ficha conserva el punto publicado pero cambia ciudad.
        self.ingestar(ciudad="Lehmann", latitud=-31.26)
        self.assertEqual(self.p.geocodificacion, {})
        self.assertEqual(self.p.latitud, -31.26)

    def test_error_de_ficha_conserva_mejora_y_evidencia(self):
        self.assertTrue(aplicar_resultado(self.p, resolver_direccion(self.p)))
        adaptador = SimpleNamespace(nombre="Gaggiotti", operaciones=("venta",),
            extraer=lambda op: [PublicacionNormalizada(identificador_fuente="1", url_original=self.p.url_original,
                                                     direccion=self.p.direccion)])
        def fallar(url):
            raise requests.HTTPError("502")
        adaptador.extraer_detalles = fallar
        with patch("propiedades.ingesta.time.sleep"):
            resumen = importar_fuente(adaptador)
        self.p.refresh_from_db()
        self.assertEqual(resumen.errores_detalle, 1)
        self.assertEqual(self.p.latitud, -31.251)
        self.assertTrue(self.p.geocodificacion)
