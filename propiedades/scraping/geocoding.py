"""Geocodificación con localidad explícita; no realiza filtros espaciales."""

import logging
import re

from geopy.exc import GeocoderServiceError
from geopy.extra.rate_limiter import RateLimiter
from geopy.geocoders import Nominatim

logger = logging.getLogger(__name__)
geolocalizador = Nominatim(user_agent="Grupo7-TAP/0.1 (proyecto academico)")
def _consultar_servicio(metodo, *args, **kwargs):
    return getattr(geolocalizador, metodo)(*args, **kwargs)


# Ambas operaciones comparten el ritmo para no duplicar la tasa de solicitudes.
consultar_servicio = RateLimiter(
    _consultar_servicio, min_delay_seconds=1.5,
    max_retries=0, swallow_exceptions=False,
)


def consultar_direccion(*args, **kwargs):
    return consultar_servicio("geocode", *args, **kwargs)


def consultar_localidad(latitud, longitud):
    return consultar_servicio(
        "reverse", (latitud, longitud), exactly_one=True,
        addressdetails=True, language="es", timeout=10,
    )


def obtener_coordenadas(direccion, ciudad=None, provincia=None):
    """Sin ciudad explícita no se consulta ni se supone Rafaela.

    Los fallos del proveedor se registran y retornan None/None.
    No se infieren ciudades por nombres de calles o pueblos vecinos.
    """
    if not direccion or not ciudad or not ciudad.strip():
        return None, None

    dir_limpia = direccion.strip()
    reemplazos = {
        "Bv.": "Bulevar", "Av.": "Avenida", "Bv ": "Bulevar ",
        "Av ": "Avenida ", "Almte.": "Almirante", "Almte ": "Almirante ",
        "Alte.": "Almirante", "Gral.": "General", "Gral ": "General ",
        "1ra": "Primera", "N°": "", "Nº": "",
    }
    for abreviatura, completo in reemplazos.items():
        dir_limpia = dir_limpia.replace(abreviatura, completo)
    dir_limpia = re.split(
        r"(?i)\b(piso|dpto|depto|pb|p\.a\.|local|lote|esq\.?|esquina|s/n|s/nº)\b|-|,|\sy\s",
        dir_limpia,
    )[0].strip()
    if not dir_limpia:
        return None, None

    texto_busqueda = ", ".join(
        parte.strip() for parte in (dir_limpia, ciudad, provincia, "Argentina")
        if parte and parte.strip()
    )
    try:
        ubicacion = consultar_direccion(texto_busqueda, timeout=10)
    except GeocoderServiceError as error:
        logger.warning("No se pudo geocodificar %s: %s", texto_busqueda, error)
        return None, None
    if ubicacion is None:
        return None, None
    return ubicacion.latitude, ubicacion.longitude
