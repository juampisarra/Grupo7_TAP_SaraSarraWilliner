import re
from urllib.parse import urlsplit

from django.conf import settings
from elasticsearch import Elasticsearch


class BusquedaNoDisponible(Exception):
    """Error público sin credenciales ni respuestas internas del proveedor."""


def nombre_indice():
    nombre = settings.ELASTICSEARCH_INDEX
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,99}", nombre):
        raise BusquedaNoDisponible("ELASTICSEARCH_INDEX debe ser un nombre en minúsculas, sin comodines")
    return nombre


def crear_cliente():
    url = settings.ELASTICSEARCH_URL
    clave = settings.ELASTICSEARCH_API_KEY
    if not url or not clave:
        raise BusquedaNoDisponible("Faltan ELASTICSEARCH_URL o ELASTICSEARCH_API_KEY")
    partes = urlsplit(url)
    if partes.scheme != "https" or not partes.hostname or partes.username or partes.password or partes.query or partes.fragment:
        raise BusquedaNoDisponible("ELASTICSEARCH_URL debe ser un endpoint HTTPS sin credenciales")
    if clave.startswith("ApiKey "):
        raise BusquedaNoDisponible("ELASTICSEARCH_API_KEY debe contener solo la clave encoded")
    return Elasticsearch(url, api_key=clave, request_timeout=20, max_retries=0, verify_certs=True)
