from django.core.management.base import BaseCommand, CommandError

from propiedades.busqueda.cliente import BusquedaNoDisponible
from propiedades.busqueda.indice import reconstruir_indice


class Command(BaseCommand):
    help = "Reconstruye el índice textual desde la base configurada, sin scraping"

    def add_arguments(self, parser):
        parser.add_argument("--permitir-vacio", action="store_true",
                            help="Permite activar una versión sin documentos si la base está vacía")

    def handle(self, *args, **options):
        try:
            version, cantidad = reconstruir_indice(permitir_vacio=options["permitir_vacio"])
        except BusquedaNoDisponible as error:
            raise CommandError(str(error)) from None
        self.stdout.write(self.style.SUCCESS(f"Índice activado: {version}. Documentos: {cantidad}"))
