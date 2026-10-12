from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from propiedades.ingesta import ResumenIngesta
from propiedades.models import Propiedad
from propiedades.scraping.contratos import DetallesPropiedad, PublicacionNormalizada


MODULO = "propiedades.management.commands.importar_propiedades"


class ToleranciaComandoTests(SimpleTestCase):
    def setUp(self):
        self.salida = StringIO()
        self.errores = StringIO()
        self.fuentes = {
            "avantix": Mock(return_value=SimpleNamespace(nombre="Avantix")),
            "brega": Mock(return_value=SimpleNamespace(nombre="Brega")),
        }
        self.registro = patch(f"{MODULO}.FUENTES", self.fuentes)
        self.registro.start()
        self.addCleanup(self.registro.stop)

    def ejecutar(self, *args, comando="importar_propiedades"):
        return call_command(
            comando, *args, stdout=self.salida, stderr=self.errores, no_color=True,
        )

    def test_fallo_primero_o_ultimo_es_parcial_y_se_intentan_ambos(self):
        for orden in (
            [requests.Timeout("Timeout de listado"), ResumenIngesta(creadas=2)],
            [ResumenIngesta(actualizadas=1), RuntimeError("Límite de páginas")],
        ):
            with self.subTest(orden=orden), patch(
                f"{MODULO}.importar_fuente", side_effect=orden,
            ) as importar:
                with self.assertRaises(CommandError) as fallo:
                    self.ejecutar("--completar-ubicacion")
                self.assertEqual(fallo.exception.returncode, 3)
                self.assertEqual(
                    [c.args[0].nombre for c in importar.call_args_list],
                    ["Avantix", "Brega"],
                )
                self.assertTrue(all(
                    c.kwargs["completar_ubicacion"] for c in importar.call_args_list
                ))
        self.assertIn("Timeout de listado", self.errores.getvalue())
        self.assertIn("Límite de páginas", self.errores.getvalue())
        self.assertIn("Fuentes completadas: brega. Fuentes fallidas: avantix.", self.salida.getvalue())
        self.assertIn("Fuentes completadas: avantix. Fuentes fallidas: brega.", self.salida.getvalue())

    def test_todas_fallidas_informa_ambas_y_salida_uno(self):
        with patch(f"{MODULO}.importar_fuente", side_effect=ValueError("Listado inválido")) as importar:
            with self.assertRaises(CommandError) as fallo:
                self.ejecutar()
        self.assertEqual(importar.call_count, 2)
        self.assertEqual(fallo.exception.returncode, 1)
        self.assertIn("Fuentes fallidas: avantix, brega", str(fallo.exception))
        self.assertIn("Fuentes completadas: ninguna", self.salida.getvalue())

    def test_error_al_crear_adaptador_no_impide_siguiente(self):
        self.fuentes["avantix"].side_effect = RuntimeError("Configuración inválida")
        with patch(f"{MODULO}.importar_fuente", return_value=ResumenIngesta()) as importar:
            with self.assertRaises(CommandError) as fallo:
                self.ejecutar()
        self.assertEqual(fallo.exception.returncode, 3)
        self.assertEqual(importar.call_count, 1)
        self.assertEqual(importar.call_args.args[0].nombre, "Brega")

    def test_fuente_individual_y_alias_fallan_sin_ejecutar_otras(self):
        for comando, argumentos in (
            ("importar_propiedades", ("brega",)), ("importar_brega", ()),
        ):
            with self.subTest(comando=comando), patch(
                f"{MODULO}.importar_fuente", side_effect=requests.ConnectionError("Sin conexión"),
            ) as importar:
                with self.assertRaises(CommandError) as fallo:
                    self.ejecutar(*argumentos, comando=comando)
                self.assertEqual(fallo.exception.returncode, 1)
                self.assertEqual(importar.call_count, 1)
                self.assertEqual(importar.call_args.args[0].nombre, "Brega")
        self.fuentes["avantix"].assert_not_called()

    def test_interrupcion_no_se_convierte_en_fallo_por_fuente(self):
        for interrupcion in (KeyboardInterrupt, SystemExit):
            with self.subTest(interrupcion=interrupcion), patch(
                f"{MODULO}.importar_fuente", side_effect=interrupcion,
            ) as importar:
                with self.assertRaises(interrupcion):
                    self.ejecutar()
                self.assertEqual(importar.call_count, 1)
        self.fuentes["brega"].assert_not_called()

    def test_sin_fuentes_es_error_no_exito(self):
        self.fuentes.clear()
        with self.assertRaisesMessage(CommandError, "No hay fuentes registradas") as fallo:
            self.ejecutar()
        self.assertEqual(fallo.exception.returncode, 1)

    def test_fichas_fallidas_conservan_semantica_de_fuente_completada(self):
        with patch(f"{MODULO}.importar_fuente", return_value=ResumenIngesta(errores_detalle=1)):
            self.ejecutar()
        self.assertIn("Errores detalle: 1", self.salida.getvalue())
        self.assertIn("Fuentes completadas: avantix, brega. Fuentes fallidas: ninguna.", self.salida.getvalue())
        self.assertEqual(self.errores.getvalue(), "")

    def test_cli_devuelve_codigo_parcial_al_shell(self):
        from propiedades.management.commands.importar_propiedades import Command

        comando = Command(stdout=self.salida, stderr=self.errores, no_color=True)
        comando.requires_system_checks = []
        with patch(
            f"{MODULO}.importar_fuente",
            side_effect=[requests.Timeout("Timeout"), ResumenIngesta()],
        ):
            with self.assertRaises(SystemExit) as salida:
                comando.run_from_argv(["manage.py", "importar_propiedades"])
        self.assertEqual(salida.exception.code, 3)


class ConservacionDatosAnteFalloTests(TestCase):
    @patch("propiedades.ingesta.time.sleep")
    def test_listado_fallido_conserva_datos_previos_y_guarda_otra_fuente_sin_duplicar(self, dormir):
        anterior = Propiedad.objects.create(
            fuente="Avantix", identificador_fuente="anterior",
            direccion="Dirección anterior", url_original="https://example.test/anterior",
        )
        aviso = PublicacionNormalizada(
            identificador_fuente="nuevo", url_original="https://example.test/nuevo",
            direccion="Dirección nueva", tipo="Casa", en_venta=True,
        )
        avantix = SimpleNamespace(
            nombre="Avantix", operaciones=("venta", "alquiler"),
            extraer=Mock(side_effect=[[], requests.Timeout("Falló alquiler")]),
        )
        brega = SimpleNamespace(
            nombre="Brega", operaciones=("venta",), extraer=Mock(return_value=[aviso]),
            extraer_detalles=Mock(return_value=DetallesPropiedad()),
        )
        with patch(f"{MODULO}.FUENTES", {"avantix": lambda: avantix, "brega": lambda: brega}):
            for _ in range(2):
                avantix.extraer.side_effect = [[], requests.Timeout("Falló alquiler")]
                with self.assertRaises(CommandError) as fallo:
                    call_command("importar_propiedades", stdout=StringIO(), stderr=StringIO())
                self.assertEqual(fallo.exception.returncode, 3)
                anterior.refresh_from_db()
                self.assertEqual(anterior.direccion, "Dirección anterior")
                self.assertEqual(Propiedad.objects.count(), 2)
                self.assertTrue(Propiedad.objects.filter(fuente="Brega", identificador_fuente="nuevo").exists())
