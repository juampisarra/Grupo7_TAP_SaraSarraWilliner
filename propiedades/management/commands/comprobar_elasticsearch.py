from django.core.management.base import BaseCommand, CommandError
from elasticsearch import ApiError
from elastic_transport import TransportError

from propiedades.busqueda.cliente import crear_cliente, BusquedaNoDisponible


class Command(BaseCommand):
    help = "Comprueba autenticación con Elasticsearch sin mostrar credenciales"

    def handle(self, *args, **options):
        try:
            with crear_cliente() as cliente:
                info = cliente.info()
        except (ApiError, TransportError, BusquedaNoDisponible):
            raise CommandError("No se pudo conectar a Elasticsearch; revisar variables, red y permisos") from None
        self.stdout.write(self.style.SUCCESS(f"Conexión correcta. Elasticsearch {info['version']['number']}"))
