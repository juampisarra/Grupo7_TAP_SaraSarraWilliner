import logging
import math
import re
import time
from urllib.parse import parse_qs, urlsplit

import requests

from .contratos import PublicacionNormalizada
from .tokko import (
    leer_detalles as leer_detalles_tokko,
    leer_listado,
    recorrer_paginas,
)

URL_BASE = "https://www.avantix.ar"

URLS_BUSQUEDA = {
    "venta": f"{URL_BASE}/Venta",
    "alquiler": f"{URL_BASE}/Alquiler",
}

CABECERAS = {
    "User-Agent": "Grupo7-TAP/0.1 (proyecto academico)",
}

logger = logging.getLogger(__name__)


def leer_ubicacion_mapa(documento):
    """Lee el punto de Avantix y lo clasifica exacto por decisión del equipo."""
    mapa = documento.select_one("#ficha_mapa")
    if mapa is None:
        return {}

    numero = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
    coordenadas = set()

    for iframe in mapa.select("iframe[src]"):
        try:
            url = urlsplit(iframe.get("src"))
        except ValueError:
            logger.warning("Ficha Avantix con URL de mapa inválida")
            return {}
        hostname = (url.hostname or "").casefold()
        dominios_google = ("google.com", "google.com.ar")
        if not any(
            hostname == dominio or hostname.endswith(f".{dominio}")
            for dominio in dominios_google
        ):
            continue
        if url.path != "/maps" and not url.path.startswith("/maps/"):
            continue

        for valor in parse_qs(url.query).get("q", []):
            coincidencia = re.fullmatch(
                rf"\s*({numero})\s*,\s*({numero})\s*",
                valor,
            )
            if coincidencia is None:
                continue

            latitud, longitud = (
                float(numero_encontrado)
                for numero_encontrado in coincidencia.groups()
            )
            if not (
                math.isfinite(latitud)
                and math.isfinite(longitud)
                and -90 <= latitud <= 90
                and -180 <= longitud <= 180
            ):
                logger.warning("Ficha Avantix con coordenadas inválidas")
                return {}
            coordenadas.add((latitud, longitud))

    if not coordenadas:
        return {}
    if len(coordenadas) != 1:
        logger.warning("Ficha Avantix con varios puntos distintos; ubicación no extraída")
        return {}

    latitud, longitud = coordenadas.pop()
    # Avantix no publica radio; el equipo decidió tratar el marcador como exacto.
    return {
        "latitud": latitud,
        "longitud": longitud,
        "ubicacion_aproximada": False,
        "radio_ubicacion_m": None,
    }


def leer_detalles(html):
    """Lee los campos Tokko y el punto que Avantix publica como ubicación."""
    return leer_detalles_tokko(
        html,
        extraer_ubicacion=leer_ubicacion_mapa,
        url_base=URL_BASE,
    )


def extraer_detalles(url_original):
    respuesta = requests.get(
        url_original,
        headers=CABECERAS,
        timeout=15,
    )
    respuesta.raise_for_status()
    return leer_detalles(respuesta.text)


def extraer_pagina(numero_pagina, operacion="alquiler"):
    if operacion not in URLS_BUSQUEDA:
        raise ValueError(f"Operacion desconocida: {operacion}")

    parametros = (
        {"p": numero_pagina}
        if numero_pagina > 1
        else None
    )

    respuesta = requests.get(
        URLS_BUSQUEDA[operacion],
        params=parametros,
        headers=CABECERAS,
        timeout=15,
    )

    respuesta.raise_for_status()

    return leer_listado(respuesta.text, URL_BASE)


def extraer_primera_pagina(operacion="alquiler"):
    return extraer_pagina(1, operacion)


def extraer_todas_las_paginas(operacion="alquiler", max_paginas=50):
    return recorrer_paginas(
        extraer_pagina,
        operacion,
        max_paginas,
        time.sleep,
    )


class AdaptadorAvantix:
    nombre = "Avantix"
    operaciones = ("venta", "alquiler")

    def extraer(self, operacion):
        return [
            PublicacionNormalizada(
                identificador_fuente=dato["identificador_fuente"],
                url_original=dato["url_original"],
                direccion=dato["direccion"] or "",
                tipo=dato["tipo"],
                precio=dato["precio"],
                moneda=dato["moneda"],
                en_venta=dato["en_venta"],
                en_alquiler=dato["en_alquiler"],
            )
            for dato in extraer_todas_las_paginas(operacion)
        ]

    def extraer_detalles(self, url_original):
        return extraer_detalles(url_original)
