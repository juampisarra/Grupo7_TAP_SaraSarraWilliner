import json

from django.core.management.base import BaseCommand, CommandError
from propiedades.coordenadas import diagnosticar


class Command(BaseCommand):
    help = "Diagnostica puntos repetidos y métodos aproximados; solo lectura, sin HTTP."

    def add_arguments(self, parser):
        parser.add_argument("--fuente")
        parser.add_argument("--umbral", type=int, default=5)

    def handle(self, *args, **options):
        try:
            informe = diagnosticar(fuente=options["fuente"], umbral=options["umbral"])
        except ValueError as error:
            raise CommandError(str(error)) from error
        self.stdout.write(json.dumps(informe, ensure_ascii=False, indent=2))
