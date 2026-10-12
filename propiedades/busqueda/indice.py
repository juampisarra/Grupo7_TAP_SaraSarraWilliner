"""Reconstrucción completa desde la base, sin scraping ni borrados automáticos."""

from uuid import uuid4

from django.utils import timezone
from django.db.models import Q
from elasticsearch import ApiError, helpers
from elastic_transport import TransportError

from propiedades.models import Propiedad
from .cliente import BusquedaNoDisponible, crear_cliente, nombre_indice


CAMPOS_TEXTO = ("titulo", "descripcion", "caracteristicas", "direccion", "zona", "ciudad", "provincia", "tipo")
MAPPING = {
    "dynamic": "strict",
    "properties": {
        "propiedad_id": {"type": "long"},
        "fuente": {"type": "keyword"},
        "identificador_fuente": {"type": "keyword"},
        "texto": {"type": "text", "analyzer": "spanish", "similarity": "BM25"},
        **{campo: {"type": "text", "analyzer": "spanish", "copy_to": "texto"}
           for campo in CAMPOS_TEXTO},
    },
}


def documento(propiedad):
    return {
        "propiedad_id": propiedad.pk,
        "fuente": propiedad.fuente,
        "identificador_fuente": propiedad.identificador_fuente,
        **{campo: getattr(propiedad, campo) for campo in CAMPOS_TEXTO},
    }


def reconstruir_indice(*, permitir_vacio=False):
    alias = nombre_indice()
    version = f"{alias}-{timezone.now():%Y%m%d%H%M%S}-{uuid4().hex[:8]}"
    try:
        with crear_cliente() as cliente:
            if cliente.indices.exists(index=alias) and not cliente.indices.exists_alias(name=alias):
                raise BusquedaNoDisponible("El nombre configurado ya corresponde a un índice físico; usar un alias libre")
            propiedades = Propiedad.objects.filter(Q(en_venta=True) | Q(en_alquiler=True))
            esperadas = propiedades.count()
            if not esperadas and not permitir_vacio and not Propiedad.objects.exists():
                raise BusquedaNoDisponible("La base no contiene propiedades; revisar DB_ENGINE. Para vaciar el índice explícitamente usar --permitir-vacio")
            cliente.indices.create(index=version, mappings=MAPPING)
            correctas = 0

            def acciones():
                for propiedad in propiedades.order_by("pk").iterator(chunk_size=200):
                    yield {"_index": version, "_id": str(propiedad.pk), "_source": documento(propiedad)}

            for ok, _ in helpers.streaming_bulk(cliente, acciones(), chunk_size=200,
                    raise_on_error=False, raise_on_exception=True, max_retries=0):
                if not ok:
                    raise BusquedaNoDisponible("Falló un documento; se conserva el alias anterior. Repetir la reconstrucción")
                correctas += 1
            cliente.indices.refresh(index=version)
            if correctas != esperadas or cliente.count(index=version)["count"] != correctas:
                raise BusquedaNoDisponible("El conteo del índice no coincide; se conserva el alias anterior")
            # Ambas acciones se procesan atómicamente. No se eliminan índices físicos.
            anteriores = cliente.indices.get_alias(name=alias) if cliente.indices.exists_alias(name=alias) else {}
            # Conservar evidencia de la versión anterior que atendía búsquedas.
            # La limpieza no adivina qué reconstrucciones antiguas fueron exitosas.
            marcado = cliente.indices.put_mapping(index=version, meta={"grupo7": {
                "alias": alias, "completo": True, "anteriores": list(anteriores),
                "documentos": correctas,
            }})
            if not marcado.get("acknowledged", False):
                raise BusquedaNoDisponible("No se pudo registrar la versión anterior; se conserva el alias")
            acciones_alias = [
                {"remove": {"index": anterior, "alias": alias, "must_exist": True}}
                for anterior in anteriores
            ]
            acciones_alias.append({"add": {"index": version, "alias": alias, "is_write_index": True}})
            respuesta = cliente.indices.update_aliases(actions=acciones_alias)
            if respuesta.get("errors") or not respuesta.get("acknowledged", False):
                raise BusquedaNoDisponible("No se pudo activar la versión nueva; revisar el alias antes de repetir")
            return version, correctas
    except (ApiError, TransportError):
        raise BusquedaNoDisponible(
            "Elasticsearch no pudo reconstruir el índice. Revisar conexión, permisos y repetir; no se borraron índices"
        ) from None
