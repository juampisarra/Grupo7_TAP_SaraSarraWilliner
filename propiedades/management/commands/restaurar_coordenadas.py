import json

from django.core.management.base import BaseCommand, CommandError
from propiedades.geocodificacion import restaurar_original
from propiedades.models import Propiedad


class Command(BaseCommand):
    help = "Restaura el punto original de un aviso enriquecido; vista previa por defecto."

    def add_arguments(self, parser):
        parser.add_argument("--id", type=int, required=True)
        parser.add_argument("--aplicar", action="store_true")

    def handle(self, *args, **options):
        try:
            propiedad = Propiedad.objects.get(pk=options["id"])
        except Propiedad.DoesNotExist as error:
            raise CommandError("La publicación no existe") from error
        if options["aplicar"]:
            self.stdout.write("Restaurada." if restaurar_original(propiedad.pk) else "Sin mejora restaurable.")
        else:
            self.stdout.write(json.dumps({"id": propiedad.pk, "mejora": propiedad.geocodificacion,
                                          "original": propiedad.coordenadas_fuente,
                                          "aplicado": False}, ensure_ascii=False))
