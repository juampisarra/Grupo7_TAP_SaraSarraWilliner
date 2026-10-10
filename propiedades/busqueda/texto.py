"""Consulta BM25 y lectura de todos los IDs por ranking, sin truncar a 10.000."""

import logging

from elasticsearch import ApiError
from elastic_transport import TransportError

from .cliente import BusquedaNoDisponible, crear_cliente, nombre_indice

logger = logging.getLogger(__name__)


def consulta_textual(texto):
    return {"bool": {
        "must": [{"match": {"texto": {
            "query": texto, "minimum_should_match": "2<75%", "zero_terms_query": "none",
        }}}],
        "should": [{"multi_match": {
            "query": texto,
            "fields": ["titulo^3", "caracteristicas^2", "tipo^2", "descripcion", "direccion", "zona", "ciudad", "provincia"],
        }}],
    }}


def buscar_ids(texto):
    texto = texto.strip()
    if not texto or len(texto) > 300:
        raise ValueError("El texto debe tener entre 1 y 300 caracteres")
    alias = nombre_indice()
    try:
        with crear_cliente() as cliente:
            pit = cliente.open_point_in_time(index=alias, keep_alive="1m")["id"]
            resultados = []
            despues = None
            try:
                while True:
                    respuesta = cliente.search(
                        pit={"id": pit, "keep_alive": "1m"}, size=100,
                        query=consulta_textual(texto),
                        sort=[{"_score": "desc"}, {"propiedad_id": "asc"}],
                        search_after=despues, source=False, track_total_hits=False,
                        allow_partial_search_results=False,
                    )
                    pit = respuesta.get("pit_id", pit)
                    if respuesta.get("timed_out") or respuesta.get("_shards", {}).get("failed", 0):
                        raise BusquedaNoDisponible("La búsqueda no se completó; intentá nuevamente")
                    lote = respuesta["hits"]["hits"]
                    if not lote:
                        break
                    resultados.extend((int(hit["_id"]), hit["_score"]) for hit in lote)
                    despues = lote[-1]["sort"]
                return resultados
            finally:
                try:
                    cliente.close_point_in_time(id=pit)
                except (ApiError, TransportError):
                    # El PIT expira al minuto; no ocultar el resultado/error original.
                    logger.warning("No se pudo cerrar el contexto de búsqueda; expirará automáticamente")
    except (ApiError, TransportError):
        raise BusquedaNoDisponible("La búsqueda textual no está disponible. Revisar conexión, credenciales e índice") from None


def combinar_resultados(queryset, coincidencias):
    # Filtros estructurados/espaciales ya aplicados por PostgreSQL; preservar ranking.
    objetos = queryset.in_bulk([pk for pk, _ in coincidencias])
    return [objetos[pk] for pk, _ in coincidencias if pk in objetos]
