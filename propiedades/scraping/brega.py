import time
import re

import logging
import math
import requests

from .contratos import PublicacionNormalizada
from .tokko import (
    leer_detalles as leer_detalles_tokko,
    leer_listado,
    recorrer_paginas,
)


URL_BASE = "https://www.bregainmobiliaria.ar"
URLS_BUSQUEDA= {
        "venta": f"{URL_BASE}/Venta",
        "alquiler": f"{URL_BASE}/Alquiler",
        }

CABECERAS = {
    "User-Agent": "Grupo7-TAP/0.1 (proyecto academico)",
}

logger = logging.getLogger(__name__)


def leer_ubicacion_mapa(documento):
    """Lee el círculo publicado en la ficha, nunca el centro/zoom del mapa.

    No ejecuta JavaScript ni calcula distancias. El radio es un dato de la fuente.
    Si el formato no se reconoce, no inventa coordenadas.
    """
    mapa = documento.select_one("#ficha_mapa")
    if mapa is None:
        return {}
    numero = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
    patron = (
        rf"\bL\.circle\s*\(\s*\[\s*({numero})\s*,\s*({numero})\s*\]"
        rf"\s*,\s*({numero})\s*,\s*\{{"
    )
    circulos = {
        tuple(float(valor) for valor in coincidencia)
        for script in mapa.select("script")
        for coincidencia in re.findall(patron, script.get_text())
    }
    if not circulos:
        return {}
    if len(circulos) != 1:
        logger.warning("Ficha Brega con varios círculos distintos; ubicación no extraída")
        return {}
    latitud, longitud, radio = circulos.pop()
    if not (
        all(math.isfinite(valor) for valor in (latitud, longitud, radio))
        and -90 <= latitud <= 90 and -180 <= longitud <= 180 and radio > 0
    ):
        logger.warning("Ficha Brega con coordenadas o radio inválidos")
        return {}
    return {
        "latitud": latitud, "longitud": longitud,
        "ubicacion_aproximada": True, "radio_ubicacion_m": radio,
    }

def extraer_detalles(url_original):
    respuesta = requests.get(
        url_original,
        headers=CABECERAS,
        timeout= 15,
    )
    respuesta.raise_for_status()
    return leer_detalles(respuesta.text)


def leer_detalles(html):
    return leer_detalles_tokko(
        html,
        extraer_ubicacion=leer_ubicacion_mapa,
    )


def extraer_dormitorios(url_original):
    """Compatibilidad para llamadas anteriores; la ingesta usa la ficha completa."""
    return extraer_detalles(url_original).dormitorios

def extraer_pagina(numero_pagina, operacion="alquiler"):
    if operacion not in URLS_BUSQUEDA:
        raise ValueError(f"Operacion desconocida: {operacion}")
    url_busqueda = URLS_BUSQUEDA[operacion]
    parametros = (
        {"p": numero_pagina}
        if numero_pagina > 1
        else None
    )
    respuesta = requests.get(
        url_busqueda,
        params=parametros,
        headers=CABECERAS,
        timeout= 15,
    )

    #Mira el codigo de respuesta HTTP (200,404,500,etc).
    respuesta.raise_for_status()

    return leer_listado(respuesta.text, URL_BASE)

def extraer_primera_pagina(operacion="alquiler"):
    return extraer_pagina(1,operacion)

def extraer_todas_las_paginas(operacion="alquiler", max_paginas=50):
    return recorrer_paginas(
        extraer_pagina,
        operacion,
        max_paginas,
        time.sleep,
    )

class AdaptadorBrega:
    """Traduce la extracción al contrato común, sin persistir datos."""

    nombre = "Brega"
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
                # Los selectores actuales no extraen una ciudad explícita.
            )
            for dato in extraer_todas_las_paginas(operacion)
        ]

    def extraer_dormitorios(self, url_original):
        return extraer_dormitorios(url_original)

    def extraer_detalles(self, url_original):
        return extraer_detalles(url_original)


if __name__ == "__main__":
       for operacion in URLS_BUSQUEDA:
        propiedades = extraer_todas_las_paginas(operacion)

        print(
            f"{operacion.capitalize()}: "
            f"{len(propiedades)} propiedades encontradas"
        )

        for propiedad in propiedades[:3]:
            print(propiedad)
