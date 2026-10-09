from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from geopy.exc import GeocoderTimedOut

from propiedades.ingesta import importar_fuente
from propiedades.models import Propiedad
from propiedades.scraping.brega import AdaptadorBrega
from propiedades.scraping.contratos import DetallesPropiedad, PublicacionNormalizada
from propiedades.scraping.geocoding import obtener_coordenadas


class GeocodingTests(SimpleTestCase):
    @patch("propiedades.scraping.geocoding.consultar_direccion")
    def test_sin_ciudad_no_consulta_ni_infiere_por_nombre_de_calle(self, consultar):
        for direccion in ("Av. Santa Fe 100", "Lehmann 200", "San Vicente 500"):
            self.assertEqual(obtener_coordenadas(direccion), (None, None))
        consultar.assert_not_called()

    @patch("propiedades.scraping.geocoding.consultar_direccion")
    def test_usa_localidad_explicita_sin_suponer_provincia(self, consultar):
        consultar.return_value = SimpleNamespace(latitude=-31.2, longitude=-61.4)
        self.assertEqual(
            obtener_coordenadas("Av. Italia 100", ciudad="Otra localidad"),
            (-31.2, -61.4),
        )
        consultar.assert_called_once_with(
            "Avenida Italia 100, Otra localidad, Argentina", timeout=10,
        )

    @patch("propiedades.scraping.geocoding.consultar_direccion")
    def test_no_encontrada_y_error_se_distinguen_en_logs(self, consultar):
        consultar.return_value = None
        self.assertEqual(obtener_coordenadas("Italia 100", "Rafaela"), (None, None))
        consultar.side_effect = GeocoderTimedOut("timeout")
        with self.assertLogs("propiedades.scraping.geocoding", level="WARNING"):
            self.assertEqual(obtener_coordenadas("Italia 100", "Rafaela"), (None, None))


class IngestaTests(TestCase):
    def setUp(self):
        self.sleep = patch("propiedades.ingesta.time.sleep").start()
        self.geocoding = patch("propiedades.ingesta.obtener_coordenadas").start()
        self.geocoding.return_value = (None, None)
        self.addCleanup(patch.stopall)
        self.dato = PublicacionNormalizada(
            identificador_fuente="123",
            url_original="https://ejemplo.test/123",
            direccion="Italia 100",
            tipo="Casa",
            precio=Decimal("120000"),
            moneda="USD",
        )
        self.adaptador = Mock()
        self.adaptador.nombre = "Prueba"
        self.adaptador.operaciones = ("venta", "alquiler")
        self.adaptador.extraer.side_effect = lambda operacion: (
            [self.dato] if operacion == "venta" else []
        )
        self.adaptador.extraer_detalles.return_value = DetallesPropiedad(dormitorios=2)

    def existente(self, **datos):
        return Propiedad.objects.create(
            fuente="Prueba", identificador_fuente="123",
            url_original=self.dato.url_original,
            direccion=datos.pop("direccion", self.dato.direccion),
            dormitorios=2, dormitorios_verificados=True, **datos,
        )

    def test_repetir_carga_actualiza_sin_duplicar_y_refresca_detalles(self):
        primero = importar_fuente(self.adaptador)
        self.dato = PublicacionNormalizada(
            identificador_fuente="123", url_original=self.dato.url_original,
            direccion="Italia 100", precio=Decimal("125000"), moneda="USD",
        )
        segundo = importar_fuente(self.adaptador)
        self.assertEqual((primero.creadas, segundo.actualizadas), (1, 1))
        self.assertEqual(Propiedad.objects.count(), 1)
        self.assertEqual(Propiedad.objects.get().precio_venta, Decimal("125000"))
        self.assertEqual(self.adaptador.extraer_detalles.call_count, 2)
        self.geocoding.assert_not_called()

    def test_unifica_operaciones_y_conserva_precios_y_monedas(self):
        alquiler = PublicacionNormalizada(
            identificador_fuente="123", url_original=self.dato.url_original,
            precio=Decimal("700000"), moneda="ARS",
        )
        self.adaptador.extraer.side_effect = lambda op: [self.dato if op == "venta" else alquiler]
        importar_fuente(self.adaptador)
        propiedad = Propiedad.objects.get()
        self.assertTrue(propiedad.en_venta and propiedad.en_alquiler)
        self.assertEqual((propiedad.precio_venta, propiedad.moneda_venta), (Decimal("120000"), "USD"))
        self.assertEqual((propiedad.precio_alquiler, propiedad.moneda_alquiler), (Decimal("700000"), "ARS"))

    def test_identificador_igual_en_otra_fuente_es_independiente(self):
        importar_fuente(self.adaptador)
        self.adaptador.nombre = "Otra fuente"
        importar_fuente(self.adaptador)
        self.assertEqual(Propiedad.objects.count(), 2)

    def test_aviso_sin_identificador_o_url_se_omite(self):
        self.adaptador.extraer.side_effect = None
        self.adaptador.extraer.return_value = [
            PublicacionNormalizada(None, "https://ejemplo.test"),
            PublicacionNormalizada("123", None),
        ]
        resumen = importar_fuente(self.adaptador)
        self.assertEqual(resumen.omitidas, 4)
        self.assertFalse(Propiedad.objects.exists())

    def test_error_de_detalle_no_impide_guardar_y_se_reintenta(self):
        self.adaptador.extraer_detalles.side_effect = requests.Timeout("timeout")
        resumen = importar_fuente(self.adaptador)
        self.assertEqual(resumen.errores_detalle, 1)
        self.assertFalse(Propiedad.objects.get().dormitorios_verificados)
        self.adaptador.extraer_detalles.side_effect = None
        self.adaptador.extraer_detalles.return_value = DetallesPropiedad()
        importar_fuente(self.adaptador)
        self.assertTrue(Propiedad.objects.get().dormitorios_verificados)
        self.assertIsNone(Propiedad.objects.get().dormitorios)

    def test_direccion_igual_reutiliza_coordenadas_incluso_cero(self):
        self.existente(latitud=0, longitud=0)
        importar_fuente(self.adaptador)
        self.geocoding.assert_not_called()
        propiedad = Propiedad.objects.get()
        self.assertEqual((propiedad.latitud, propiedad.longitud), (0, 0))

    def test_direccion_cambiada_sin_ciudad_descarta_coordenadas_anteriores(self):
        self.existente(direccion="Otra 200", latitud=-31, longitud=-61)
        importar_fuente(self.adaptador)
        propiedad = Propiedad.objects.get()
        self.assertEqual(propiedad.direccion, "Italia 100")
        self.assertIsNone(propiedad.latitud)
        self.assertIsNone(propiedad.longitud)
        self.geocoding.assert_not_called()

    def test_direccion_cambiada_geocodifica_y_si_falla_no_conserva_ubicacion_vieja(self):
        propiedad = self.existente(direccion="Otra 200", latitud=-31, longitud=-61)
        self.dato = PublicacionNormalizada(
            identificador_fuente="123", url_original=self.dato.url_original,
            direccion="Italia 100", ciudad="Rafaela", provincia="Santa Fe",
        )
        importar_fuente(self.adaptador)
        propiedad.refresh_from_db()
        self.assertEqual((propiedad.latitud, propiedad.longitud), (None, None))
        self.geocoding.assert_called_once_with(
            "Italia 100", ciudad="Rafaela", provincia="Santa Fe",
        )
        self.geocoding.return_value = (-31.2, -61.5)
        importar_fuente(self.adaptador)
        propiedad.refresh_from_db()
        self.assertEqual((propiedad.latitud, propiedad.longitud), (-31.2, -61.5))

    def test_par_incompleto_se_recalcula(self):
        self.existente(latitud=-31, longitud=None)
        self.dato = PublicacionNormalizada(
            identificador_fuente="123", url_original=self.dato.url_original,
            direccion="Italia 100", ciudad="Rafaela",
        )
        self.geocoding.return_value = (-31.2, -61.5)
        importar_fuente(self.adaptador)
        self.assertEqual(Propiedad.objects.get().longitud, -61.5)

    def test_error_listado_no_deja_importacion_parcial(self):
        self.adaptador.extraer.side_effect = [[self.dato], requests.Timeout("timeout")]
        with self.assertRaises(requests.Timeout):
            importar_fuente(self.adaptador)
        self.assertFalse(Propiedad.objects.exists())

    def test_detalles_se_persisten_y_un_error_posterior_no_los_borra(self):
        self.adaptador.extraer_detalles.return_value = DetallesPropiedad(
            titulo="Casa con cochera", descripcion="Patio y quincho",
            caracteristicas="Cocheras: 1\nParrilla", ambientes=4, banos=1,
            dormitorios=2, ciudad="Localidad explícita", provincia="Provincia",
            zona="Centro",
        )
        importar_fuente(self.adaptador)
        propiedad = Propiedad.objects.get()
        self.assertEqual(propiedad.titulo, "Casa con cochera")
        self.assertEqual(propiedad.descripcion, "Patio y quincho")
        self.assertEqual((propiedad.ambientes, propiedad.banos), (4, 1))
        self.assertEqual(propiedad.ciudad, "Localidad explícita")
        self.assertEqual(propiedad.zona, "Centro")
        self.adaptador.extraer_detalles.side_effect = requests.Timeout("timeout")
        importar_fuente(self.adaptador)
        propiedad.refresh_from_db()
        self.assertEqual(propiedad.titulo, "Casa con cochera")
        self.assertEqual(propiedad.dormitorios, 2)

    def test_cambio_de_ciudad_invalida_coordenadas_aunque_la_calle_sea_igual(self):
        propiedad = self.existente(ciudad="Anterior", latitud=-31, longitud=-61)
        self.adaptador.extraer_detalles.return_value = DetallesPropiedad(ciudad="Nueva")
        importar_fuente(self.adaptador)
        propiedad.refresh_from_db()
        self.assertEqual(propiedad.ciudad, "Nueva")
        self.assertIsNone(propiedad.latitud)
        self.geocoding.assert_called_once_with("Italia 100", ciudad="Nueva", provincia="")

    def test_coordenadas_de_fuente_se_guardan_sin_ciudad_ni_geocodificar(self):
        self.adaptador.extraer_detalles.return_value = DetallesPropiedad(
            latitud=-31.2684177, longitud=-61.4354131,
            ubicacion_aproximada=True, radio_ubicacion_m=400,
        )
        importar_fuente(self.adaptador)
        propiedad = Propiedad.objects.get()
        self.assertEqual((propiedad.latitud, propiedad.longitud), (-31.2684177, -61.4354131))
        self.assertTrue(propiedad.ubicacion_aproximada)
        self.assertEqual(propiedad.radio_ubicacion_m, 400)
        self.assertEqual(propiedad.ciudad, "")
        self.geocoding.assert_not_called()

    def test_cambio_direccion_usa_coordenadas_nuevas_publicadas(self):
        self.existente(direccion="Anterior 100", latitud=-31, longitud=-61)
        self.adaptador.extraer_detalles.return_value = DetallesPropiedad(
            latitud=0, longitud=0, ubicacion_aproximada=True, radio_ubicacion_m=300,
        )
        importar_fuente(self.adaptador)
        propiedad = Propiedad.objects.get()
        self.assertEqual((propiedad.latitud, propiedad.longitud), (0, 0))
        self.assertEqual(propiedad.radio_ubicacion_m, 300)
        self.geocoding.assert_not_called()

    def test_par_parcial_de_fuente_no_se_mezcla_con_el_par_anterior(self):
        self.existente(latitud=-31, longitud=-61, ubicacion_aproximada=True, radio_ubicacion_m=400)
        self.adaptador.extraer_detalles.return_value = DetallesPropiedad(latitud=-32)
        importar_fuente(self.adaptador)
        propiedad = Propiedad.objects.get()
        self.assertEqual((propiedad.latitud, propiedad.longitud), (-31, -61))

    def test_invalidar_ubicacion_tambien_limpia_precision_anterior(self):
        self.existente(direccion="Anterior 100", latitud=-31, longitud=-61,
                       ubicacion_aproximada=True, radio_ubicacion_m=400)
        importar_fuente(self.adaptador)
        propiedad = Propiedad.objects.get()
        self.assertIsNone(propiedad.ubicacion_aproximada)
        self.assertIsNone(propiedad.radio_ubicacion_m)

    @patch("propiedades.management.commands.importar_propiedades.FUENTES")
    def test_ambos_comandos_usan_el_mismo_flujo(self, fuentes):
        fuentes.__getitem__.return_value.return_value = self.adaptador
        fuentes.__iter__.return_value = iter(["brega"])
        call_command("importar_brega", verbosity=0)
        call_command("importar_propiedades", "brega", verbosity=0)
        self.assertEqual(Propiedad.objects.count(), 1)


class AdaptadorBregaTests(SimpleTestCase):
    def test_extrae_circulo_de_la_ficha_y_su_radio(self):
        from propiedades.scraping.brega import leer_detalles
        detalle = leer_detalles('''
          <div id="prop-desc">Casa</div>
          <section id="ficha_mapa"><script>
            var map = L.map("openstreetmap_box").setView([-30, -60], 15);
            L.circle([-31.2684177, -61.4354131], 400, {color: 'red'}).addTo(map);
          </script></section>
        ''')
        self.assertEqual((detalle.latitud, detalle.longitud), (-31.2684177, -61.4354131))
        self.assertTrue(detalle.ubicacion_aproximada)
        self.assertEqual(detalle.radio_ubicacion_m, 400)

    def test_no_usa_zoom_del_mapa_ni_coordenadas_del_footer(self):
        from propiedades.scraping.brega import leer_detalles
        detalle = leer_detalles('''
          <div id="prop-desc">Casa</div>
          <section id="ficha_mapa"><script>L.map('map').setView([-31,-61],15);</script></section>
          <footer><script>L.circle([-31,-61],400,{});</script></footer>
        ''')
        self.assertIsNone(detalle.latitud)
        self.assertIsNone(detalle.longitud)

    def test_coordenadas_radio_invalidos_o_varios_circulos_se_descartan(self):
        from propiedades.scraping.brega import leer_detalles
        for codigo in (
            'L.circle([95,-61],400,{});',
            'L.circle([-31,-181],400,{});',
            'L.circle([-31,-61],-1,{});',
            'L.circle([-31,-61],1e999,{});',
            'L.circle([-31,-61],400,{});L.circle([-32,-62],400,{});',
        ):
            with self.subTest(codigo=codigo), self.assertLogs('propiedades.scraping.brega', level='WARNING'):
                detalle = leer_detalles(
                    '<div id="prop-desc">Casa</div><section id="ficha_mapa"><script>'
                    + codigo + '</script></section>'
                )
                self.assertIsNone(detalle.latitud)

    def test_ficha_completa_limpia_html_y_no_confunde_zona_con_ciudad(self):
        from propiedades.scraping.brega import leer_detalles
        detalle = leer_detalles('''
          <meta property="og:title" content="Casa con cochera">
          <div class="ficha_detalle_item"><b>Ubicación</b><br>Barrio 30 de Octubre</div>
          <div id="prop-desc">&lt;p&gt;Casa con &lt;b&gt;cochera&lt;/b&gt; y patio.&lt;/p&gt;</div>
          <ul id="lista_informacion_basica" class="ficha_ul">
            <li>Ambientes : 4</li><li>Dormitorios : 2</li><li>Baños : 1</li>
            <li>Cocheras : 1</li>
          </ul>
          <ul class="ficha_ul"><li>Parrilla</li><li>Parrilla</li></ul>
        ''')
        self.assertEqual(detalle.titulo, "Casa con cochera")
        self.assertEqual(detalle.descripcion, "Casa con cochera y patio.")
        self.assertEqual((detalle.dormitorios, detalle.ambientes, detalle.banos), (2, 4, 1))
        self.assertIn("Cocheras : 1", detalle.caracteristicas)
        self.assertEqual(detalle.caracteristicas.count("Parrilla"), 1)
        self.assertEqual(detalle.zona, "Barrio 30 de Octubre")
        self.assertIsNone(detalle.ciudad)

    def test_cantidad_invalida_y_estructura_desconocida_son_errores(self):
        from propiedades.scraping.brega import leer_detalles
        with self.assertRaises(ValueError):
            leer_detalles('<div class="ficha_detalle_item"><b>Dormitorios</b><br>muchos</div>')
        with self.assertRaises(ValueError):
            leer_detalles('<html><p>Servicio no disponible</p></html>')

    def test_datos_faltantes_no_se_inventan_y_cero_es_valido(self):
        from propiedades.scraping.brega import leer_detalles
        detalle = leer_detalles('<div class="ficha_detalle_item"><b>Dormitorios</b><br>0</div>')
        self.assertEqual(detalle.dormitorios, 0)
        self.assertIsNone(detalle.banos)
        self.assertIsNone(detalle.descripcion)
        self.assertIsNone(detalle.ciudad)

    @patch("propiedades.scraping.brega.extraer_todas_las_paginas")
    def test_traduce_sin_inventar_ciudad(self, extraer):
        extraer.return_value = [{
            "identificador_fuente": "1", "url_original": "https://ejemplo.test/1",
            "direccion": None, "tipo": "Casa", "precio": Decimal("100"),
            "moneda": "USD", "en_venta": True, "en_alquiler": False,
        }]
        dato, = AdaptadorBrega().extraer("venta")
        self.assertIsInstance(dato, PublicacionNormalizada)
        self.assertEqual(dato.direccion, "")
        self.assertIsNone(dato.ciudad)
        self.assertEqual(dato.precio, Decimal("100"))

    @patch("propiedades.scraping.brega.requests.get")
    def test_html_conocido_conserva_extraccion_y_normalizacion(self, get):
        get.return_value.text = """
        <li prop-id="12">
          <a href="/propiedad/12">Ver</a>
          <div class="prop-desc-dir">Italia 100</div>
          <div class="prop-desc-tipo-ub">Casa en venta</div>
          <div class="prop-valor-nro">USD 120.000</div>
        </li>
        """
        from propiedades.scraping.brega import extraer_pagina
        dato, = extraer_pagina(1, "venta")
        self.assertEqual(dato["identificador_fuente"], "12")
        self.assertEqual(dato["precio"], Decimal("120000"))
        self.assertTrue(dato["en_venta"])
        self.assertEqual(dato["url_original"], "https://www.bregainmobiliaria.ar/propiedad/12")
