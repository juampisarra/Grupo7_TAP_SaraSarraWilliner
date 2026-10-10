from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings

from propiedades.models import Propiedad
from propiedades.busqueda.cliente import BusquedaNoDisponible, crear_cliente
from propiedades.busqueda.indice import CAMPOS_TEXTO, documento, reconstruir_indice
from propiedades.busqueda.texto import buscar_ids, combinar_resultados


CONFIG = {
    "ELASTICSEARCH_URL": "https://ejemplo.elastic.cloud:443",
    "ELASTICSEARCH_API_KEY": "clave-de-prueba",
    "ELASTICSEARCH_INDEX": "propiedades",
    "SECURE_SSL_REDIRECT": False,
}


@override_settings(**CONFIG)
class ClienteTests(SimpleTestCase):
    @override_settings(ELASTICSEARCH_API_KEY="")
    def test_configuracion_ausente_falla_sin_mostrar_secretos(self):
        with self.assertRaises(BusquedaNoDisponible):
            crear_cliente()

    @override_settings(ELASTICSEARCH_URL="http://ejemplo.elastic.cloud")
    def test_no_envia_api_key_por_http(self):
        with self.assertRaises(BusquedaNoDisponible):
            crear_cliente()

    def test_documento_no_indexa_precios_ni_coordenadas(self):
        p = SimpleNamespace(pk=3, fuente="Brega", identificador_fuente="42",
                            **{campo: "texto" for campo in CAMPOS_TEXTO})
        d = documento(p)
        self.assertEqual(d["propiedad_id"], 3)
        self.assertNotIn("latitud", d)
        self.assertNotIn("precio_venta", d)

    @patch("propiedades.busqueda.texto.crear_cliente")
    def test_paginacion_conserva_todo_el_ranking_y_cierra_pit(self, crear):
        cliente = crear.return_value.__enter__.return_value
        cliente.open_point_in_time.return_value = {"id": "pit-original"}
        def hit(i):
            return {"_id": str(i), "_score": float(200-i), "sort": [float(200-i), i]}
        cliente.search.side_effect = [
            {"pit_id": "pit-nuevo", "hits": {"hits": [hit(i) for i in range(1, 101)]}},
            {"hits": {"hits": [hit(i) for i in range(101, 111)]}},
            {"hits": {"hits": []}},
        ]
        resultado = buscar_ids("departamento con cochera")
        self.assertEqual([pk for pk, _ in resultado], list(range(1, 111)))
        self.assertEqual(cliente.search.call_args_list[1].kwargs["search_after"], [100.0, 100])
        self.assertEqual(cliente.search.call_args_list[1].kwargs["pit"]["id"], "pit-nuevo")
        cliente.close_point_in_time.assert_called_once_with(id="pit-nuevo")

    @patch("propiedades.busqueda.texto.crear_cliente")
    def test_timeout_no_devuelve_resultados_parciales(self, crear):
        cliente = crear.return_value.__enter__.return_value
        cliente.open_point_in_time.return_value = {"id": "pit"}
        cliente.search.return_value = {"timed_out": True, "hits": {"hits": []}}
        with self.assertRaises(BusquedaNoDisponible):
            buscar_ids("cochera")
        cliente.close_point_in_time.assert_called_once()

    @patch("propiedades.busqueda.texto.crear_cliente")
    def test_rechaza_texto_excesivo_antes_de_conectarse(self, crear):
        with self.assertRaises(ValueError):
            buscar_ids("x" * 301)
        crear.assert_not_called()


@override_settings(**CONFIG)
class ReconstruccionTests(TestCase):
    def setUp(self):
        self.p = Propiedad.objects.create(fuente="Brega", identificador_fuente="1", descripcion="Casa con cochera")
        self.crear = patch("propiedades.busqueda.indice.crear_cliente").start()
        self.addCleanup(patch.stopall)
        self.cliente = self.crear.return_value.__enter__.return_value
        self.cliente.indices.exists.return_value = False
        self.cliente.indices.exists_alias.return_value = False
        self.cliente.count.return_value = {"count": 1}
        self.cliente.indices.update_aliases.return_value = {"acknowledged": True}
        self.bulk = patch("propiedades.busqueda.indice.helpers.streaming_bulk").start()
        self.enviados = []
        def enviar(cliente, acciones, **kwargs):
            for accion in acciones:
                self.enviados.append(accion)
                yield True, {}
        self.bulk.side_effect = enviar

    def test_reconstruccion_usa_id_estable_y_cambia_alias_sin_borrar(self):
        version, cantidad = reconstruir_indice()
        self.assertEqual(cantidad, 1)
        self.assertEqual(self.enviados[0]["_id"], str(self.p.pk))
        self.assertEqual(self.enviados[0]["_index"], version)
        self.cliente.indices.delete.assert_not_called()
        acciones = self.cliente.indices.update_aliases.call_args.kwargs["actions"]
        self.assertEqual(acciones, [{"add": {"index": version, "alias": "propiedades", "is_write_index": True}}])

    def test_error_de_documento_conserva_alias_anterior(self):
        self.bulk.side_effect = None
        self.bulk.return_value = iter([(False, {"error": "fallo"})])
        with self.assertRaises(BusquedaNoDisponible):
            reconstruir_indice()
        self.cliente.indices.update_aliases.assert_not_called()
        self.cliente.indices.delete.assert_not_called()

    def test_conteo_incorrecto_no_activa_indice(self):
        self.cliente.count.return_value = {"count": 0}
        with self.assertRaises(BusquedaNoDisponible):
            reconstruir_indice()
        self.cliente.indices.update_aliases.assert_not_called()

    def test_cambio_de_alias_existente_es_una_sola_operacion(self):
        self.cliente.indices.exists.return_value = True
        self.cliente.indices.exists_alias.return_value = True
        self.cliente.indices.get_alias.return_value = {"propiedades-anterior": {}}
        version, _ = reconstruir_indice()
        acciones = self.cliente.indices.update_aliases.call_args.kwargs["actions"]
        self.assertEqual(acciones[0], {"remove": {"index": "propiedades-anterior", "alias": "propiedades", "must_exist": True}})
        self.assertEqual(acciones[1]["add"]["index"], version)

    def test_no_reemplaza_indice_fisico_con_nombre_de_alias(self):
        self.cliente.indices.exists.return_value = True
        with self.assertRaises(BusquedaNoDisponible):
            reconstruir_indice()
        self.cliente.indices.create.assert_not_called()

    def test_base_vacia_no_reemplaza_el_indice_por_accidente(self):
        Propiedad.objects.all().delete()
        self.cliente.count.return_value = {"count": 0}
        with self.assertRaises(BusquedaNoDisponible):
            reconstruir_indice()
        self.cliente.indices.update_aliases.assert_not_called()


@override_settings(**CONFIG)
class CombinacionTests(TestCase):
    def setUp(self):
        self.a = Propiedad.objects.create(fuente="Brega", identificador_fuente="a", en_alquiler=True)
        self.b = Propiedad.objects.create(fuente="Brega", identificador_fuente="b", en_venta=True)
        self.c = Propiedad.objects.create(fuente="Brega", identificador_fuente="c", en_alquiler=True)

    def test_filtra_en_base_y_conserva_ranking_descartando_ids_inexistentes(self):
        hits = [(self.b.pk, 9), (self.c.pk, 8), (999999, 7), (self.a.pk, 6)]
        self.assertEqual(combinar_resultados(Propiedad.objects.filter(en_alquiler=True), hits), [self.c, self.a])

    @patch("propiedades.views.buscar_ids")
    def test_visita_sin_texto_y_health_no_consultan_elasticsearch(self, buscar):
        self.assertEqual(self.client.get("/propiedades/").status_code, 200)
        self.assertEqual(self.client.get("/health/").status_code, 200)
        buscar.assert_not_called()

    @patch("propiedades.views.buscar_ids")
    def test_busqueda_http_ordena_y_filtra_operacion(self, buscar):
        buscar.return_value = [(self.b.pk, 9), (self.c.pk, 8), (self.a.pk, 7)]
        respuesta = self.client.get("/propiedades/?q=cochera")
        self.assertEqual(list(respuesta.context["propiedades"]), [self.c, self.a])

    @patch("propiedades.views.buscar_ids", side_effect=BusquedaNoDisponible("Servicio no disponible"))
    def test_caida_de_elasticsearch_no_se_presenta_como_busqueda_vacia(self, buscar):
        self.assertEqual(self.client.get("/propiedades/?q=cochera").status_code, 503)

    @patch("propiedades.views.buscar_ids", return_value=[])
    def test_sin_coincidencias_no_devuelve_todas_las_propiedades(self, buscar):
        respuesta = self.client.get("/propiedades/?q=zzzzzz")
        self.assertEqual(list(respuesta.context["propiedades"]), [])
