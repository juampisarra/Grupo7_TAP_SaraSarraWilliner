from urllib.parse import urljoin
import time
import re
import unicodedata
import logging
import math
import requests
from bs4 import BeautifulSoup
from .contratos import DetallesPropiedad, PublicacionNormalizada
from .normalizacion import (
        normalizar_precio,
        normalizar_tipo,
        normalizar_operaciones
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


def _etiqueta(texto):
    texto = unicodedata.normalize("NFKD", texto.casefold())
    return " ".join("".join(c for c in texto if not unicodedata.combining(c)).split())


def leer_detalles(html):
    """Selectores verificados en fichas Brega; no infiere datos de la prosa."""
    documento = BeautifulSoup(html, "html.parser")
    if not documento.select_one(".ficha_detalle_item, #lista_informacion_basica, #prop-desc"):
        raise ValueError("No se reconoció la estructura de la ficha Brega")
    valores = {}
    for detalle in documento.select(".ficha_detalle_item"):
        etiqueta = detalle.select_one("b")
        if etiqueta:
            textos = list(detalle.stripped_strings)
            if len(textos) > 1:
                valores[_etiqueta(etiqueta.get_text())] = " ".join(textos[1:])
    for item in documento.select("#lista_informacion_basica li"):
        nombre, separador, valor = item.get_text(" ", strip=True).partition(":")
        if separador:
            valores[_etiqueta(nombre)] = valor.strip()

    def cantidad(nombre):
        valor = valores.get(nombre)
        if valor is None or not valor.strip():
            return None
        if _etiqueta(valor) in ("no informado", "no especificado", "consultar", "-", "s/d"):
            return None
        if not re.fullmatch(r"\d+", valor) or int(valor) > 32767:
            raise ValueError(f"Cantidad de {nombre} inválida: {valor}")
        return int(valor)

    titulo = documento.select_one("meta[property='og:title']")
    descripcion = documento.select_one("#prop-desc")
    # El sitio entrega HTML escapado dentro de #prop-desc.
    texto_descripcion = (
        BeautifulSoup(descripcion.get_text(" ", strip=True), "html.parser").get_text(" ", strip=True)
        if descripcion else None
    )
    if not texto_descripcion:
        meta = documento.select_one("meta[property='og:description']")
        texto_descripcion = meta.get("content") if meta else None
    caracteristicas = list(dict.fromkeys(
        item.get_text(" ", strip=True)
        for item in documento.select(".ficha_ul li")
        if item.get_text(" ", strip=True)
    ))
    return DetallesPropiedad(
        titulo=titulo.get("content") if titulo else None,
        descripcion=texto_descripcion,
        caracteristicas="\n".join(caracteristicas) or None,
        # 'Ubicación' puede ser un barrio. No se convierte en ciudad.
        zona=valores.get("ubicacion"),
        ciudad=valores.get("ciudad"),
        provincia=valores.get("provincia"),
        dormitorios=cantidad("dormitorios"),
        ambientes=cantidad("ambientes"),
        banos=cantidad("banos"),
        **leer_ubicacion_mapa(documento),
    )


def extraer_dormitorios(url_original):
    """Compatibilidad para llamadas anteriores; la ingesta usa la ficha completa."""
    return extraer_detalles(url_original).dormitorios

def extraer_pagina(numero_pagina, operacion="venta"):
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


    documento = BeautifulSoup(respuesta.text, "html.parser")
    tarjetas = documento.select("li[prop-id]")

    #prepara la lisat final, la crea vacia y dentro del ciclo agregamos
    #un diccionario por cada propiedad
    propiedades = []

    #en cada vuelta, tarjeta representa a un prop-id fiferente.
    for tarjeta in tarjetas:
        direccion_elemento = tarjeta.select_one(".prop-desc-dir")
        tipo_elemento = tarjeta.select_one(".prop-desc-tipo-ub")
        tipo_descripcion = (
            tipo_elemento.get_text(" ", strip=True)
            if tipo_elemento
            else None
        )
        tipo = normalizar_tipo(tipo_descripcion)
        en_venta, en_alquiler = normalizar_operaciones(tipo_descripcion)
        precio_elemento = tarjeta.select_one(".prop-valor-nro")
        precio_crudo = (
            next(precio_elemento.stripped_strings, None)
            if precio_elemento
            else None
        )
        #aca llama a la funcion en normalizacion.py
        precio, moneda = normalizar_precio(precio_crudo)

        enlace_elemento = tarjeta.select_one("a[href]")

        #Diccionario con nombres uniformes, independiente de como Brega llame a los elementos en su HTML
        propiedad = {
            "identificador_fuente": tarjeta.get("prop-id"),
            "direccion": (
                direccion_elemento.get_text(strip= True)
                if direccion_elemento
                else None
            ),
            "tipo": tipo,
            "en_venta": en_venta,
            "en_alquiler": en_alquiler,
            "precio_crudo": precio_crudo,
            "precio": precio,
            "moneda": moneda,
            "url_original": (
                urljoin(URL_BASE, enlace_elemento.get("href"))
                if enlace_elemento
                else None
            ),
        }

        propiedades.append(propiedad)

    return propiedades

def extraer_primera_pagina(operacion= "venta"):
    return extraer_pagina(1,operacion)

def extraer_todas_las_paginas(operacion = "venta", max_paginas=50):
    propiedades = []
    identificadores_vistos = set()

    for numero_pagina in range (1, max_paginas + 1):
        lote = extraer_pagina(numero_pagina, operacion)
        if not lote :
            break
        nuevas = []

        for propiedad in lote:
            identificador = propiedad["identificador_fuente"]

            if identificador in identificadores_vistos:
                continue

            identificadores_vistos.add(identificador)
            nuevas.append(propiedad)

        if not nuevas:
            break
        propiedades.extend(nuevas)
        time.sleep(0.5)

    else:
        raise RuntimeError(
            f"Se alcanzó el limite de {max_paginas} paginas"
        )

    return propiedades

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
