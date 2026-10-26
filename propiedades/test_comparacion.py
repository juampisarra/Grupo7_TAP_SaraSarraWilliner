from datetime import timedelta
from decimal import Decimal
import json
from unittest.mock import Mock, patch

from django.test import Client, TestCase, override_settings
from django.utils import timezone

from .comparacion import datos_para_llm, preparar_comparacion
from .comparacion_ia import analizar_comparacion, consumir_cuota
from .llm.cliente import generar_analisis, LLMNoDisponible, validar_respuesta
from .models import ComparacionGenerada, Propiedad, UsoComparacion


def analisis(ids):
    return {
        "resumen": "Alternativas con diferencias de precio y distribución.",
        "diferencias": ["La primera tiene menor precio publicado."],
        "por_propiedad": [{"propiedad_id": pid, "ventajas": ["Precio informado."],
                           "limitaciones": ["Consultar condiciones con la inmobiliaria."]} for pid in ids],
        "datos_faltantes": ["Superficie no informada."],
        "conclusion": "Si priorizás el precio, considerá la alternativa de menor valor publicado.",
    }


@override_settings(SECURE_SSL_REDIRECT=False, GEMINI_API_KEY="clave-simulada", GEMINI_MODEL="modelo-prueba")
class ComparacionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = Propiedad.objects.create(
            fuente="Brega", identificador_fuente="comparar-a", tipo="Casa", direccion="Mitre 100",
            en_alquiler=True, precio_alquiler=Decimal("500000.25"), moneda_alquiler="ARS",
            dormitorios=0, dormitorios_verificados=False, caracteristicas="Patio; cochera",
            ciudad="Rafaela", latitud=-31.25, longitud=-61.49, ubicacion_aproximada=True,
            url_original="https://example.com/a",
        )
        cls.b = Propiedad.objects.create(
            fuente="Avantix", identificador_fuente="comparar-b", tipo="Casa", direccion="Mitre 100",
            en_alquiler=True, precio_alquiler=Decimal("600000.30"), moneda_alquiler="ARS",
            dormitorios=None, url_original="https://example.com/b",
        )

    def tabla(self, ids=None, **extra):
        return self.client.get("/api/propiedades/comparacion/", {
            "ids": ",".join(map(str, ids or [self.a.pk, self.b.pk])), "operacion": "alquiler", **extra,
        })

    def post(self, **cambios):
        datos = self.tabla().json()
        cuerpo = {"ids": [self.a.pk, self.b.pk], "operacion": "alquiler", "firma": datos["firma"], **cambios}
        return self.client.post("/api/propiedades/comparacion/analisis/", data=json.dumps(cuerpo), content_type="application/json")

    def test_tabla_actual_preserva_orden_publicaciones_fuentes_y_decimales(self):
        with patch("propiedades.views.buscar_ids") as buscar:
            with self.assertNumQueries(1):
                respuesta = self.tabla([self.b.pk, self.a.pk])
            buscar.assert_not_called()
        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.json()
        self.assertEqual([p["id"] for p in datos["propiedades"]], [self.b.pk, self.a.pk])
        self.assertEqual(datos["propiedades"][0]["diferencia_con_menor_precio"], "100000.05")
        self.assertEqual(datos["propiedades"][1]["precio"], "500000.25")
        self.assertIsNone(datos["propiedades"][0]["dormitorios"])
        self.assertEqual(datos["propiedades"][1]["dormitorios"], 0)
        self.assertFalse(datos["propiedades"][1]["dormitorios_verificados"])
        self.assertEqual(datos["propiedades"][1]["precision"], "aproximada")
        self.assertEqual(datos["propiedades"][0]["precision"], "sin_coordenadas")
        self.assertEqual(datos["firma"], self.tabla().json()["firma"])
        self.assertIn("no-store", respuesta["Cache-Control"])
        self.assertNotIn("clave-simulada", respuesta.content.decode())

    def test_no_compara_precios_de_distintas_monedas_desconocidos_o_sin_moneda(self):
        for cambios in ({"moneda_alquiler": "USD"}, {"moneda_alquiler": ""}, {"precio_alquiler": None}):
            with self.subTest(cambios=cambios):
                Propiedad.objects.filter(pk=self.b.pk).update(**{"precio_alquiler": 600000, "moneda_alquiler": "ARS", **cambios})
                datos = self.tabla().json()
                self.assertFalse(datos["precios_comparables"])
                self.assertTrue(all(p["diferencia_con_menor_precio"] is None for p in datos["propiedades"]))

    def test_selecciones_invalidas_y_avisos_retirados(self):
        for ids in ("1", "1,2,3,4,5", "1,1", "-1,2", "1.0,2", "true,2", "0,2", "9" * 100 + ",2"):
            with self.subTest(ids=ids):
                self.assertEqual(self.tabla(ids=[ids]).status_code, 400)
        self.assertEqual(self.client.get("/api/propiedades/comparacion/?ids=1,2&ids=3,4&operacion=alquiler").status_code, 400)
        faltante = self.tabla([self.a.pk, 999999])
        self.assertEqual(faltante.status_code, 404)
        self.assertEqual(faltante.json()["ids"], [999999])
        Propiedad.objects.filter(pk=self.b.pk).update(en_alquiler=False)
        retirada = self.tabla()
        self.assertEqual(retirada.status_code, 409)
        self.assertEqual(retirada.json()["ids"], [self.b.pk])
        self.assertEqual(self.tabla(operacion="compra").status_code, 400)

    @patch("propiedades.comparacion_ia.generar_analisis")
    def test_post_usa_datos_del_servidor_cache_compartida_y_csrf(self, generar):
        generar.return_value = analisis([self.a.pk, self.b.pk])
        primero = self.post()
        self.assertEqual(primero.status_code, 200, primero.content)
        self.assertFalse(primero.json()["reutilizado"])
        self.assertTrue(self.post().json()["reutilizado"])
        generar.assert_called_once()
        self.assertEqual(ComparacionGenerada.objects.count(), 1)
        self.assertEqual(UsoComparacion.objects.count(), 3)
        self.assertEqual(self.post(precio="1").status_code, 400)
        csrf = Client(enforce_csrf_checks=True)
        cuerpo = {"ids": [self.a.pk, self.b.pk], "operacion": "alquiler", "firma": self.tabla().json()["firma"]}
        self.assertEqual(csrf.post("/api/propiedades/comparacion/analisis/", data=json.dumps(cuerpo), content_type="application/json").status_code, 403)
        mapa = csrf.get("/propiedades/mapa/")
        self.assertTrue(mapa.cookies["comparador_visitante"]["httponly"])
        self.assertEqual(csrf.post("/api/propiedades/comparacion/analisis/", data=json.dumps(cuerpo), content_type="application/json",
                                   HTTP_X_CSRFTOKEN=mapa.cookies["csrftoken"].value).status_code, 200)

    @patch("propiedades.comparacion_ia.generar_analisis")
    def test_snapshot_cambiado_antes_o_durante_ia_no_se_presenta_como_actual(self, generar):
        datos = self.tabla().json()
        Propiedad.objects.filter(pk=self.a.pk).update(precio_alquiler=450000)
        self.assertEqual(self.post(firma=datos["firma"]).json()["codigo"], "datos_cambiaron")
        generar.assert_not_called()
        def modificar(entrada):
            Propiedad.objects.filter(pk=self.b.pk).update(en_alquiler=False)
            return analisis([self.a.pk, self.b.pk])
        generar.side_effect = modificar
        self.assertEqual(self.post().json()["codigo"], "publicaciones_retiradas")

    @patch("propiedades.comparacion_ia.generar_analisis")
    @override_settings(COMPARACION_LIMITE_VISITANTE=1)
    def test_cuota_reserva_y_recuperacion_de_fallos(self, generar):
        generar.return_value = analisis([self.a.pk, self.b.pk])
        datos = preparar_comparacion([self.a.pk, self.b.pk], "alquiler")
        analizar_comparacion(datos, "visitante")
        datos["propiedades"][0]["caracteristicas"] = "Pileta"
        with self.assertRaises(LLMNoDisponible) as error:
            analizar_comparacion(datos, "visitante")
        self.assertEqual(error.exception.status, 429)
        self.assertEqual(ComparacionGenerada.objects.count(), 1, "La reserva denegada no queda bloqueada")
        generar.side_effect = LLMNoDisponible("Fallo simulado")
        with self.assertRaises(LLMNoDisponible):
            analizar_comparacion(datos, "otro")
        self.assertEqual(ComparacionGenerada.objects.count(), 1)

    @patch("propiedades.comparacion_ia.generar_analisis")
    def test_reserva_en_curso_no_duplica_llamada_y_vence(self, generar):
        generar.return_value = analisis([self.a.pk, self.b.pk])
        self.post()
        cache = ComparacionGenerada.objects.get()
        cache.resultado = {}; cache.vence_en = timezone.now() + timedelta(seconds=50); cache.save()
        self.assertEqual(self.post().json()["codigo"], "analisis_en_curso")
        self.assertEqual(generar.call_count, 1)
        cache.vence_en = timezone.now() - timedelta(seconds=1); cache.save()
        self.assertEqual(self.post().status_code, 200)
        self.assertEqual(generar.call_count, 2)

    @override_settings(GEMINI_API_KEY="", GEMINI_MODEL="")
    def test_sin_gemini_funciona_tabla_y_no_crea_reserva(self):
        self.assertFalse(self.tabla().json()["ia_disponible"])
        self.assertEqual(self.post().status_code, 503)
        self.assertEqual(ComparacionGenerada.objects.count(), 0)

    def test_payload_acotado_sin_contactos_comentarios_direccion_fotos_o_coordenadas(self):
        Propiedad.objects.filter(pk=self.a.pk).update(caracteristicas="Patio https://example.com/contacto hola@example.com +54 3492 123456 " + "x" * 5000)
        entrada = datos_para_llm(preparar_comparacion([self.a.pk, self.b.pk], "alquiler"))
        self.assertLessEqual(len(entrada["propiedades"][0]["caracteristicas_publicadas"]), 1600)
        texto = json.dumps(entrada)
        for prohibido in ("3492", "hola@example.com", "https://", "Mitre 100", "latitud", "url_original", "comentarios", "foto_portada"):
            self.assertNotIn(prohibido, texto)

    @override_settings(COMPARACION_LIMITE_MINUTO=2, COMPARACION_LIMITE_DIA=3)
    def test_cuotas_globales_compartidas_y_rollback_de_intentos_denegados(self):
        ahora = timezone.now()
        consumir_cuota("uno", ahora)
        consumir_cuota("dos", ahora)
        with self.assertRaises(LLMNoDisponible):
            consumir_cuota("tres", ahora)
        self.assertFalse(UsoComparacion.objects.filter(clave__startswith="visitante:tres:").exists())
        siguiente = ahora + timedelta(minutes=1)
        consumir_cuota("tres", siguiente)
        with self.assertRaises(LLMNoDisponible):
            consumir_cuota("cuatro", siguiente)
        self.assertEqual(UsoComparacion.objects.get(clave__startswith="global:dia:").solicitudes, 3)

    @patch("propiedades.comparacion_ia.generar_analisis")
    def test_solicitud_durante_http_encuentra_reserva_compartida(self, generar):
        datos = preparar_comparacion([self.a.pk, self.b.pk], "alquiler")
        def durante_http(entrada):
            with self.assertRaises(LLMNoDisponible) as error:
                analizar_comparacion(datos, "otro-worker")
            self.assertEqual(error.exception.codigo, "analisis_en_curso")
            return analisis([self.a.pk, self.b.pk])
        generar.side_effect = durante_http
        analizar_comparacion(datos, "primero")
        generar.assert_called_once()

    @patch("propiedades.llm.cliente.requests.post")
    def test_cliente_rest_valida_salida_y_no_expone_credenciales(self, post):
        salida = analisis([self.a.pk, self.b.pk])
        post.return_value = Mock(status_code=200)
        post.return_value.json.return_value = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(salida)}]}}]}
        entrada = datos_para_llm(preparar_comparacion([self.a.pk, self.b.pk], "alquiler"))
        self.assertEqual(generar_analisis(entrada), salida)
        self.assertNotIn("clave-simulada", post.call_args.args[0])
        self.assertFalse(post.call_args.kwargs["allow_redirects"])
        for status in (403, 429, 500):
            post.return_value.status_code = status
            with self.assertRaises(LLMNoDisponible) as error:
                generar_analisis(entrada)
            self.assertNotIn("clave-simulada", str(error.exception))
        salida["por_propiedad"][0]["propiedad_id"] = 99999
        with self.assertRaises(LLMNoDisponible):
            validar_respuesta(salida, [self.a.pk, self.b.pk])

    @patch("propiedades.llm.cliente.requests.post")
    def test_cliente_rechaza_respuestas_truncadas_bloqueadas_y_timeouts(self, post):
        import requests
        entrada = datos_para_llm(preparar_comparacion([self.a.pk, self.b.pk], "alquiler"))
        for cuerpo in ({}, {"candidates": []}, {"candidates": [{"finishReason": "MAX_TOKENS"}]},
                       {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "{"}]}}]}):
            post.return_value = Mock(status_code=200)
            post.return_value.json.return_value = cuerpo
            with self.assertRaises(LLMNoDisponible):
                generar_analisis(entrada)
        post.side_effect = requests.Timeout("Error que podría incluir información interna")
        with self.assertRaises(LLMNoDisponible) as error:
            generar_analisis(entrada)
        self.assertNotIn("información interna", str(error.exception))

    def test_json_invalido_metodos_y_plantilla(self):
        url = "/api/propiedades/comparacion/analisis/"
        for cuerpo in ("{", "[]", json.dumps({"ids": [True, 2], "operacion": "alquiler", "firma": "x"}), "x" * 5000):
            self.assertEqual(self.client.post(url, data=cuerpo, content_type="application/json").status_code, 400)
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post("/api/propiedades/comparacion/").status_code, 405)
        mapa = self.client.get("/propiedades/mapa/")
        for id_elemento in ("comparador", "card-comparar", "comparacion-barra", "comparacion-tabla", "comparacion-analisis"):
            self.assertContains(mapa, f'id="{id_elemento}"', count=1)
        self.assertNotContains(mapa, "clave-simulada")
