"""Geocodificación con localidad explícita; no realiza filtros espaciales."""

import logging
import re
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from geopy.exc import GeocoderServiceError
from geopy.extra.rate_limiter import RateLimiter
from geopy.geocoders import Nominatim

logger = logging.getLogger(__name__)
geolocalizador = Nominatim(user_agent=settings.NOMINATIM_USER_AGENT,
                         domain=settings.NOMINATIM_DOMAIN, scheme="https")
def _consultar_servicio(metodo, *args, **kwargs):
    return getattr(geolocalizador, metodo)(*args, **kwargs)


# Ambas operaciones comparten el ritmo para no duplicar la tasa de solicitudes.
consultar_servicio = RateLimiter(
    # Tareas periódicas en el servidor público: máximo cuatro consultas/minuto.
    _consultar_servicio, min_delay_seconds=15.1,
    max_retries=0, swallow_exceptions=False, error_wait_seconds=15.1,
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
    # También cachear el respaldo experimental usado por la ingesta. No comparte
    # aceptación ni claves con el nuevo validador estricto de alturas.
    from propiedades.coordenadas import huella, par_valido
    from propiedades.enriquecimiento import normalizar_nombre
    from propiedades.models import ConsultaDireccion
    consulta = {"version": "experimental-v1", "proveedor": settings.NOMINATIM_DOMAIN,
                "texto": normalizar_nombre(texto_busqueda)}
    clave = huella(consulta)
    cache = ConsultaDireccion.objects.filter(clave=clave).first()
    vigencia = timedelta(hours=24) if cache and cache.estado == "error" else timedelta(days=30)
    if cache and cache.consultada_en > timezone.now() - vigencia:
        return (cache.resultado["latitud"], cache.resultado["longitud"]) if cache.estado == "resuelto" else (None, None)
    try:
        ubicacion = consultar_direccion(texto_busqueda, timeout=10)
    except GeocoderServiceError as error:
        logger.warning("No se pudo geocodificar %s: %s", texto_busqueda, error)
        estado, resultado = "error", {}
    else:
        if ubicacion is not None and par_valido(ubicacion.latitude, ubicacion.longitude):
            estado, resultado = "resuelto", {"latitud": ubicacion.latitude, "longitud": ubicacion.longitude}
        else:
            estado, resultado = "sin_resultado", {}
    ConsultaDireccion.objects.update_or_create(
        clave=clave, defaults={"consulta": consulta, "estado": estado, "resultado": resultado})
    return (resultado["latitud"], resultado["longitud"]) if estado == "resuelto" else (None, None)
