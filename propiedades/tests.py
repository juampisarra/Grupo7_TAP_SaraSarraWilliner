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

    def test_punto_exacto_de_fuente_conserva_false_y_no_geocodifica(self):
        self.adaptador.extraer_detalles.return_value = DetallesPropiedad(
            latitud=-31.250540799413834,
            longitud=-61.49395149727678,
            ubicacion_aproximada=False,
            radio_ubicacion_m=None,
        )

        importar_fuente(self.adaptador)

        propiedad = Propiedad.objects.get()
        self.assertEqual(
            (propiedad.latitud, propiedad.longitud),
            (-31.250540799413834, -61.49395149727678),
        )
        self.assertIs(propiedad.ubicacion_aproximada, False)
        self.assertIsNone(propiedad.radio_ubicacion_m)
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


class ComandoGeneralIngestaTests(SimpleTestCase):
    def setUp(self):
        self.avantix = SimpleNamespace(nombre="Avantix")
        self.brega = SimpleNamespace(nombre="Brega")
        self.crear_avantix = Mock(return_value=self.avantix)
        self.crear_brega = Mock(return_value=self.brega)
        self.fuentes = {
            "avantix": self.crear_avantix,
            "brega": self.crear_brega,
        }

    def test_sin_argumento_importa_ambas_fuentes_en_orden(self):
        from propiedades.ingesta import ResumenIngesta

        with (
            patch(
                "propiedades.management.commands.importar_propiedades.FUENTES",
                self.fuentes,
            ),
            patch(
                "propiedades.management.commands.importar_propiedades.importar_fuente",
                return_value=ResumenIngesta(),
            ) as importar,
        ):
            call_command("importar_propiedades", verbosity=0)

        self.crear_avantix.assert_called_once_with()
        self.crear_brega.assert_called_once_with()
        self.assertEqual(
            [llamada.args[0] for llamada in importar.call_args_list],
            [self.avantix, self.brega],
        )

    def test_argumento_avantix_no_importa_brega(self):
        from propiedades.ingesta import ResumenIngesta

        with (
            patch(
                "propiedades.management.commands.importar_propiedades.FUENTES",
                self.fuentes,
            ),
            patch(
                "propiedades.management.commands.importar_propiedades.importar_fuente",
                return_value=ResumenIngesta(),
            ) as importar,
        ):
            call_command("importar_propiedades", "avantix", verbosity=0)

        self.crear_avantix.assert_called_once_with()
        self.crear_brega.assert_not_called()
        self.assertIs(importar.call_args.args[0], self.avantix)


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

class AdaptadorAvantixTests(SimpleTestCase):
    def test_esta_registrado_como_fuente(self):
        from propiedades.scraping.avantix import AdaptadorAvantix
        from propiedades.scraping.fuentes import FUENTES

        self.assertIs(FUENTES["avantix"], AdaptadorAvantix)

    def test_ficha_extrae_campos_y_no_interpreta_un_script_del_mapa(self):
        from propiedades.scraping.avantix import leer_detalles

        detalle = leer_detalles('''
          <meta property="og:title" content="Departamento céntrico">
          <div class="ficha_detalle_item"><b>Ubicación</b><br>Barrio San Martín</div>
          <div id="prop-desc">&lt;p&gt;Departamento con &lt;b&gt;balcón&lt;/b&gt;.&lt;/p&gt;</div>
          <ul id="lista_informacion_basica" class="ficha_ul">
            <li>Ambientes : 3</li>
            <li>Dormitorios : 2</li>
            <li>Baños : 1</li>
          </ul>
          <ul class="ficha_ul"><li>Patio</li><li>Patio</li></ul>
          <div id="ficha_mapa"><script>
            new google.maps.Marker({position: {lat: -31.25, lng: -61.49}});
          </script></div>
        ''')

        self.assertEqual(detalle.titulo, "Departamento céntrico")
        self.assertEqual(detalle.descripcion, "Departamento con balcón .")
        self.assertEqual((detalle.dormitorios, detalle.ambientes, detalle.banos), (2, 3, 1))
        self.assertEqual(detalle.zona, "Barrio San Martín")
        self.assertEqual(detalle.caracteristicas.count("Patio"), 1)
        self.assertIsNone(detalle.latitud)
        self.assertIsNone(detalle.longitud)
        self.assertIsNone(detalle.ubicacion_aproximada)
        self.assertIsNone(detalle.radio_ubicacion_m)

    def test_punto_google_maps_se_trata_como_ubicacion_exacta(self):
        from propiedades.scraping.avantix import leer_detalles

        detalle = leer_detalles('''
          <div id="prop-desc">Departamento</div>
          <div id="ficha_mapa">
            <iframe src="https://maps.google.com/maps?q=-31.250540799413834%2C-61.49395149727678&amp;output=embed"></iframe>
            <iframe src="https://www.google.com/maps/embed/v1/place?key=demo&amp;q=-31.250540799413834%2C-61.49395149727678"></iframe>
          </div>
        ''')

        self.assertEqual(
            (detalle.latitud, detalle.longitud),
            (-31.250540799413834, -61.49395149727678),
        )
        self.assertIs(detalle.ubicacion_aproximada, False)
        self.assertIsNone(detalle.radio_ubicacion_m)

    def test_punto_cero_es_valido_y_mapa_fuera_de_la_ficha_se_ignora(self):
        from propiedades.scraping.avantix import leer_detalles

        detalle = leer_detalles('''
          <iframe src="https://www.google.com/maps/embed/v1/place?q=-31.25%2C-61.49"></iframe>
          <div id="prop-desc">Departamento</div>
          <div id="ficha_mapa">
            <iframe src="https://ejemplo.test/maps?q=-30%2C-60"></iframe>
            <iframe src="https://maps.google.com/maps?q=Maipu+239"></iframe>
            <iframe src="https://www.google.com/maps/embed/v1/place?q=0%2C0"></iframe>
          </div>
        ''')

        self.assertEqual((detalle.latitud, detalle.longitud), (0, 0))
        self.assertIs(detalle.ubicacion_aproximada, False)

    def test_coordenadas_invalidas_o_puntos_distintos_se_descartan(self):
        from propiedades.scraping.avantix import leer_detalles

        casos = (
            '''
              <div id="prop-desc">Departamento</div>
              <div id="ficha_mapa">
                <iframe src="http://[host-invalido"></iframe>
              </div>
            ''',
            '''
              <div id="prop-desc">Departamento</div>
              <div id="ficha_mapa">
                <iframe src="https://www.google.com/maps/embed/v1/place?q=91%2C-61"></iframe>
              </div>
            ''',
            '''
              <div id="prop-desc">Departamento</div>
              <div id="ficha_mapa">
                <iframe src="https://www.google.com/maps/embed/v1/place?q=-31.25%2C-61.49"></iframe>
                <iframe src="https://www.google.com/maps/embed/v1/place?q=-32.25%2C-62.49"></iframe>
              </div>
            ''',
        )

        for html in casos:
            with self.subTest(html=html), self.assertLogs(
                "propiedades.scraping.avantix",
                level="WARNING",
            ):
                detalle = leer_detalles(html)

            self.assertIsNone(detalle.latitud)
            self.assertIsNone(detalle.longitud)
            self.assertIsNone(detalle.ubicacion_aproximada)
            self.assertIsNone(detalle.radio_ubicacion_m)

    @patch("propiedades.scraping.avantix.requests.get")
    def test_extraer_detalles_descarga_una_ficha(self, get):
        get.return_value.text = '<div id="prop-desc">Departamento</div>'

        from propiedades.scraping.avantix import CABECERAS, extraer_detalles

        detalle = extraer_detalles("https://www.avantix.ar/p/11827974")

        get.assert_called_once_with(
            "https://www.avantix.ar/p/11827974",
            headers=CABECERAS,
            timeout=15,
        )
        get.return_value.raise_for_status.assert_called_once_with()
        self.assertEqual(detalle.descripcion, "Departamento")

    @patch("propiedades.scraping.avantix.extraer_detalles")
    def test_adaptador_delega_la_lectura_de_la_ficha(self, extraer):
        from propiedades.scraping.avantix import AdaptadorAvantix

        esperado = DetallesPropiedad(titulo="Departamento")
        extraer.return_value = esperado

        resultado = AdaptadorAvantix().extraer_detalles(
            "https://www.avantix.ar/p/11827974"
        )

        extraer.assert_called_once_with("https://www.avantix.ar/p/11827974")
        self.assertIs(resultado, esperado)

    @patch("propiedades.scraping.avantix.extraer_todas_las_paginas")
    def test_traduce_listado_al_contrato_comun(self, extraer):
        extraer.return_value = [{
            "identificador_fuente": "11827974",
            "url_original": "https://www.avantix.ar/p/11827974",
            "direccion": None,
            "tipo": "Departamento",
            "precio": Decimal("54000"),
            "moneda": "USD",
            "en_venta": True,
            "en_alquiler": True,
        }]

        from propiedades.scraping.avantix import AdaptadorAvantix

        dato, = AdaptadorAvantix().extraer("venta")

        extraer.assert_called_once_with("venta")
        self.assertIsInstance(dato, PublicacionNormalizada)
        self.assertEqual(dato.identificador_fuente, "11827974")
        self.assertEqual(dato.url_original, "https://www.avantix.ar/p/11827974")
        self.assertEqual(dato.direccion, "")
        self.assertEqual(dato.tipo, "Departamento")
        self.assertEqual(dato.precio, Decimal("54000"))
        self.assertEqual(dato.moneda, "USD")
        self.assertTrue(dato.en_venta)
        self.assertTrue(dato.en_alquiler)

    @patch("propiedades.scraping.avantix.time.sleep")
    @patch("propiedades.scraping.avantix.extraer_pagina")
    def test_limite_de_paginas_evitar_recorrido_infinito(
        self,
        extraer_pagina,
        sleep,
    ):
        extraer_pagina.side_effect = [
            [{"identificador_fuente": "1"}],
            [{"identificador_fuente": "2"}],
        ]

        from propiedades.scraping.avantix import extraer_todas_las_paginas

        with self.assertRaisesRegex(RuntimeError, "límite de 2 páginas"):
            extraer_todas_las_paginas("venta", max_paginas=2)

        self.assertEqual(extraer_pagina.call_count, 2)
        self.assertEqual(sleep.call_count, 2)

    @patch("propiedades.scraping.avantix.time.sleep")
    @patch("propiedades.scraping.avantix.extraer_pagina")
    def test_recorre_paginas_y_evita_repetidos(
        self,
        extraer_pagina,
        sleep,
    ):
        propiedad_1 = {"identificador_fuente": "1"}
        propiedad_2 = {"identificador_fuente": "2"}
        propiedad_3 = {"identificador_fuente": "3"}

        extraer_pagina.side_effect = [
            [propiedad_1, propiedad_2],
            [propiedad_2, propiedad_3],
            [],
        ]

        from propiedades.scraping.avantix import extraer_todas_las_paginas

        resultado = extraer_todas_las_paginas("venta")

        self.assertEqual(
            [propiedad["identificador_fuente"] for propiedad in resultado],
            ["1", "2", "3"],
        )
        self.assertEqual(extraer_pagina.call_count, 3)
        extraer_pagina.assert_any_call(1, "venta")
        extraer_pagina.assert_any_call(2, "venta")
        extraer_pagina.assert_any_call(3, "venta")
        self.assertEqual(sleep.call_count, 2)

    @patch("propiedades.scraping.avantix.requests.get")
    def test_extrae_y_normaliza_una_pagina(self, get):
        get.return_value.text = """
        <li prop-id="11827974">
          <a href="/p/11827974-Departamento-en-Venta-Alquiler">
            Ver detalles
          </a>
          <div class="prop-desc-dir">Ituzaingó 660</div>
          <div class="prop-desc-tipo-ub">
            Departamento en Venta / Alquiler en Barrio San Martin, Rafaela
          </div>
          <div class="prop-valor-nro">
            USD54.000
            <div class="codref">AAP11827974</div>
          </div>
        </li>
        """

        from propiedades.scraping.avantix import extraer_pagina

        dato, = extraer_pagina(1, "venta")

        self.assertEqual(dato["identificador_fuente"], "11827974")
        self.assertEqual(dato["direccion"], "Ituzaingó 660")
        self.assertEqual(dato["tipo"], "Departamento")
        self.assertTrue(dato["en_venta"])
        self.assertTrue(dato["en_alquiler"])
        self.assertEqual(dato["precio"], Decimal("54000"))
        self.assertEqual(dato["moneda"], "USD")
        self.assertEqual(
            dato["url_original"],
            "https://www.avantix.ar/p/11827974-Departamento-en-Venta-Alquiler",
        )
