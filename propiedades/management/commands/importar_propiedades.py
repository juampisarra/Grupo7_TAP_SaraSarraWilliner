from dataclasses import asdict

from django.core.management.base import BaseCommand, CommandError

from propiedades.ingesta import importar_fuente
from propiedades.scraping.fuentes import FUENTES


# El workflow distingue un resultado parcial de errores fatales/argumentos inválidos.
SALIDA_PARCIAL = 3


class Command(BaseCommand):
    help = "Importa publicaciones mediante el flujo común de ingesta para una o todas las fuentes."

    def add_arguments(self, parser):
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
        fuentes_a_procesar = [options["fuente"]] if options["fuente"] else sorted(FUENTES)
        completar_ubicacion = options.get("completar_ubicacion", False)
        completadas = []
        fallidas = []

        if not fuentes_a_procesar:
            raise CommandError("No hay fuentes registradas para importar.")

        for nombre_fuente in fuentes_a_procesar:
            self.stdout.write(f"Iniciando fuente: {nombre_fuente}")
            try:
                adaptador = FUENTES[nombre_fuente]()
                resumen = importar_fuente(
                    adaptador, informar=self.stdout.write,
                    completar_ubicacion=completar_ubicacion,
                )
            except Exception as error:
                # Aislar la ejecución completa de una fuente, incluso su inicialización.
                # No capturar KeyboardInterrupt/SystemExit ni revertir escrituras previas.
                fallidas.append(nombre_fuente)
                self.stderr.write(self.style.ERROR(
                    f"Falló {nombre_fuente} ({type(error).__name__}): {error}"
                ))
                continue

            completadas.append(nombre_fuente)
            mensaje = " | ".join(
                f"{campo.replace('_', ' ').capitalize()}: {valor}"
                for campo, valor in asdict(resumen).items()
            )
            self.stdout.write(self.style.SUCCESS(f"Resumen {nombre_fuente}: {mensaje}"))

        self.stdout.write(
            f"Fuentes completadas: {', '.join(completadas) or 'ninguna'}. "
            f"Fuentes fallidas: {', '.join(fallidas) or 'ninguna'}."
        )
        if fallidas:
            raise CommandError(
                f"Ingesta {'parcial' if completadas else 'fallida'}. "
                f"Fuentes fallidas: {', '.join(fallidas)}. "
                "Los datos ya guardados se conservan.",
                returncode=SALIDA_PARCIAL if completadas else 1,
            )
