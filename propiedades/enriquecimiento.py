"""Enriquecimiento opcional de nombres administrativos, separado del scraping."""

import logging
import math
from datetime import timedelta
import unicodedata

from django.utils import timezone
from geopy.exc import GeocoderServiceError

from propiedades.models import ConsultaLocalidad
from propiedades.scraping.geocoding import consultar_localidad

logger = logging.getLogger(__name__)
ORIGEN_INVERSA = "nominatim_inversa"


def normalizar_nombre(nombre):
    nombre = unicodedata.normalize("NFKD", nombre.casefold())
    return " ".join("".join(c for c in nombre if not unicodedata.combining(c)).split())


def leer_localidad(resultado):
    if resultado is None:
        return "sin_resultado", "", ""
    direccion = resultado.raw.get("address", {})
    if not isinstance(direccion, dict) or direccion.get("country_code", "").lower() != "ar":
        return "ambiguo", "", ""
    ciudades = {
        valor.strip() for campo in ("city", "town", "village")
        if isinstance(valor := direccion.get(campo), str) and valor.strip()
    }
    if len({normalizar_nombre(nombre) for nombre in ciudades}) > 1:
        return "ambiguo", "", ""
    ciudad = sorted(ciudades)[0] if ciudades else ""
    provincia = direccion.get("state", "")
    if not isinstance(provincia, str):
        return "ambiguo", "", ""
    provincia = provincia.strip()
    if len(ciudad) > 150 or len(provincia) > 150:
        return "ambiguo", "", ""
    # Nunca interpretar suburb/neighbourhood/county como ciudad o provincia.
    return ("resuelto" if ciudad or provincia else "sin_resultado"), ciudad, provincia


def buscar_localidad(latitud, longitud):
    cache = ConsultaLocalidad.objects.filter(latitud=latitud, longitud=longitud).first()
    if cache and (
        cache.estado != "error"
        or cache.consultada_en > timezone.now() - timedelta(hours=24)
    ):
        return cache
    try:
        estado, ciudad, provincia = leer_localidad(consultar_localidad(latitud, longitud))
    except (GeocoderServiceError, ValueError, TypeError, AttributeError) as error:
        logger.warning("No se pudo resolver la localidad por coordenadas: %s", error)
        estado, ciudad, provincia = "error", "", ""
    cache, _ = ConsultaLocalidad.objects.update_or_create(
        latitud=latitud, longitud=longitud,
        defaults={"estado": estado, "ciudad": ciudad, "provincia": provincia},
    )
    return cache


def completar_localidad(valores, existente, habilitado=False):
    """Conserva valores explícitos y elimina inferencias de coordenadas anteriores.

    No modifica latitud/longitud ni su precisión. Retorna si completó algún campo.
    """
    for campo in ("ciudad", "provincia"):
        if valores.get(campo):
            valores[f"{campo}_origen"] = "fuente"
    latitud = valores.get("latitud", getattr(existente, "latitud", None))
    longitud = valores.get("longitud", getattr(existente, "longitud", None))
    cambio = existente is not None and (
        latitud != existente.latitud or longitud != existente.longitud
    )
    if cambio:
        for campo in ("ciudad", "provincia"):
            if (
                getattr(existente, f"{campo}_origen") == ORIGEN_INVERSA
                and not valores.get(campo)
            ):
                valores[campo] = ""
                valores[f"{campo}_origen"] = ""
    actuales = {
        campo: valores.get(campo, getattr(existente, campo, ""))
        for campo in ("ciudad", "provincia")
    }
    if not habilitado or all(actuales.values()):
        return False
    if (
        latitud is None or longitud is None
        or not math.isfinite(latitud) or not math.isfinite(longitud)
        or not -90 <= latitud <= 90 or not -180 <= longitud <= 180
    ):
        return False
    resultado = buscar_localidad(latitud, longitud)
    if resultado.estado != "resuelto":
        return False
    # Si contradice datos conocidos, no completar parcialmente un lugar distinto.
    for campo in ("ciudad", "provincia"):
        propuesto = getattr(resultado, campo)
        if actuales[campo] and propuesto and normalizar_nombre(actuales[campo]) != normalizar_nombre(propuesto):
            logger.warning("Localidad inversa incompatible con %s guardada; enriquecimiento omitido", campo)
            return False
    completo = False
    for campo in ("ciudad", "provincia"):
        propuesto = getattr(resultado, campo)
        if not actuales[campo] and propuesto:
            valores[campo] = propuesto
            valores[f"{campo}_origen"] = ORIGEN_INVERSA
            completo = True
    return completo
