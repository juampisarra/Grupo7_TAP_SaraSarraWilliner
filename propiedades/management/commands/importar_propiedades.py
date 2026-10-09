from dataclasses import asdict

from django.core.management.base import BaseCommand

from propiedades.ingesta import importar_fuente
from propiedades.scraping.fuentes import FUENTES


class Command(BaseCommand):
    help = "Importa publicaciones mediante el flujo común de ingesta"

    def add_arguments(self, parser):
        parser.add_argument("fuente", choices=sorted(FUENTES))
        self.agregar_opciones_ubicacion(parser)

    def agregar_opciones_ubicacion(self, parser):
        parser.add_argument(
            "--completar-ubicacion", action="store_true",
            help="Completa ciudad/provincia faltantes con Nominatim y caché persistente",
        )

    def handle(self, *args, **options):
        adaptador = FUENTES[options["fuente"]]()
        resumen = importar_fuente(
            adaptador, informar=self.stdout.write,
            completar_ubicacion=options.get("completar_ubicacion", False),
        )
        mensaje = " | ".join(
            f"{campo.replace('_', ' ').capitalize()}: {valor}"
            for campo, valor in asdict(resumen).items()
        )
        self.stdout.write(self.style.SUCCESS(mensaje))
