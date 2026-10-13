import json

from django.core.management.base import BaseCommand, CommandError
from propiedades.coordenadas import diagnosticar
from propiedades.geocodificacion import aplicar_resultado, resolver_direccion
from propiedades.models import Propiedad


class Command(BaseCommand):
    help = "Vista previa de candidatos; --consultar guarda caché; --aplicar corrige puntos validados."

    def add_arguments(self, parser):
        parser.add_argument("--fuente")
        parser.add_argument("--umbral", type=int, default=5)
        parser.add_argument("--limite", type=int, default=10)
        parser.add_argument("--desde-id", type=int, default=0)
        grupo = parser.add_mutually_exclusive_group()
        grupo.add_argument("--consultar", action="store_true")
        grupo.add_argument("--aplicar", action="store_true")

    def handle(self, *args, **options):
        if not 1 <= options["limite"] <= 100:
            raise CommandError("El límite debe estar entre 1 y 100")
        if options["desde_id"] < 0:
            raise CommandError("desde-id debe ser cero o positivo")
        try:
            informe = diagnosticar(fuente=options["fuente"], umbral=options["umbral"])
        except ValueError as error:
            raise CommandError(str(error)) from error
        candidatos = [c for c in informe["candidatos"] if c["elegible"] and not c["ya_enriquecida"]
                      and c["id"] > options["desde_id"]][:options["limite"]]
        consultar = options["consultar"] or options["aplicar"]
        self.stdout.write("Política Nominatim: https://operations.osmfoundation.org/policies/nominatim/\n"
                          "Un proceso/máquina, caché y hasta 4 solicitudes/minuto. No ejecutar junto a la ingesta.")
        for candidato in candidatos:
            salida = {**candidato, "estado": "vista_previa", "aplicado": False}
            if consultar:
                propiedad = Propiedad.objects.get(pk=candidato["id"])
                cache = resolver_direccion(propiedad)
                salida["estado"] = cache.estado if cache else "direccion_incompleta"
                salida["resultado"] = cache.resultado if cache else {}
                if options["aplicar"]:
                    salida["aplicado"] = aplicar_resultado(propiedad, cache)
            self.stdout.write(json.dumps(salida, ensure_ascii=False))
        self.stdout.write(f"Candidatos procesados: {len(candidatos)}. "
                          + ("Sin HTTP ni escrituras." if not consultar else "Consultar no modifica publicaciones; aplicar sí."))
