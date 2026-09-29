import time
import requests

from django.core.management.base import BaseCommand

from propiedades.models import Propiedad
from propiedades.scraping.brega import (
    extraer_dormitorios,
    extraer_todas_las_paginas,
    )


class Command(BaseCommand):
    help = "Extrae y guarda las propiedades de Brega"

    def handle(self, *args, **options):
        datos_por_identificador = {}
        omitidas = 0

        for operacion in ("venta", "alquiler"):
            datos = extraer_todas_las_paginas(operacion)

            for dato in datos:
                identificador = dato["identificador_fuente"]
                url_original = dato["url_original"]

                if not identificador or not url_original:
                    omitidas += 1
                    continue

                propiedad = datos_por_identificador.setdefault(
                    identificador,
                    {
                        "direccion": dato["direccion"] or "",
                        "tipo": dato["tipo"],
                        "url_original": url_original,
                        "en_venta": False,
                        "precio_venta": None,
                        "moneda_venta": "",
                        "en_alquiler": False,
                        "precio_alquiler": None,
                        "moneda_alquiler": "",
                    },
                )

                if dato["direccion"]:
                    propiedad["direccion"] = dato["direccion"]

                if dato["tipo"]:
                    propiedad["tipo"] = dato["tipo"]

                propiedad["en_venta"] = (
                    propiedad["en_venta"]
                    or dato["en_venta"]
                    or operacion == "venta"
                )
                propiedad["en_alquiler"] = (
                    propiedad["en_alquiler"]
                    or dato["en_alquiler"]
                    or operacion == "alquiler"
                )

                if operacion == "venta":
                    propiedad["precio_venta"] = dato["precio"]
                    propiedad["moneda_venta"] = dato["moneda"]
                else:
                    propiedad["precio_alquiler"] = dato["precio"]
                    propiedad["moneda_alquiler"] = dato["moneda"]

        creadas = 0
        actualizadas = 0
        detalles_solicitados = 0
        detalles_verificados = 0
        detalles_reutilizados = 0
        errores_detalle = 0

        for identificador, valores in datos_por_identificador.items():
            propiedad_existente = Propiedad.objects.filter(
                fuente = "Brega",
                identificador_fuente = identificador,
            ).first()

            if (
                propiedad_existente
                and propiedad_existente.dormitorios_verificados
            ):
                detalles_reutilizados +=1
            else:
                detalles_solicitados +=1

                try:
                    dormitorios = extraer_dormitorios(
                        valores["url_original"]
                    )

                except (requests.RequestException, ValueError) as error:
                    errores_detalle +=1
                    self.stderr.write(
                        self.style.WARNING(
                            f"No se pudieron obtener los dormitorios "
                            f"de {identificador}: {error}"
                        )
                    )
                else:
                    valores["dormitorios"] = dormitorios
                    valores["dormitorios_verificados"] = True
                    detalles_verificados +=1
                finally:
                    time.sleep(0.5)

            _, fue_creada = Propiedad.objects.update_or_create(
                fuente = "Brega",
                identificador_fuente = identificador,
                defaults=valores,
            )

            if fue_creada:
                creadas +=1
            else:
                actualizadas +=1

        self.stdout.write(
                self.style.SUCCESS(
                    f"Procesadas: {len(datos_por_identificador)} | "
                    f"Creadas: {creadas} | "
                    f"Actualizadas: {actualizadas} | "
                    f"Omitidas: {omitidas} | "
                    f"Detalles solicitados: {detalles_solicitados} | "
                    f"Detalles verificados: {detalles_verificados} | "
                    f"Detalles reutilizados: {detalles_reutilizados} | "
                    f"Errores de detalle: {errores_detalle}"
    )
)