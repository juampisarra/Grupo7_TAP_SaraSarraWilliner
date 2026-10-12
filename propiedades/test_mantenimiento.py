from decimal import Decimal
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings

from propiedades.busqueda.cliente import BusquedaNoDisponible
from propiedades.busqueda.mantenimiento import limpiar_indices
from propiedades.ingesta import guardar_publicacion, importar_fuente
from propiedades.models import Propiedad
from propiedades.scraping.contratos import DetallesPropiedad, PublicacionNormalizada
from propiedades.scraping.tokko import leer_listado, recorrer_paginas


@override_settings(SECURE_SSL_REDIRECT=False)
class BajasTests(TestCase):
    def setUp(self):
        pausa = patch("propiedades.ingesta.time.sleep")
        pausa.start()
        self.addCleanup(pausa.stop)
        self.anterior = Propiedad.objects.create(
            fuente="Prueba", identificador_fuente="1", en_venta=True, en_alquiler=True,
            precio_venta=Decimal("123.45"), moneda_venta="USD", precio_alquiler=Decimal("20"),
            moneda_alquiler="ARS", descripcion="Texto conservado", latitud=0, longitud=0,
            url_original="https://ejemplo.test/1",
        )
        self.listados = {"venta": [], "alquiler": []}
        self.adaptador = SimpleNamespace(
            nombre="Prueba", operaciones=("venta", "alquiler"),
            extraer=Mock(side_effect=lambda op: self.listados[op]),
            extraer_detalles=Mock(return_value=DetallesPropiedad()),
        )

    def aviso(self, id="1", **campos):
        return PublicacionNormalizada(id, f"https://ejemplo.test/{id}", **campos)

    def test_baja_por_operacion_conserva_ficha_precios_y_otra_fuente(self):
        otra = Propiedad.objects.create(fuente="Otra", identificador_fuente="1", en_venta=True)
        self.listados["alquiler"] = [self.aviso(precio=Decimal("30"), moneda="ARS", en_venta=True)]
        resumen = importar_fuente(self.adaptador)
        self.anterior.refresh_from_db()
        otra.refresh_from_db()
        self.assertFalse(self.anterior.en_venta)
        self.assertTrue(self.anterior.en_alquiler)
        self.assertEqual((resumen.bajas_venta, resumen.bajas_alquiler), (1, 0))
        self.assertEqual(self.anterior.precio_venta, Decimal("123.45"))
        self.assertEqual(self.anterior.descripcion, "Texto conservado")
        self.assertEqual(self.anterior.latitud, 0)
        self.assertTrue(otra.en_venta)

    def test_listado_vacio_confirmado_desactiva_sin_borrar_y_repeticion_es_idempotente(self):
        resumen = importar_fuente(self.adaptador)
        self.anterior.refresh_from_db()
        self.assertFalse(self.anterior.en_venta or self.anterior.en_alquiler)
        self.assertEqual((resumen.bajas_venta, resumen.bajas_alquiler), (1, 1))
        self.assertEqual(Propiedad.objects.count(), 1)
        segundo = importar_fuente(self.adaptador)
        self.assertEqual((segundo.bajas_venta, segundo.bajas_alquiler), (0, 0))

    def test_reaparicion_reactiva_misma_fila_sin_duplicar(self):
        importar_fuente(self.adaptador)
        self.listados["venta"] = [self.aviso(precio=Decimal("150"), moneda="USD")]
        importar_fuente(self.adaptador)
        self.anterior.refresh_from_db()
        self.assertTrue(self.anterior.en_venta)
        self.assertFalse(self.anterior.en_alquiler)
        self.assertEqual(self.anterior.precio_venta, Decimal("150"))
        self.assertEqual(Propiedad.objects.count(), 1)

    def test_fallo_listado_no_desactiva_ninguna_operacion(self):
        self.adaptador.extraer.side_effect = [[], requests.Timeout("Listado incompleto")]
        with self.assertRaises(requests.Timeout):
            importar_fuente(self.adaptador)
        self.anterior.refresh_from_db()
        self.assertTrue(self.anterior.en_venta and self.anterior.en_alquiler)

    def test_error_fatal_de_persistencia_conserva_vigencia_ausentes_y_escrituras_previas(self):
        self.listados["venta"] = [self.aviso("2"), self.aviso("3")]
        def guardar(fuente, id, valores):
            if id == "3":
                raise RuntimeError("Fallo fatal")
            return guardar_publicacion(fuente, id, valores)
        with patch("propiedades.ingesta.guardar_publicacion", side_effect=guardar):
            with self.assertRaises(RuntimeError):
                importar_fuente(self.adaptador)
        self.anterior.refresh_from_db()
        self.assertTrue(self.anterior.en_venta and self.anterior.en_alquiler)
        self.assertTrue(Propiedad.objects.filter(identificador_fuente="2", en_venta=True).exists())

    def test_detalle_fallido_no_es_baja_si_listado_confirma_vigencia(self):
        self.listados["venta"] = [self.aviso()]
        self.adaptador.extraer_detalles.side_effect = requests.Timeout("Ficha")
        resumen = importar_fuente(self.adaptador)
        self.anterior.refresh_from_db()
        self.assertTrue(self.anterior.en_venta)
        self.assertFalse(self.anterior.en_alquiler)
        self.assertEqual(resumen.errores_detalle, 1)

    def test_tarjeta_invalida_inhibe_todas_las_bajas_de_la_fuente(self):
        for aviso in (PublicacionNormalizada(None, "https://ejemplo.test"), PublicacionNormalizada("1", None)):
            self.listados["venta"] = [aviso]
            resumen = importar_fuente(self.adaptador)
            self.anterior.refresh_from_db()
            self.assertTrue(self.anterior.en_venta and self.anterior.en_alquiler)
            self.assertEqual(resumen.bajas_omitidas, 1)

    def test_adaptador_de_una_operacion_no_modifica_la_otra(self):
        self.adaptador.operaciones = ("venta",)
        importar_fuente(self.adaptador)
        self.anterior.refresh_from_db()
        self.assertFalse(self.anterior.en_venta)
        self.assertTrue(self.anterior.en_alquiler)
        self.assertEqual(self.anterior.precio_alquiler, Decimal("20"))

    @patch("propiedades.views.buscar_ids")
    def test_html_y_json_excluyen_retirada_aunque_indice_anterior_aun_la_devuelva(self, buscar):
        importar_fuente(self.adaptador)
        buscar.return_value = [(self.anterior.pk, 10)]
        for path in ("/api/propiedades/", "/propiedades/"):
            for op in ("venta", "alquiler"):
                for texto in ("", "cochera"):
                    respuesta = self.client.get(path, {"operacion": op, "q": texto})
                    self.assertEqual(respuesta.status_code, 200)
                    if path.startswith("/api"):
                        self.assertEqual(respuesta.json()["total"], 0)
                    else:
                        self.assertEqual(list(respuesta.context["propiedades"]), [])

    def test_operaciones_invalidas_no_reconcilian(self):
        for operaciones in ((), ("venta", "venta"), ("desconocida",)):
            self.adaptador.operaciones = operaciones
            with self.assertRaises(ValueError):
                importar_fuente(self.adaptador)
        self.anterior.refresh_from_db()
        self.assertTrue(self.anterior.en_venta and self.anterior.en_alquiler)

    def test_error_durante_conciliacion_revierte_bajas_de_ambas_operaciones(self):
        from django.db.models.query import QuerySet
        actualizar = QuerySet.update
        def update(queryset, **valores):
            if valores.get("en_alquiler") is False:
                raise RuntimeError("Fallo segunda operación")
            return actualizar(queryset, **valores)
        with patch.object(QuerySet, "update", update):
            with self.assertRaises(RuntimeError):
                importar_fuente(self.adaptador)
        self.anterior.refresh_from_db()
        self.assertTrue(self.anterior.en_venta and self.anterior.en_alquiler)


class IntegridadListadoTests(SimpleTestCase):
    def test_html_desconocido_no_se_interpreta_como_cero_avisos(self):
        for html in ("", "<html>Mantenimiento</html>", "<li>Una tarjeta que cambió de formato</li>"):
            with self.assertRaises(ValueError):
                leer_listado(html, "https://ejemplo.test")
        self.assertEqual(leer_listado(" --NoMoreProperties--\n", "https://ejemplo.test"), [])

    def test_pagina_repetida_no_se_interpreta_como_fin(self):
        extraer = Mock(return_value=[{"identificador_fuente": "1"}])
        with self.assertRaisesMessage(ValueError, "repetida"):
            recorrer_paginas(extraer, "venta", 50, Mock())
        self.assertEqual(extraer.call_count, 2)

    def test_superposicion_parcial_de_paginas_tambien_rechaza_listado(self):
        extraer = Mock(side_effect=[
            [{"identificador_fuente": "1"}],
            [{"identificador_fuente": "1"}, {"identificador_fuente": "2"}],
        ])
        with self.assertRaisesMessage(ValueError, "repetida"):
            recorrer_paginas(extraer, "venta", 50, Mock())


@override_settings(ELASTICSEARCH_INDEX="propiedades")
class LimpiezaTests(SimpleTestCase):
    def setUp(self):
        self.activo = "propiedades-20261012065209-aaaaaaaa"
        self.anterior = "propiedades-20261011065209-bbbbbbbb"
        self.viejo = "propiedades-20261010065209-cccccccc"
        self.otro_alias = "propiedades-20261009065209-dddddddd"
        self.futuro = "propiedades-20261013065209-eeeeeeee"
        self.mismo_segundo = "propiedades-20261012065209-00000000"
        self.inventario = {
            self.activo: {"aliases": {"propiedades": {}}},
            self.anterior: {"aliases": {}}, self.viejo: {"aliases": {}},
            self.otro_alias: {"aliases": {"otro": {}}}, self.futuro: {"aliases": {}},
            self.mismo_segundo: {"aliases": {}}, "propiedades-ajeno": {"aliases": {}},
        }
        parche = patch("propiedades.busqueda.mantenimiento.crear_cliente")
        self.cliente = parche.start().return_value.__enter__.return_value
        self.addCleanup(parche.stop)
        self.activos = {self.activo: self.inventario[self.activo]}
        self.cliente.indices.get_alias.side_effect = lambda **kw: self.activos if "name" in kw else self.inventario
        self.meta = {"alias": "propiedades", "completo": True, "anteriores": [self.anterior]}
        self.cliente.indices.get_mapping.side_effect = lambda **kw: {self.activo: {"mappings": {"_meta": {"grupo7": self.meta}}}}
        self.cliente.indices.delete.return_value = {"acknowledged": True}

    def test_vista_previa_protege_activo_anterior_aliases_nombres_ajenos_y_nuevos(self):
        salida = StringIO()
        call_command("limpiar_indices", stdout=salida)
        self.assertIn(self.viejo, salida.getvalue())
        self.assertIn("Vista previa", salida.getvalue())
        self.cliente.indices.delete.assert_not_called()
        plan, eliminados = limpiar_indices()
        self.assertEqual(plan.candidatos, (self.viejo,))
        self.assertIn(self.anterior, plan.conservar)
        self.assertEqual(eliminados, [])

    def test_aplicar_borra_solo_nombres_concretos_candidatos(self):
        _, eliminados = limpiar_indices(aplicar=True)
        self.assertEqual(eliminados, [self.viejo])
        self.cliente.indices.delete.assert_called_once_with(index=self.viejo)

    def test_sin_metadatos_anteriores_no_adivina_ni_borra(self):
        self.meta.clear()
        plan, _ = limpiar_indices()
        self.assertTrue(plan.advertencia)
        self.assertEqual(plan.candidatos, ())
        with self.assertRaises(CommandError):
            call_command("limpiar_indices", "--aplicar", stdout=StringIO())
        self.cliente.indices.delete.assert_not_called()

    def test_antecesor_registrado_ausente_impide_borrados(self):
        del self.inventario[self.anterior]
        plan, _ = limpiar_indices()
        self.assertEqual(plan.candidatos, ())
        with self.assertRaisesMessage(BusquedaNoDisponible, "Falta una versión anterior"):
            limpiar_indices(aplicar=True)
        self.cliente.indices.delete.assert_not_called()

    def test_alias_multiple_o_formato_desconocido_no_permiten_limpieza(self):
        for activos in ({self.activo: {}, self.anterior: {}}, {"propiedades-ajeno": {}}):
            self.activos = activos
            with self.assertRaises(BusquedaNoDisponible):
                limpiar_indices(aplicar=True)
        self.cliente.indices.delete.assert_not_called()

    def test_cambio_de_alias_antes_de_borrar_aborta(self):
        llamadas = 0
        def aliases(**kw):
            nonlocal llamadas
            if "name" not in kw:
                return self.inventario
            llamadas += 1
            return self.activos if llamadas == 1 else {self.anterior: {}}
        self.cliente.indices.get_alias.side_effect = aliases
        with self.assertRaises(BusquedaNoDisponible):
            limpiar_indices(aplicar=True)
        self.cliente.indices.delete.assert_not_called()

    def test_nuevo_alias_en_candidato_aborta_antes_del_borrado(self):
        llamadas = 0
        def aliases(**kw):
            nonlocal llamadas
            if "name" in kw:
                return self.activos
            llamadas += 1
            if llamadas == 2:
                self.inventario[self.viejo]["aliases"] = {"nuevo": {}}
            return self.inventario
        self.cliente.indices.get_alias.side_effect = aliases
        with self.assertRaises(BusquedaNoDisponible):
            limpiar_indices(aplicar=True)
        self.cliente.indices.delete.assert_not_called()

    def test_error_red_no_oculta_que_pueden_existir_borrados_previos(self):
        from elastic_transport import ConnectionError
        self.cliente.indices.delete.side_effect = ConnectionError("fallo")
        with self.assertRaisesMessage(BusquedaNoDisponible, "no se revierten"):
            limpiar_indices(aplicar=True)

    def test_respuesta_no_confirmada_aborta(self):
        self.cliente.indices.delete.return_value = {"acknowledged": False}
        with self.assertRaisesMessage(BusquedaNoDisponible, "No se confirmó"):
            limpiar_indices(aplicar=True)
