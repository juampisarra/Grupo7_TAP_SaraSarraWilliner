from decimal import Decimal
from io import StringIO
from unittest.mock import Mock, patch

import requests
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from propiedades.busqueda.indice import documento
from propiedades.models import Propiedad
from propiedades.scraping.gaggiotti import (
    AdaptadorGaggiotti, leer_coordenadas, leer_detalles, leer_precio,
    leer_publicacion, leer_ubicacion,
)


MODULO = "propiedades.scraping.gaggiotti"


def aviso(clave=123):
    """Datos sintéticos con la estructura de la respuesta pública verificada."""
    return {
        "id": clave, "publicationTitle": "Casa con cochera", "type": {"name": "Casa"},
        "address": "San Martín al 100", "realAddress": "San Martín 123",
        "description": "<p>Casa &amp; jardín</p><script>no indexar</script>",
        "suiteAmount": 2, "roomAmount": 4, "bathroomAmount": 1,
        "parkingLotAmount": 1, "tags": [{"name": "Gas Natural"}, {"name": "Patio"}],
        "customTags": [], "extraAttributes": [{"name": "Galería", "value": "cubierta"}],
        "location": {"fullLocation": "Argentina | Santa Fe | Castellanos | Rafaela | Barrio Centro"},
        "geoLatitude": "-31.25", "geoLongitude": "-61.49", "gmLocationType": "ROOFTOP",
        "webPrice": True,
        "operations": [
            {"operationType": "Compra-Venta", "prices": [{"currency": "USD", "period": "0", "price": 125000.25}]},
            {"operationType": "Alquiler", "prices": [{"currency": "ARS", "period": "0", "price": 650000}]},
        ],
    }


def respuesta(datos):
    resultado = Mock()
    resultado.json.return_value = {"communicationStatus": 200, "response": datos}
    return resultado


def pagina(avisos, offset=0, total=None, limite=20):
    total = len(avisos) if total is None else total
    return respuesta({"properties": avisos, "pagination": {
        "limit": limite, "offset": offset, "totalCount": total,
        "remaining": total - offset - len(avisos),
    }})


class ParserGaggiottiTests(SimpleTestCase):
    def test_normaliza_identidad_operaciones_y_precios_por_separado(self):
        venta = leer_publicacion(aviso(), "venta")
        alquiler = leer_publicacion(aviso(), "alquiler")
        self.assertEqual(venta.identificador_fuente, "123")
        self.assertEqual(venta.url_original, "https://www.gaggiotti.com.ar/propiedad/compra-venta/123/")
        self.assertEqual((venta.precio, venta.moneda), (Decimal("125000.25"), "USD"))
        self.assertEqual((alquiler.precio, alquiler.moneda), (Decimal("650000"), "ARS"))
        self.assertEqual((venta.en_venta, venta.en_alquiler), (True, False))
        self.assertEqual((alquiler.en_venta, alquiler.en_alquiler), (False, True))
        self.assertEqual(venta.direccion, "San Martín 123")
        self.assertEqual(venta.tipo, "Casa")

    def test_precio_oculto_o_ausente_no_se_publica(self):
        for bandera in (False, None, "true", 1):
            dato = aviso()
            dato["webPrice"] = bandera
            self.assertEqual(leer_precio(dato, "venta"), (None, ""))
        dato = aviso()
        dato["operations"][0]["prices"] = []
        self.assertEqual(leer_precio(dato, "venta"), (None, ""))

    def test_primer_precio_coincide_con_el_frontend_sin_conversion(self):
        dato = aviso()
        dato["operations"][0]["prices"].append({"currency": "ARS", "period": "0", "price": 999})
        self.assertEqual(leer_precio(dato, "venta"), (Decimal("125000.25"), "USD"))
        dato["operations"][0]["prices"][0]["price"] = 0
        self.assertEqual(leer_precio(dato, "venta"), (Decimal("0"), "USD"))

    def test_moneda_o_periodo_desconocidos_no_se_asumen(self):
        for campo, valor in (("currency", "EUR"), ("period", "1")):
            dato = aviso()
            dato["operations"][0]["prices"][0][campo] = valor
            with self.assertLogs(MODULO, level="WARNING"):
                self.assertEqual(leer_precio(dato, "venta"), (None, ""))

    def test_importes_invalidos_y_operacion_ambigua_son_errores(self):
        for valor in (-1, "NaN", "Infinity", True, "1.234,56", 1.234, 10**13):
            with self.subTest(valor=valor):
                dato = aviso()
                dato["operations"][0]["prices"][0]["price"] = valor
                with self.assertRaises(ValueError):
                    leer_precio(dato, "venta")
        dato = aviso()
        dato["operations"] = dato["operations"][:1] * 2
        with self.assertRaises(ValueError):
            leer_precio(dato, "venta")
        with self.assertRaises(ValueError):
            leer_precio(dato, "alquiler")

    def test_detalles_limpian_html_y_respetan_dormitorios_ambientes_y_cero(self):
        dato = aviso()
        dato["bathroomAmount"] = 0
        detalle = leer_detalles(dato)
        self.assertEqual(detalle.descripcion, "Casa & jardín")
        self.assertEqual((detalle.dormitorios, detalle.ambientes, detalle.banos), (2, 4, 0))
        self.assertIn("Gas Natural", detalle.caracteristicas)
        self.assertIn("Galería: cubierta", detalle.caracteristicas)
        self.assertIn("Cocheras: 1", detalle.caracteristicas)
        self.assertEqual((detalle.ciudad, detalle.provincia, detalle.zona), ("Rafaela", "Santa Fe", "Barrio Centro"))

    def test_ausencias_no_inventan_cantidades_ni_localidad(self):
        detalle = leer_detalles({"id": 123})
        self.assertIsNone(detalle.dormitorios)
        self.assertIsNone(detalle.ciudad)
        self.assertIsNone(detalle.latitud)
        self.assertIsNone(detalle.titulo)
        for valor in (-1, 1.5, True, 32768):
            with self.subTest(valor=valor), self.assertRaises(ValueError):
                leer_detalles({"id": 123, "suiteAmount": valor})

    def test_jerarquia_no_confunde_departamento_con_ciudad(self):
        dato = aviso()
        dato["location"]["fullLocation"] = "Argentina | Santa Fe | Castellanos "
        self.assertEqual(leer_ubicacion(dato), {"provincia": "Santa Fe", "ciudad": None, "zona": None})
        dato["location"]["fullLocation"] = "Argentina | Santa Fe | Castellanos | Bella Italia"
        self.assertEqual(leer_ubicacion(dato)["ciudad"], "Bella Italia")
        dato["location"]["fullLocation"] = "Otro país | Provincia | Ciudad"
        with self.assertLogs(MODULO, level="WARNING"):
            self.assertEqual(leer_ubicacion(dato), {})

    def test_coordenadas_y_precision_no_se_inventan(self):
        dato = aviso()
        for tipo in ("ROOFTOP", "BY_HAND", "APPROXIMATE", None):
            dato["gmLocationType"] = tipo
            ubicacion = leer_coordenadas(dato)
            self.assertEqual((ubicacion["latitud"], ubicacion["longitud"]), (-31.25, -61.49))
            self.assertIsNone(ubicacion["ubicacion_aproximada"])
            self.assertIsNone(ubicacion["radio_ubicacion_m"])
        dato.update(geoLatitude=0, geoLongitude=0)
        self.assertEqual(leer_coordenadas(dato)["latitud"], 0)
        for par in ((None, 1), (91, 0), (0, -181), (True, 1), ("nan", 1), (1, "inf")):
            dato.update(zip(("geoLatitude", "geoLongitude"), par))
            with self.subTest(par=par), self.assertLogs(MODULO, level="WARNING"):
                self.assertEqual(leer_coordenadas(dato), {})


class RedGaggiottiTests(SimpleTestCase):
    @patch(f"{MODULO}.time.sleep")
    @patch(f"{MODULO}.requests.post")
    def test_paginacion_con_lote_final_corto_y_parametros_verificados(self, post, dormir):
        post.side_effect = [pagina([aviso(1), aviso(2)], total=3), pagina([aviso(3)], offset=2, total=3)]
        datos = AdaptadorGaggiotti().extraer("venta")
        self.assertEqual([p.identificador_fuente for p in datos], ["1", "2", "3"])
        self.assertEqual([c.kwargs["json"]["offset"] for c in post.call_args_list], [0, 2])
        self.assertEqual(post.call_args.kwargs["json"]["operationTypes"], [1])
        self.assertEqual(post.call_args.kwargs["timeout"], 15)
        dormir.assert_called_once_with(0.5)

    @patch(f"{MODULO}.requests.post")
    def test_listado_vacio_valido_y_operacion_invalida(self, post):
        post.return_value = pagina([])
        self.assertEqual(AdaptadorGaggiotti().extraer("alquiler"), [])
        self.assertEqual(post.call_args.kwargs["json"]["operationTypes"], [2])
        with self.assertRaises(ValueError):
            AdaptadorGaggiotti().extraer("temporario")
        self.assertEqual(post.call_count, 1)

    @patch(f"{MODULO}.time.sleep")
    @patch(f"{MODULO}.requests.post")
    def test_error_http_json_o_esquema_no_equivale_a_listado_vacio(self, post, dormir):
        for respuesta_mala in (respuesta({}), respuesta({"properties": []}), Mock()):
            respuesta_mala.raise_for_status.return_value = None
            post.return_value = respuesta_mala
            with self.subTest(respuesta=respuesta_mala), self.assertRaises(ValueError):
                AdaptadorGaggiotti().extraer("venta")
        post.return_value = respuesta({})
        post.return_value.raise_for_status.side_effect = requests.HTTPError("503")
        with self.assertRaises(requests.HTTPError):
            AdaptadorGaggiotti().extraer("venta")
        post.return_value = respuesta({})
        post.return_value.json.side_effect = ValueError("No es JSON")
        with self.assertRaises(ValueError):
            AdaptadorGaggiotti().extraer("venta")

    @patch(f"{MODULO}.time.sleep")
    @patch(f"{MODULO}.requests.post")
    def test_paginacion_repetida_cambiante_o_truncada_falla(self, post, dormir):
        for segunda in (pagina([aviso(1)], offset=1, total=2), pagina([], offset=1, total=2), pagina([aviso(2)], offset=1, total=3), pagina([aviso(2)], offset=0, total=2)):
            post.side_effect = [pagina([aviso(1)], total=2), segunda]
            with self.subTest(segunda=segunda), self.assertRaises(ValueError):
                AdaptadorGaggiotti().extraer("venta")

    @patch(f"{MODULO}.time.sleep")
    @patch(f"{MODULO}.requests.post")
    def test_limite_de_paginas_no_devuelve_ingesta_incompleta(self, post, dormir):
        post.return_value = pagina([aviso()], total=2)
        with patch(f"{MODULO}.MAX_PAGINAS", 1), self.assertRaises(RuntimeError):
            AdaptadorGaggiotti().extraer("venta")

    @patch(f"{MODULO}.requests.get")
    def test_ficha_usa_endpoint_fijo_y_verifica_identidad(self, get):
        url = leer_publicacion(aviso(), "venta").url_original
        get.return_value = respuesta(aviso())
        self.assertEqual(AdaptadorGaggiotti().extraer_detalles(url).dormitorios, 2)
        self.assertEqual(get.call_args.args[0], "https://www.gaggiotti.com.ar/api/Property/123")
        get.return_value = respuesta(aviso(999))
        with self.assertRaises(ValueError):
            AdaptadorGaggiotti().extraer_detalles(url)
        get.reset_mock()
        with self.assertRaises(ValueError):
            AdaptadorGaggiotti().extraer_detalles("https://otro.test/propiedad/venta/123/")
        get.assert_not_called()

    @patch(f"{MODULO}.requests.get")
    @patch(f"{MODULO}.requests.post")
    def test_reutiliza_ficha_completa_solo_en_la_instancia_y_la_refresca(self, post, get):
        adaptador = AdaptadorGaggiotti()
        dato = aviso()
        post.return_value = pagina([dato])
        url = adaptador.extraer("venta")[0].url_original
        self.assertEqual(adaptador.extraer_detalles(url).dormitorios, 2)
        get.assert_not_called()
        dato = aviso()
        dato["suiteAmount"] = 3
        post.return_value = pagina([dato])
        adaptador.extraer("venta")
        self.assertEqual(adaptador.extraer_detalles(url).dormitorios, 3)
        get.return_value = respuesta(aviso())
        self.assertEqual(AdaptadorGaggiotti().extraer_detalles(url).dormitorios, 2)
        get.assert_called_once()

    @patch(f"{MODULO}.requests.get")
    @patch(f"{MODULO}.requests.post")
    @patch(f"{MODULO}.time.sleep")
    def test_listado_incompleto_no_publica_fichas_para_reutilizar(self, dormir, post, get):
        adaptador = AdaptadorGaggiotti()
        post.side_effect = [pagina([aviso()], total=2), requests.Timeout("Página 2")]
        with self.assertRaises(requests.Timeout):
            adaptador.extraer("venta")
        get.return_value = respuesta(aviso())
        adaptador.extraer_detalles(leer_publicacion(aviso(), "venta").url_original)
        get.assert_called_once()


class IngestaGaggiottiTests(TestCase):
    @patch("propiedades.ingesta.obtener_coordenadas")
    @patch("propiedades.ingesta.time.sleep")
    @patch(f"{MODULO}.requests.get")
    @patch(f"{MODULO}.requests.post")
    def test_ingesta_real_del_contrato_actualiza_sin_duplicar_y_genera_documento(self, post, get, dormir, geocodificar):
        dato = aviso()
        post.return_value = pagina([dato])
        get.return_value = respuesta(dato)
        Propiedad.objects.create(fuente="Brega", identificador_fuente="123")
        for precio in (650000, 700000):
            dato["operations"][1]["prices"][0]["price"] = precio
            call_command("importar_propiedades", "gaggiotti", stdout=StringIO(), stderr=StringIO())
            p = Propiedad.objects.get(fuente="Gaggiotti", identificador_fuente="123")
            p.full_clean()
            self.assertEqual(p.precio_alquiler, precio)
            self.assertEqual(p.precio_venta, Decimal("125000.25"))
            self.assertTrue(p.en_venta and p.en_alquiler and p.dormitorios_verificados)
            self.assertEqual(p.ciudad_origen, "fuente")
            self.assertIsNone(p.ubicacion_aproximada)
            self.assertEqual(Propiedad.objects.count(), 2)
        geocodificar.assert_not_called()
        get.assert_not_called()
        doc = documento(p)
        self.assertEqual(doc["fuente"], "Gaggiotti")
        self.assertIn("Gas Natural", doc["caracteristicas"])
        self.assertNotIn("latitud", doc)

    @patch("propiedades.ingesta.time.sleep")
    @patch(f"{MODULO}.requests.get")
    @patch(f"{MODULO}.requests.post")
    def test_fallo_ficha_conserva_detalles_y_no_aborta_fuente(self, post, get, dormir):
        Propiedad.objects.create(fuente="Gaggiotti", identificador_fuente="123", descripcion="Anterior", dormitorios=3)
        dato = aviso()
        dato["suiteAmount"] = -1
        post.return_value = pagina([dato])
        salida = StringIO()
        call_command("importar_propiedades", "gaggiotti", stdout=salida, stderr=StringIO())
        p = Propiedad.objects.get(fuente="Gaggiotti")
        self.assertEqual((p.descripcion, p.dormitorios), ("Anterior", 3))
        self.assertIn("Errores detalle: 1", salida.getvalue())

    @patch("propiedades.ingesta.time.sleep")
    @patch(f"{MODULO}.requests.get")
    @patch(f"{MODULO}.requests.post")
    def test_fallo_de_otra_fuente_no_impide_gaggiotti_y_se_informa_parcial(self, post, get, dormir):
        from propiedades.scraping.fuentes import FUENTES

        self.assertIs(FUENTES["gaggiotti"], AdaptadorGaggiotti)
        roto = Mock(side_effect=RuntimeError("Fuente caída"))
        post.return_value = pagina([aviso()])
        get.return_value = respuesta(aviso())
        with patch("propiedades.management.commands.importar_propiedades.FUENTES", {
            "avantix": roto, "brega": roto, "gaggiotti": AdaptadorGaggiotti,
        }):
            with self.assertRaises(CommandError) as error:
                call_command("importar_propiedades", stdout=StringIO(), stderr=StringIO())
        self.assertEqual(error.exception.returncode, 3)
        self.assertEqual(Propiedad.objects.filter(fuente="Gaggiotti").count(), 1)

    @patch(f"{MODULO}.requests.post")
    def test_fallo_listado_gaggiotti_conserva_datos_y_permite_fuente_siguiente(self, post):
        from propiedades.ingesta import ResumenIngesta
        from propiedades.management.commands import importar_propiedades as comando

        Propiedad.objects.create(fuente="Gaggiotti", identificador_fuente="anterior")
        post.side_effect = requests.Timeout("Listado Gaggiotti inaccesible")
        original = comando.importar_fuente
        siguiente = Mock(nombre="Prueba")

        def importar(adaptador, **kwargs):
            if adaptador is siguiente:
                return ResumenIngesta()
            return original(adaptador, **kwargs)

        with patch.object(comando, "FUENTES", {"gaggiotti": AdaptadorGaggiotti, "posterior": lambda: siguiente}), patch.object(comando, "importar_fuente", side_effect=importar) as flujo:
            with self.assertRaises(CommandError) as error:
                call_command("importar_propiedades", stdout=StringIO(), stderr=StringIO())
        self.assertEqual(error.exception.returncode, 3)
        self.assertEqual(flujo.call_count, 2)
        self.assertTrue(Propiedad.objects.filter(fuente="Gaggiotti", identificador_fuente="anterior").exists())
