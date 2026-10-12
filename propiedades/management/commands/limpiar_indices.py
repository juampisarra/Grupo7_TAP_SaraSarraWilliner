from django.core.management.base import BaseCommand, CommandError

from propiedades.busqueda.cliente import BusquedaNoDisponible
from propiedades.busqueda.mantenimiento import limpiar_indices


class Command(BaseCommand):
    help = "Muestra índices antiguos a eliminar; conserva el activo y su versión anterior"

    def add_arguments(self, parser):
        parser.add_argument("--aplicar", action="store_true", help="Ejecuta los borrados mostrados; por defecto solo vista previa")

    def handle(self, *args, **options):
        try:
            _, eliminados = limpiar_indices(aplicar=options["aplicar"], informar=self.stdout.write)
        except BusquedaNoDisponible as error:
            raise CommandError(str(error)) from None
        if options["aplicar"]:
            self.stdout.write(self.style.SUCCESS(f"Índices eliminados: {len(eliminados)}"))
