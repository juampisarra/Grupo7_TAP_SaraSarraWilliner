from decimal import Decimal
from html.parser import HTMLParser
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from .busqueda.cliente import BusquedaNoDisponible
from .models import Propiedad


@override_settings(SECURE_SSL_REDIRECT=False)
class ConsultaPropiedadesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.casa = Propiedad.objects.create(
            fuente="Brega", identificador_fuente="1", tipo="Casa", dormitorios=2,
            en_venta=True, precio_venta=Decimal("100000.25"), moneda_venta="USD",
            en_alquiler=True, precio_alquiler=Decimal("500000"), moneda_alquiler="ARS",
            latitud=0, longitud=0, ubicacion_aproximada=None,
        )
        cls.depto = Propiedad.objects.create(
            fuente="Avantix", identificador_fuente="2", tipo="Departamento", dormitorios=0,
            en_alquiler=True, precio_alquiler=Decimal("0"), moneda_alquiler="ARS",
            en_venta=True, precio_venta=Decimal("500000"), moneda_venta="ARS",
        )
        cls.otra = Propiedad.objects.create(
            fuente="Gaggiotti", identificador_fuente="3", tipo="Casa", dormitorios=2,
            en_venta=True, precio_venta=Decimal("150000"), moneda_venta="USD",
            en_alquiler=True, precio_alquiler=Decimal("600"), moneda_alquiler="USD",
        )
        cls.desconocida = Propiedad.objects.create(
            fuente="Gaggiotti", identificador_fuente="4", tipo="Casa", en_alquiler=True,
        )

    def consultar(self, **parametros):
        respuesta = self.client.get("/api/propiedades/", parametros)
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        return respuesta.json()

    def ids(self, datos):
        return [p["id"] for p in datos["resultados"]]

    def test_combina_tipo_dormitorios_y_precio_inclusivo_sin_mezclar_operaciones(self):
        datos = self.consultar(operacion="venta", tipo=" casa ", dormitorios="2", moneda="usd",
                               precio_min="100000.25", precio_max="100000.25")
        self.assertEqual(self.ids(datos), [self.casa.pk])
        self.assertEqual(datos["resultados"][0]["venta"]["precio"], "100000.25")
        self.assertEqual(datos["resultados"][0]["alquiler"]["precio"], "500000.00")
        self.assertEqual(self.ids(self.consultar(operacion="alquiler", moneda="USD", precio_max="600")), [self.otra.pk])

    def test_cero_es_valido_y_los_desconocidos_no_cumplen_un_rango(self):
        datos = self.consultar(operacion="alquiler", moneda="ARS", dormitorios="0", precio_min="0", precio_max="0")
        self.assertEqual(self.ids(datos), [self.depto.pk])
        self.assertEqual(datos["resultados"][0]["alquiler"]["precio"], "0.00")
        self.assertIsNone(datos["resultados"][0]["latitud"])
        self.assertEqual(self.consultar(dormitorios="2")["total"], 2)

    def test_tipo_es_completo_y_no_coincidencia_es_lista_vacia(self):
        self.assertEqual(self.consultar(tipo="Casa")["total"], 3)
        self.assertEqual(self.consultar(tipo="Cas")["total"], 0)
        self.assertEqual(self.consultar(tipo="Inexistente")["resultados"], [])

    @patch("propiedades.views.buscar_ids")
    def test_entradas_invalidas_son_400_antes_de_elasticsearch(self, buscar):
        casos = [
            {"operacion": "comprar"}, {"operacion": ""}, {"tipo": "x" * 51},
            {"dormitorios": "-1"}, {"dormitorios": "1.5"}, {"dormitorios": "32768"},
            {"moneda": "EUR"}, {"moneda": "ARS"}, {"precio_min": "0"},
            {"operacion": "venta", "precio_min": "1"},
            {"operacion": "venta", "moneda": "USD", "precio_min": "2", "precio_max": "1"},
            {"pagina": "0"}, {"pagina": "-1"}, {"pagina": "1.5"}, {"pagina": ""},
            {"por_pagina": "0"}, {"por_pagina": "101"}, {"por_pagina": "todos"},
            {"q": "x" * 301},
        ]
        for valor in ("NaN", "Infinity", "-1", "1e3", "1,50", "1.001", "10000000000000", "9" * 5000):
            casos.append({"operacion": "venta", "moneda": "USD", "precio_min": valor})
        for url in ("/api/propiedades/", "/propiedades/"):
            for caso in casos:
                with self.subTest(url=url, caso=caso):
                    respuesta = self.client.get(url, caso)
                    self.assertEqual(respuesta.status_code, 400)
                    self.assertIn("error", respuesta.json())
        buscar.assert_not_called()

    def test_rechaza_parametros_conocidos_repetidos(self):
        for campo in ("operacion", "tipo", "dormitorios", "pagina", "por_pagina", "q", "radio_m"):
            with self.subTest(campo=campo):
                self.assertEqual(self.client.get(f"/api/propiedades/?{campo}=1&{campo}=2").status_code, 400)

    @patch("propiedades.views.buscar_ids")
    def test_ausentes_y_opcionales_vacios_conservan_alquiler_predeterminado(self, buscar):
        datos = self.consultar(tipo="", dormitorios="", moneda="", precio_min="", precio_max="", q=" ")
        self.assertEqual(datos["operacion"], "alquiler")
        self.assertEqual(datos["total"], 4)
        self.assertEqual(datos["orden"], "actualizacion")
        buscar.assert_not_called()

    def test_paginacion_determinista_sin_repetidos_y_enlaces_conservan_filtros(self):
        Propiedad.objects.update(actualizada_en=timezone.now())
        primera = self.consultar(tipo="Casa", por_pagina="2")
        self.assertEqual(self.ids(primera), [self.desconocida.pk, self.otra.pk])
        self.assertEqual((primera["total"], primera["total_paginas"], primera["anterior"]), (3, 2, None))
        link = urlsplit(primera["siguiente"])
        self.assertEqual(link.path, "/api/propiedades/")
        self.assertEqual(parse_qs(link.query), {"tipo": ["Casa"], "por_pagina": ["2"], "pagina": ["2"]})
        segunda = self.client.get(primera["siguiente"]).json()
        self.assertEqual(self.ids(segunda), [self.casa.pk])
        self.assertIsNone(segunda["siguiente"])
        self.assertEqual(len(set(self.ids(primera) + self.ids(segunda))), 3)

    def test_pagina_inexistente_404_y_primera_vacia_200(self):
        for url in ("/propiedades/", "/api/propiedades/"):
            self.assertEqual(self.client.get(url, {"pagina": "99"}).status_code, 404)
            self.assertEqual(self.client.get(url, {"tipo": "Nada", "pagina": "2"}).status_code, 404)
        datos = self.consultar(tipo="Nada")
        self.assertEqual((datos["total"], datos["total_paginas"], datos["pagina"]), (0, 1, 1))
        self.assertIsNone(datos["siguiente"])
        self.assertIsNone(datos["anterior"])

    def test_limite_predeterminado_20_y_maximo_100(self):
        Propiedad.objects.bulk_create([
            Propiedad(fuente="Prueba", identificador_fuente=str(i), en_alquiler=True)
            for i in range(21)
        ])
        datos = self.consultar()
        self.assertEqual((datos["total"], datos["por_pagina"], len(datos["resultados"])), (25, 20, 20))
        self.assertEqual(len(self.client.get(datos["siguiente"]).json()["resultados"]), 5)
        self.assertEqual(len(self.consultar(por_pagina="100")["resultados"]), 25)

    @patch("propiedades.views.buscar_ids")
    def test_filtra_antes_de_paginar_relevancia_y_descarta_ids_ausentes(self, buscar):
        buscar.return_value = [(self.depto.pk, 10), (999999, 9), (self.otra.pk, 8), (self.casa.pk, 7)]
        datos = self.consultar(q="cochera", tipo="Casa", dormitorios="2", por_pagina="1")
        self.assertEqual(self.ids(datos), [self.otra.pk])
        self.assertEqual(datos["total"], 2)
        self.assertEqual(datos["resultados"][0]["relevancia"], 8)
        siguiente = self.client.get(datos["siguiente"]).json()
        self.assertEqual(self.ids(siguiente), [self.casa.pk])
        html = self.client.get("/propiedades/", {"q": "cochera", "tipo": "Casa", "dormitorios": "2", "por_pagina": "1"})
        self.assertEqual(list(html.context["propiedades"]), [self.otra])
        self.assertContains(html, "2 resultados")
        self.assertContains(html, 'name="dormitorios" value="2"')
        self.assertNotContains(html, 'name="pagina"')

    @patch("propiedades.views.buscar_ids", side_effect=BusquedaNoDisponible("Búsqueda no disponible"))
    def test_fallo_textual_503_en_ambos_formatos(self, buscar):
        for url in ("/propiedades/", "/api/propiedades/"):
            respuesta = self.client.get(url, {"q": "casa"})
            self.assertEqual(respuesta.status_code, 503)
            self.assertIn("error", respuesta.json())

    @patch("propiedades.views.buscar_ids", return_value=[])
    def test_texto_sin_resultados_no_hace_fallback(self, buscar):
        self.assertEqual(self.consultar(q="zzzz")["total"], 0)

    def test_serializacion_conserva_nulos_cero_y_procedencia(self):
        datos = self.consultar(tipo="Casa", dormitorios="2", operacion="venta", moneda="USD", precio_max="100001")
        p = datos["resultados"][0]
        self.assertEqual((p["latitud"], p["longitud"]), (0, 0))
        self.assertIsNone(p["ubicacion_aproximada"])
        self.assertIsNone(p["radio_ubicacion_m"])
        self.assertEqual(p["fuente"], "Brega")
        self.assertIsNone(p["relevancia"])
        self.assertIn("actualizada_en", p)
        self.assertNotIn("ubicacion", p)

    def test_metodos_de_solo_lectura(self):
        for url in ("/propiedades/", "/api/propiedades/"):
            self.assertEqual(self.client.head(url).status_code, 200)
            self.assertEqual(self.client.head(url).content, b"")
            for metodo in (self.client.post, self.client.put, self.client.delete):
                respuesta = metodo(url)
                self.assertEqual(respuesta.status_code, 405)
                self.assertEqual(respuesta["Allow"], "GET, HEAD")

    def test_sin_texto_solo_carga_los_objetos_de_la_pagina(self):
        with CaptureQueriesContext(connection) as consultas:
            datos = self.consultar(por_pagina="1")
        self.assertEqual(len(datos["resultados"]), 1)
        self.assertEqual(len(consultas), 2)  # COUNT y SELECT con LIMIT.
        self.assertIn("LIMIT 1", consultas[-1]["sql"])

    @patch("propiedades.views.buscar_ids")
    def test_con_texto_solo_recupera_detalles_de_la_pagina(self, buscar):
        buscar.return_value = [(self.casa.pk, 8), (self.otra.pk, 7)]
        with CaptureQueriesContext(connection) as consultas:
            datos = self.consultar(q="casa", por_pagina="1")
        self.assertEqual(self.ids(datos), [self.casa.pk])
        self.assertEqual(len(consultas), 2)  # IDs filtrados y detalles de una página.
        self.assertNotIn('"descripcion"', consultas[0]["sql"])
        self.assertIn('"descripcion"', consultas[1]["sql"])

    @patch("propiedades.views.buscar_ids")
    def test_ranking_largo_filtra_en_lotes_sin_truncar(self, buscar):
        buscar.return_value = [(i, 10) for i in range(10000, 11100)] + [(self.casa.pk, 2), (self.otra.pk, 1)]
        datos = self.consultar(q="casa", por_pagina="1", pagina="2")
        self.assertEqual(datos["total"], 2)
        self.assertEqual(self.ids(datos), [self.otra.pk])

    def test_geografia_invalida_400_y_sqlite_valida_503(self):
        self.assertEqual(self.client.get("/api/propiedades/?radio_m=-1&latitud=0&longitud=0").status_code, 400)
        if connection.vendor == "sqlite":
            self.assertEqual(self.client.get("/api/propiedades/?radio_m=1&latitud=0&longitud=0").status_code, 503)

    @patch("propiedades.consultas.aplicar_filtros_geograficos")
    @patch("propiedades.views.buscar_ids")
    def test_geografia_y_filtros_se_aplican_antes_de_paginar(self, buscar, geografia):
        # Aislar la coordinación; los cálculos reales se cubren en integración PostGIS.
        geografia.side_effect = lambda qs, params: qs.filter(pk=self.casa.pk)
        buscar.return_value = [(self.otra.pk, 9), (self.casa.pk, 8)]
        datos = self.consultar(q="casa", tipo="Casa", por_pagina="1", radio_m="100", latitud="0", longitud="0", incluir_aproximadas="1")
        self.assertEqual(self.ids(datos), [self.casa.pk])
        self.assertEqual(datos["total"], 1)
        self.assertEqual(len(datos["advertencias"]), 1)

    def test_vista_mapa_devuelve_200_html(self):
        respuesta = self.client.get("/propiedades/mapa/")
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'id="map"')
        self.assertContains(respuesta, "Observatorio Inmobiliario")
        self.assertContains(respuesta, "Alquilar")

    @override_settings(MAPTILER_API_KEY="")
    def test_mapa_sin_clave_no_impide_servir_la_pagina(self):
        respuesta = self.client.get("/propiedades/mapa/")
        self.assertEqual(respuesta.context["map_config"], {"maptilerApiKey": ""})
        self.assertContains(respuesta, 'data-engine="maplibre"')

    @override_settings(MAPTILER_API_KEY='prueba</script><script>alert(1)</script>&')
    def test_clave_de_mapa_se_serializa_sin_inyectar_html(self):
        respuesta = self.client.get("/propiedades/mapa/")
        self.assertContains(respuesta, 'id="map-config" type="application/json"')
        self.assertEqual(respuesta.context["map_config"]["maptilerApiKey"],
                         'prueba</script><script>alert(1)</script>&')
        self.assertNotContains(respuesta, '<script>alert(1)</script>')
        self.assertContains(respuesta, r'\u003C/script\u003E')

    def test_mapa_ofrece_tipos_vigentes_y_nuevos_sin_depender_de_la_pagina(self):
        nave = Propiedad.objects.create(
            fuente="Brega", identificador_fuente="nave", tipo="Nave Industrial", en_venta=True)
        Propiedad.objects.create(
            fuente="Brega", identificador_fuente="retirada", tipo="Campo", en_venta=False, en_alquiler=False)
        Propiedad.objects.create(
            fuente="Brega", identificador_fuente="sin-tipo", tipo="", en_alquiler=True)
        respuesta = self.client.get("/propiedades/mapa/", {"pagina": "99", "por_pagina": "1"})
        self.assertContains(respuesta, 'data-filter-tipo="Nave Industrial"', count=1)
        self.assertContains(respuesta, 'data-filter-tipo="Casa"', count=1)
        self.assertContains(respuesta, 'data-filter-tipo="Departamento"', count=1)
        self.assertNotContains(respuesta, 'data-filter-tipo="Campo"')
        self.assertNotContains(respuesta, 'data-filter-tipo=""')
        self.assertEqual(self.ids(self.consultar(operacion="venta", tipo="Nave Industrial")), [nave.pk])

    def test_mapa_sin_publicaciones_no_inventa_tipos(self):
        Propiedad.objects.all().delete()
        respuesta = self.client.get("/propiedades/mapa/")
        self.assertContains(respuesta, "Sin tipos disponibles")
        self.assertNotContains(respuesta, "data-filter-tipo=")

    def botones_tipo(self, respuesta):
        class Parser(HTMLParser):
            botones = {}

            def handle_starttag(self, tag, attrs):
                datos = dict(attrs)
                if tag == "button" and "data-filter-tipo" in datos:
                    self.botones[datos["data-filter-tipo"]] = datos

        parser = Parser()
        parser.feed(respuesta.content.decode())
        return parser.botones

    @patch("propiedades.views.buscar_ids")
    def test_mapa_disponibilidad_de_tipos_por_operacion_en_catalogo_completo(self, buscar):
        nave = Propiedad.objects.create(
            fuente="Brega", identificador_fuente="nave", tipo="Nave Industrial", en_venta=True)
        Propiedad.objects.create(
            fuente="Avantix", identificador_fuente="nave-otra", tipo="Nave Industrial", en_venta=True)
        Propiedad.objects.create(
            fuente="Brega", identificador_fuente="campo", tipo="Campo", en_alquiler=True)
        Propiedad.objects.create(
            fuente="Brega", identificador_fuente="retirada", tipo="Chacra")
        Propiedad.objects.create(
            fuente="Brega", identificador_fuente="sin-tipo", tipo="", en_alquiler=True)
        with self.assertNumQueries(1):
            respuesta = self.client.get("/propiedades/mapa/", {
                "pagina": "99", "por_pagina": "1", "q": "sin coincidencias", "tipo": "Casa",
            })
        buscar.assert_not_called()
        botones = self.botones_tipo(respuesta)
        self.assertEqual(set(botones), {"Casa", "Departamento", "Campo", "Nave Industrial"})
        for tipo in ("Casa", "Departamento"):
            self.assertEqual(botones[tipo]["data-disponible-alquiler"], "true")
            self.assertEqual(botones[tipo]["data-disponible-venta"], "true")
            self.assertNotIn("hidden", botones[tipo])
        self.assertEqual(botones["Campo"]["data-disponible-alquiler"], "true")
        self.assertEqual(botones["Campo"]["data-disponible-venta"], "false")
        self.assertNotIn("hidden", botones["Campo"])
        self.assertEqual(botones["Nave Industrial"]["data-disponible-alquiler"], "false")
        self.assertEqual(botones["Nave Industrial"]["data-disponible-venta"], "true")
        self.assertIn("hidden", botones["Nave Industrial"])
        self.assertIn("disabled", botones["Nave Industrial"])
        self.assertEqual(self.consultar(operacion="alquiler", tipo="Nave Industrial")["total"], 0)
        self.assertIn(nave.pk, self.ids(self.consultar(operacion="venta", tipo="Nave Industrial")))

    def test_mapa_sin_tipos_en_alquiler_conserva_opciones_para_venta(self):
        Propiedad.objects.all().delete()
        Propiedad.objects.create(
            fuente="Brega", identificador_fuente="venta", tipo="Nave Industrial", en_venta=True)
        respuesta = self.client.get("/propiedades/mapa/")
        self.assertFalse(respuesta.context["hay_tipos_alquiler"])
        self.assertContains(respuesta, 'id="tipos-vacios">Sin tipos disponibles para alquilar.')
        self.assertEqual(set(self.botones_tipo(respuesta)), {"Nave Industrial"})
        self.assertIn("hidden", self.botones_tipo(respuesta)["Nave Industrial"])

    def test_selector_de_vistas_es_independiente_del_panel_de_filtros(self):
        respuesta = self.client.get('/propiedades/mapa/')
        self.assertContains(respuesta, 'id="estilos-menu"', count=1)
        for nombre in ('calles', 'oscuro', 'satelite'):
            self.assertContains(respuesta, f'data-estilo-mapa="{nombre}"', count=1)
        self.assertContains(respuesta, 'id="estilo-seleccionado">Calles</span>')
        html = respuesta.content.decode()
        self.assertLess(html.index('id="estilos-menu"'), html.index('id="filter-dock"'))
        self.assertNotContains(respuesta, 'data-estilo-mapa="positron"')
