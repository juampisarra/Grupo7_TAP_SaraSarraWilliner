from django.core.management.base import BaseCommand, CommandError

from propiedades.busqueda.cliente import BusquedaNoDisponible
from propiedades.busqueda.texto import buscar_ids, combinar_resultados
from propiedades.models import Propiedad


class Command(BaseCommand):
    help = "Prueba búsqueda textual y muestra relevancia; datos completos desde PostgreSQL"

    def add_arguments(self, parser):
        parser.add_argument("texto")
        parser.add_argument("--limite", type=int, default=10)

    def handle(self, *args, **options):
        if not 1 <= options["limite"] <= 100:
            raise CommandError("--limite debe estar entre 1 y 100")
        try:
            coincidencias = buscar_ids(options["texto"])
        except (BusquedaNoDisponible, ValueError) as error:
            raise CommandError(str(error)) from None
        propiedades = combinar_resultados(Propiedad.objects.all(), coincidencias)
        scores = dict(coincidencias)
        self.stdout.write(f"Resultados existentes en la base: {len(propiedades)}")
        for p in propiedades[:options["limite"]]:
            self.stdout.write(f"{p.pk} | score={scores[p.pk]:.3f} | {p.fuente} | {p.tipo} | {p.titulo or p.direccion}")
