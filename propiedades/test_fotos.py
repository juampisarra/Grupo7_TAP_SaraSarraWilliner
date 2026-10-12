from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase, override_settings

from propiedades.busqueda.indice import documento
from propiedades.fotos import normalizar_fotos, validar_fotos
from propiedades.ingesta import importar_fuente
from propiedades.models import Propiedad
from propiedades.scraping.brega import leer_detalles as leer_brega
from propiedades.scraping.avantix import leer_detalles as leer_avantix
from propiedades.scraping.gaggiotti import leer_detalles as leer_gaggiotti
from propiedades.scraping.contratos import DetallesPropiedad, PublicacionNormalizada


FOTO_A = "https://static.tokkobroker.com/pictures/a.jpg"
FOTO_B = "https://static.tokkobroker.com/w_pics/b.jpg"


class NormalizacionFotosTests(SimpleTestCase):
    def test_urls_relativas_protocolo_y_deduplicacion_conservan_orden_query(self):
        fotos = normalizar_fotos([
            " /imagenes/a.jpg#vista ", "https://ejemplo.test/imagenes/a.jpg",
            "//static.tokkobroker.com/pictures/b.jpg?width=300&quality=80",
        ], url_base="https://ejemplo.test")
        self.assertEqual(fotos, ["https://ejemplo.test/imagenes/a.jpg", "https://static.tokkobroker.com/pictures/b.jpg?width=300&quality=80"])

    def test_rechaza_esquemas_credenciales_red_local_y_valores_invalidos(self):
        for url in (None, 42, {}, "", "javascript:alert(1)", "data:image/png;base64,a",
                    "http://ejemplo.test/foto.jpg", "https://user:clave@ejemplo.test/a.jpg",
                    "https://127.0.0.1/a.jpg", "https://[::1]/a.jpg", "https://10.0.0.2/a.jpg",
                    "https://localhost/a.jpg", "https://pc.local/a.jpg", "https://a.localhost/a.jpg",
                    "https://ejemplo.test/a\nb.jpg", "https://ejemplo.test/a b.jpg", "https://ejemplo.test\\a.jpg"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                normalizar_fotos([url])
        for valor in (None, {}, "https://ejemplo.test/a.jpg"):
            with self.assertRaises(ValueError):
                normalizar_fotos(valor)

    def test_validador_del_modelo_exige_lista_normalizada_y_sin_duplicados(self):
        validar_fotos([])
        validar_fotos([FOTO_A])
        for fotos in ([FOTO_A, FOTO_A], [FOTO_A + "#vista"], {"foto": FOTO_A}, ["/relativa.jpg"]):
            with self.assertRaises(ValidationError):
                validar_fotos(fotos)


class FotosTokkoTests(SimpleTestCase):
    def ficha(self, galeria):
        return '<div id="prop-desc">Casa con patio</div>' + galeria

    def test_ambas_fuentes_extraen_solo_galeria_no_logo_iconos_og_ni_recomendados(self):
        html = self.ficha(f'''
            <img src="https://ejemplo.test/logo.png">
            <meta property="og:image" content="https://ejemplo.test/og.jpg">
            <div id="ficha_slider"><ul class="slides">
                <li><img class="zoomImg" src="{FOTO_B}"></li>
                <li><img class="zoomImg" src="{FOTO_A}"></li>
                <li><img class="zoomImg" src="{FOTO_B}"></li>
            </ul></div>
            <aside><img class="zoomImg" src="https://ejemplo.test/otra.jpg"></aside>
        ''')
        for leer in (leer_brega, leer_avantix):
            detalle = leer(html)
            self.assertEqual(detalle.fotos, [FOTO_B, FOTO_A])
            self.assertEqual(detalle.descripcion, "Casa con patio")

    def test_resuelve_relativas_y_lazy_load_con_base_de_cada_fuente(self):
        html = self.ficha('''<div id="ficha_slider"><ul class="slides">
            <li><img class="zoomImg" src="data:image/png;base64,x" data-src="/fotos/a.jpg"></li>
        </ul></div>''')
        self.assertEqual(leer_brega(html).fotos, ["https://www.bregainmobiliaria.ar/fotos/a.jpg"])
        self.assertEqual(leer_avantix(html).fotos, ["https://www.avantix.ar/fotos/a.jpg"])

    def test_vacia_confirmada_difiere_de_ausente_o_estructura_desconocida(self):
        self.assertEqual(leer_brega(self.ficha('<div id="ficha_slider"><ul class="slides"></ul></div>')).fotos, [])
        for html in ("", '<div id="ficha_slider"></div>',
                     '<div id="ficha_slider"><ul class="slides"><div>Nuevo formato</div></ul></div>',
                     '<div id="ficha_slider"><ul class="slides"><li><img src="/a.jpg"></li></ul></div>',
                     '<div id="ficha_slider"><ul class="slides"><li><img class="zoomImg"></li></ul></div>'):
            self.assertIsNone(leer_brega(self.ficha(html)).fotos)

    def test_url_invalida_no_entrega_galeria_parcial_ni_pierde_detalles(self):
        html = self.ficha(f'''<div id="ficha_slider"><ul class="slides">
            <li><img class="zoomImg" src="{FOTO_A}"></li>
            <li><img class="zoomImg" src="javascript:alert(1)"></li>
        </ul></div>''')
        with self.assertLogs("propiedades.scraping.tokko", level="WARNING"):
            detalle = leer_brega(html)
        self.assertIsNone(detalle.fotos)
        self.assertEqual(detalle.descripcion, "Casa con patio")


class FotosGaggiottiTests(SimpleTestCase):
    def foto(self, url, orden=0, portada=False):
        return {"image": url, "order": orden, "isFrontCover": portada,
                "original": "https://ejemplo.test/original.jpg", "thumb": "https://ejemplo.test/thumb.jpg"}

    def test_portada_explicita_orden_y_deduplicacion_sin_usar_originales(self):
        dato = {"id": 1, "photos": [self.foto(FOTO_A, 9), self.foto(FOTO_B, 10, True),
                self.foto("https://ejemplo.test/c.jpg", 2), self.foto(FOTO_A, 11)]}
        self.assertEqual(leer_gaggiotti(dato).fotos, [FOTO_B, "https://ejemplo.test/c.jpg", FOTO_A])

    def test_sin_portada_usa_orden_y_desempata_con_posicion_original(self):
        dato = {"id": 1, "photos": [self.foto(FOTO_B, 1), self.foto(FOTO_A, 1)]}
        self.assertEqual(leer_gaggiotti(dato).fotos, [FOTO_B, FOTO_A])

    def test_vacia_confirmada_y_ausencia(self):
        self.assertEqual(leer_gaggiotti({"id": 1, "photos": []}).fotos, [])
        self.assertIsNone(leer_gaggiotti({"id": 1}).fotos)
        self.assertIsNone(leer_gaggiotti({"id": 1, "photos": None}).fotos)

    def test_formato_invalido_conserva_galeria_y_no_impide_extraer_texto(self):
        for fotos in ({}, [None], [self.foto("http://ejemplo.test/a.jpg")],
                      [self.foto(FOTO_A, -1)], [self.foto(FOTO_A, True)],
                      [self.foto(FOTO_A, portada=True), self.foto(FOTO_B, portada=True)],
                      [{"image": FOTO_A}], [self.foto(None)]):
            with self.subTest(fotos=fotos), self.assertLogs("propiedades.scraping.gaggiotti", level="WARNING"):
                detalle = leer_gaggiotti({"id": 1, "description": "Texto útil", "photos": fotos})
            self.assertIsNone(detalle.fotos)
            self.assertEqual(detalle.descripcion, "Texto útil")


@override_settings(SECURE_SSL_REDIRECT=False, STORAGES={"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class PersistenciaFotosTests(TestCase):
    def setUp(self):
        pausa = patch("propiedades.ingesta.time.sleep")
        pausa.start()
        self.addCleanup(pausa.stop)
        self.adaptador = SimpleNamespace(
            nombre="Prueba", operaciones=("venta",),
            extraer=Mock(return_value=[PublicacionNormalizada("1", "https://ejemplo.test/1")]),
            extraer_detalles=Mock(return_value=DetallesPropiedad(fotos=[FOTO_A, FOTO_B])),
        )

    def test_guarda_reemplaza_orden_y_repite_sin_duplicados(self):
        importar_fuente(self.adaptador)
        p = Propiedad.objects.get()
        self.assertEqual(p.fotos, [FOTO_A, FOTO_B])
        self.assertEqual(p.foto_portada, FOTO_A)
        p.full_clean()
        self.adaptador.extraer_detalles.return_value = DetallesPropiedad(fotos=[FOTO_B])
        importar_fuente(self.adaptador)
        importar_fuente(self.adaptador)
        p.refresh_from_db()
        self.assertEqual(p.fotos, [FOTO_B])
        self.assertEqual(Propiedad.objects.count(), 1)

    def test_detalle_fallido_o_fotos_desconocidas_conservan_anteriores(self):
        importar_fuente(self.adaptador)
        self.adaptador.extraer_detalles.side_effect = requests.Timeout("Fallo ficha")
        importar_fuente(self.adaptador)
        self.assertEqual(Propiedad.objects.get().fotos, [FOTO_A, FOTO_B])
        self.adaptador.extraer_detalles.side_effect = None
        self.adaptador.extraer_detalles.return_value = DetallesPropiedad(descripcion="Actualizada", fotos=None)
        importar_fuente(self.adaptador)
        p = Propiedad.objects.get()
        self.assertEqual(p.fotos, [FOTO_A, FOTO_B])
        self.assertEqual(p.descripcion, "Actualizada")

    def test_vacia_confirmada_limpia_y_nueva_sin_datos_usa_lista_independiente(self):
        importar_fuente(self.adaptador)
        self.adaptador.extraer_detalles.return_value = DetallesPropiedad(fotos=[])
        importar_fuente(self.adaptador)
        p = Propiedad.objects.get()
        self.assertEqual(p.fotos, [])
        self.assertIsNone(p.foto_portada)
        a, b = Propiedad(), Propiedad()
        a.fotos.append(FOTO_A)
        self.assertEqual(b.fotos, [])

    def test_modelo_rechaza_objetos_json_incluso_vacios_y_urls_invalidas(self):
        importar_fuente(self.adaptador)
        p = Propiedad.objects.get()
        for fotos in ({}, {"url": FOTO_A}, None, ["javascript:alert(1)"], [FOTO_A, FOTO_A]):
            p.fotos = fotos
            with self.subTest(fotos=fotos), self.assertRaises(ValidationError) as error:
                p.full_clean()
            self.assertIn("fotos", error.exception.message_dict)

    def test_retirada_no_borra_fotos_y_reaparicion_actualiza_misma_fila(self):
        importar_fuente(self.adaptador)
        p = Propiedad.objects.get()
        self.adaptador.extraer.return_value = []
        importar_fuente(self.adaptador)
        p.refresh_from_db()
        self.assertFalse(p.en_venta)
        self.assertEqual(p.fotos, [FOTO_A, FOTO_B])
        self.adaptador.extraer.return_value = [PublicacionNormalizada("1", "https://ejemplo.test/1")]
        importar_fuente(self.adaptador)
        self.assertEqual(Propiedad.objects.count(), 1)
        self.assertEqual(Propiedad.objects.get().pk, p.pk)

    @patch("propiedades.views.buscar_ids")
    def test_api_y_html_exponen_portada_sin_consultar_fuentes_ni_indexar_imagenes(self, buscar):
        importar_fuente(self.adaptador)
        p = Propiedad.objects.get()
        buscar.return_value = [(p.pk, 5)]
        with patch("requests.get") as get, patch("requests.post") as post:
            for texto in ("", "casa"):
                datos = self.client.get("/api/propiedades/", {"operacion": "venta", "q": texto, "por_pagina": 1}).json()
                self.assertEqual(datos["resultados"][0]["fotos"], [FOTO_A, FOTO_B])
                self.assertEqual(datos["resultados"][0]["foto_portada"], FOTO_A)
            respuesta = self.client.get("/propiedades/?operacion=venta")
            self.assertContains(respuesta, f'src="{FOTO_A}"')
            self.assertContains(respuesta, 'loading="lazy"')
            self.assertContains(respuesta, 'data-foto-reemplazo hidden')
            get.assert_not_called()
            post.assert_not_called()
        self.assertNotIn("fotos", documento(p))
        self.assertNotIn("foto_portada", documento(p))

    def test_api_sin_fotos_usa_lista_vacia_y_portada_null(self):
        self.adaptador.extraer_detalles.return_value = DetallesPropiedad()
        importar_fuente(self.adaptador)
        datos = self.client.get("/api/propiedades/?operacion=venta").json()["resultados"][0]
        self.assertEqual(datos["fotos"], [])
        self.assertIsNone(datos["foto_portada"])
        self.assertContains(self.client.get("/propiedades/?operacion=venta"), "Sin fotos disponibles.")
