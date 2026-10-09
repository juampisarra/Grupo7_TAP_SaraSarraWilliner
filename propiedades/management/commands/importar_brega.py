"""Comando compatible con el uso previo; delega en la ingesta común."""

from .importar_propiedades import Command as ImportarPropiedadesCommand


class Command(ImportarPropiedadesCommand):
    help = "Extrae y guarda las propiedades de Brega mediante el flujo común"

    def add_arguments(self, parser):
        # Este alias no requiere el argumento posicional fuente.
        self.agregar_opciones_ubicacion(parser)

    def handle(self, *args, **options):
        options["fuente"] = "brega"
        return super().handle(*args, **options)
