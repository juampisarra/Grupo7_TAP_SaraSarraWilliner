from dataclasses import asdict

from django.core.management.base import BaseCommand

from propiedades.ingesta import importar_fuente
from propiedades.scraping.fuentes import FUENTES


class Command(BaseCommand):
    help = "Importa publicaciones mediante el flujo común de ingesta para una o todas las fuentes."

    def add_arguments(self, parser):
        # Hacer que 'fuente' sea opcional con nargs="?"
        parser.add_argument(
            "fuente",
            nargs="?",
            choices=sorted(FUENTES),
            help="Fuente específica a importar. Si se omite, se importan todas las fuentes registradas.",
        )
        self.agregar_opciones_ubicacion(parser)

    def agregar_opciones_ubicacion(self, parser):
        parser.add_argument(
            "--completar-ubicacion", action="store_true",
            help="Completa ciudad/provincia faltantes con Nominatim y caché persistente",
        )

    def handle(self, *args, **options):
        # Si el usuario pasó una fuente, procesamos esa sola. Si no, procesamos todas.
        fuentes_a_procesar = [options["fuente"]] if options["fuente"] else sorted(FUENTES)
        
        completar_ubicacion = options.get("completar_ubicacion", False)

        for nombre_fuente in fuentes_a_procesar:
            if not options["fuente"]:
                self.stdout.write(self.style.WARNING(f"\n=== Iniciando ingesta general: fuente {nombre_fuente} ==="))
                
            adaptador = FUENTES[nombre_fuente]()
            resumen = importar_fuente(
                adaptador, informar=self.stdout.write,
                completar_ubicacion=completar_ubicacion,
            )
            
            mensaje = " | ".join(
                f"{campo.replace('_', ' ').capitalize()}: {valor}"
                for campo, valor in asdict(resumen).items()
            )
            self.stdout.write(self.style.SUCCESS(f"Resumen {nombre_fuente}: {mensaje}"))
