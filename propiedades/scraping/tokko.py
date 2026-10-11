from urllib.parse import urljoin
from bs4 import BeautifulSoup
import re
import unicodedata
from .contratos import DetallesPropiedad

from .normalizacion import (
    normalizar_operaciones,
    normalizar_precio,
    normalizar_tipo
)


def recorrer_paginas(extraer_pagina, operacion, max_paginas, pausar):
    """Recorre un listado Tokko hasta un lote vacío o sin IDs nuevos."""
    propiedades = []
    identificadores_vistos = set()

    for numero_pagina in range(1, max_paginas + 1):
        lote = extraer_pagina(numero_pagina, operacion)
        if not lote:
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
        pausar(0.5)
    else:
        raise RuntimeError(
            f"Se alcanzó el límite de {max_paginas} páginas"
        )

    return propiedades


def leer_listado(html, url_base):
    documento = BeautifulSoup(html, "html.parser")
    tarjetas = documento.select("li[prop-id]")

    propiedades = []

    for tarjeta in tarjetas:
        direccion_elemento = tarjeta.select_one(".prop-desc-dir")
        tipo_elemento = tarjeta.select_one(".prop-desc-tipo-ub")
        precio_elemento = tarjeta.select_one(".prop-valor-nro")
        enlace_elemento = tarjeta.select_one("a[href]")

        tipo_descripcion = (
            tipo_elemento.get_text(" ", strip=True)
            if tipo_elemento
            else None
        )

        tipo = normalizar_tipo(tipo_descripcion)
        en_venta, en_alquiler = normalizar_operaciones(tipo_descripcion)

        precio_crudo = (
            next(precio_elemento.stripped_strings, None)
            if precio_elemento
            else None
        )
        precio, moneda = normalizar_precio(precio_crudo)

        propiedades.append({
            "identificador_fuente": tarjeta.get("prop-id"),
            "direccion": (
                direccion_elemento.get_text(" ", strip=True)
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
                urljoin(url_base, enlace_elemento.get("href"))
                if enlace_elemento
                else None
            ),
        })

    return propiedades 

def _etiqueta(texto):
    texto = unicodedata.normalize("NFKD", texto.casefold())
    return " ".join(
        "".join(
            caracter
            for caracter in texto
            if not unicodedata.combining(caracter)
        ).split()
    )


def leer_detalles(html, extraer_ubicacion=None):
    documento = BeautifulSoup(html, "html.parser")

    if not documento.select_one(
        ".ficha_detalle_item, #lista_informacion_basica, #prop-desc"
    ):
        raise ValueError("No se reconoció la estructura de la ficha Tokko")

    valores = {}

    for detalle in documento.select(".ficha_detalle_item"):
        etiqueta = detalle.select_one("b")

        if etiqueta:
            textos = list(detalle.stripped_strings)

            if len(textos) > 1:
                valores[_etiqueta(etiqueta.get_text())] = " ".join(
                    textos[1:]
                )

    for item in documento.select("#lista_informacion_basica li"):
        nombre, separador, valor = item.get_text(
            " ",
            strip=True,
        ).partition(":")

        if separador:
            valores[_etiqueta(nombre)] = valor.strip()

    def cantidad(nombre):
        valor = valores.get(nombre)

        if valor is None or not valor.strip():
            return None

        if _etiqueta(valor) in (
            "no informado",
            "no especificado",
            "consultar",
            "-",
            "s/d",
        ):
            return None

        if not re.fullmatch(r"\d+", valor) or int(valor) > 32767:
            raise ValueError(
                f"Cantidad de {nombre} inválida: {valor}"
            )

        return int(valor)

    titulo = documento.select_one("meta[property='og:title']")
    descripcion = documento.select_one("#prop-desc")

    texto_descripcion = (
        BeautifulSoup(
            descripcion.get_text(" ", strip=True),
            "html.parser",
        ).get_text(" ", strip=True)
        if descripcion
        else None
    )

    if not texto_descripcion:
        meta = documento.select_one("meta[property='og:description']")
        texto_descripcion = meta.get("content") if meta else None

    caracteristicas = list(dict.fromkeys(
        item.get_text(" ", strip=True)
        for item in documento.select(".ficha_ul li")
        if item.get_text(" ", strip=True)
    ))

    ubicacion = (
        extraer_ubicacion(documento)
        if extraer_ubicacion
        else {}
    )

    return DetallesPropiedad(
        titulo=titulo.get("content") if titulo else None,
        descripcion=texto_descripcion,
        caracteristicas="\n".join(caracteristicas) or None,
        zona=valores.get("ubicacion"),
        ciudad=valores.get("ciudad"),
        provincia=valores.get("provincia"),
        dormitorios=cantidad("dormitorios"),
        ambientes=cantidad("ambientes"),
        banos=cantidad("banos"),
        **ubicacion,
    )
