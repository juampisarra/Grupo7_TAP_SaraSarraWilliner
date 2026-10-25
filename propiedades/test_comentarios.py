from decimal import Decimal
import json

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.test import Client, TestCase, override_settings

from .models import Comentario, Propiedad


@override_settings(SECURE_SSL_REDIRECT=False)
class ComentariosPropiedadTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.propiedad = Propiedad.objects.create(
            fuente="Brega",
            identificador_fuente="101",
            tipo="Casa",
            direccion="San Martín 123",
            en_alquiler=True,
            precio_alquiler=Decimal("450000"),
            moneda_alquiler="ARS",
        )
        cls.otra = Propiedad.objects.create(
            fuente="Avantix",
            identificador_fuente="202",
            tipo="Departamento",
            en_venta=True,
            precio_venta=Decimal("80000"),
            moneda_venta="USD",
        )

    def url(self, propiedad_id=None):
        pid = self.propiedad.pk if propiedad_id is None else propiedad_id
        return f"/api/propiedades/{pid}/comentarios/"

    def test_modelo_normaliza_alias_vacio_a_anonimo_y_valida_longitudes(self):
        comentario = Comentario(propiedad=self.propiedad, autor="   ", texto="  Muy buena ubicación.  ")
        comentario.clean()
        self.assertEqual(comentario.autor, "Anónimo")
        self.assertEqual(comentario.texto, "Muy buena ubicación.")

        for texto_invalido in ("", "  ", "ab", "x" * 501):
            with self.subTest(texto=texto_invalido):
                invalido = Comentario(propiedad=self.propiedad, autor="Juan", texto=texto_invalido)
                with self.assertRaises(ValidationError):
                    invalido.clean()

        autor_largo = Comentario(propiedad=self.propiedad, autor="a" * 61, texto="Comentario válido")
        with self.assertRaises(ValidationError):
            autor_largo.clean()

    def test_get_lista_solo_comentarios_activos_de_la_propiedad_en_orden_reciente(self):
        primero = Comentario.objects.create(
            propiedad=self.propiedad, autor="Lucía", texto="Excelente iluminación natural.",
        )
        segundo = Comentario.objects.create(
            propiedad=self.propiedad, autor="Anónimo", texto="Consulté y sigue disponible.",
        )
        Comentario.objects.create(
            propiedad=self.propiedad, autor="Spam", texto="Ocultado por moderación.", activo=False,
        )
        Comentario.objects.create(
            propiedad=self.otra, autor="Pedro", texto="Comentario de otra propiedad.",
        )

        respuesta = self.client.get(self.url())
        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.json()
        self.assertEqual(datos["propiedad_id"], self.propiedad.pk)
        self.assertEqual(datos["total"], 2)
        self.assertEqual([c["id"] for c in datos["comentarios"]], [segundo.pk, primero.pk])
        self.assertEqual(datos["comentarios"][0]["autor"], "Anónimo")
        self.assertEqual(datos["comentarios"][1]["autor"], "Lucía")

    def test_propiedad_inexistente_devuelve_404_en_get_y_post(self):
        self.assertEqual(self.client.get(self.url(999999)).status_code, 404)
        respuesta_post = self.client.post(
            self.url(999999),
            data=json.dumps({"texto": "Hola mundo"}),
            content_type="application/json",
        )
        self.assertEqual(respuesta_post.status_code, 404)

    def test_post_json_crea_comentario_con_alias_y_respaldo_anonimo(self):
        r1 = self.client.post(
            self.url(),
            data=json.dumps({"autor": "  Martín  ", "texto": "  Muy amplio el patio trasero.  "}),
            content_type="application/json",
        )
        self.assertEqual(r1.status_code, 201, r1.content)
        creado1 = r1.json()["comentario"]
        self.assertEqual(creado1["autor"], "Martín")
        self.assertEqual(creado1["texto"], "Muy amplio el patio trasero.")
        self.assertEqual(creado1["propiedad_id"], self.propiedad.pk)

        r2 = self.client.post(
            self.url(),
            data=json.dumps({"texto": "Alguien sabe si acepta mascotas?"}),
            content_type="application/json",
        )
        self.assertEqual(r2.status_code, 201, r2.content)
        creado2 = r2.json()["comentario"]
        self.assertEqual(creado2["autor"], "Anónimo")
        self.assertEqual(Comentario.objects.filter(propiedad=self.propiedad).count(), 2)

    def test_post_rechaza_entradas_invalidas_y_duplicados_inmediatos(self):
        casos_invalidos = [
            {},
            {"texto": ""},
            {"texto": "ok"},
            {"texto": "x" * 501},
            {"autor": "a" * 61, "texto": "Comentario válido"},
            {"autor": ["lista"], "texto": "Comentario válido"},
            {"autor": "Ana", "texto": 12345},
        ]
        for payload in casos_invalidos:
            with self.subTest(payload=payload):
                respuesta = self.client.post(
                    self.url(),
                    data=json.dumps(payload),
                    content_type="application/json",
                )
                self.assertEqual(respuesta.status_code, 400)
                self.assertIn("error", respuesta.json())

        mal_json = self.client.post(self.url(), data="{invalido", content_type="application/json")
        self.assertEqual(mal_json.status_code, 400)

        # Duplicado inmediato dentro de la ventana de 60 segundos
        valido = {"autor": "Sofía", "texto": "Me interesa coordinar una visita."}
        primera = self.client.post(self.url(), data=json.dumps(valido), content_type="application/json")
        self.assertEqual(primera.status_code, 201)
        repetida = self.client.post(self.url(), data=json.dumps(valido), content_type="application/json")
        self.assertEqual(repetida.status_code, 429)

    def test_proteccion_csrf_activa_en_post_y_cookie_en_mapa(self):
        cliente_csrf = Client(enforce_csrf_checks=True)
        sin_token = cliente_csrf.post(
            self.url(),
            data=json.dumps({"texto": "Intento sin token CSRF"}),
            content_type="application/json",
        )
        self.assertEqual(sin_token.status_code, 403)

        vista_mapa = cliente_csrf.get("/propiedades/mapa/")
        self.assertEqual(vista_mapa.status_code, 200)
        self.assertIn("csrftoken", vista_mapa.cookies)
        token = vista_mapa.cookies["csrftoken"].value

        con_token = cliente_csrf.post(
            self.url(),
            data=json.dumps({"autor": "Tester", "texto": "Envío válido con CSRF token."}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(con_token.status_code, 201)

    def test_comentario_registrado_en_django_admin(self):
        self.assertIn(Comentario, admin.site._registry)
        admin_model = admin.site._registry[Comentario]
        comentario = Comentario.objects.create(
            propiedad=self.propiedad,
            autor="Carlos",
            texto="x" * 80,
        )
        resumen = admin_model.resumen_texto(comentario)
        self.assertEqual(len(resumen), 61)
        self.assertTrue(resumen.endswith("…"))


    def test_plantilla_mapa_incluye_seccion_de_comentarios_en_la_ficha(self):
        respuesta = self.client.get("/propiedades/mapa/")
        self.assertEqual(respuesta.status_code, 200)
        for elemento_id in (
            "card-comments-section",
            "card-comments-badge",
            "card-comments-status",
            "card-comments-list",
            "form-comentario",
            "comentario-autor",
            "comentario-texto",
            "comentario-contador",
            "btn-enviar-comentario",
            "comentario-error",
        ):
            with self.subTest(elemento_id=elemento_id):
                self.assertContains(respuesta, f'id="{elemento_id}"', count=1)
