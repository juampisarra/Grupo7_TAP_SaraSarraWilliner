from urllib.parse import urljoin
import time
import requests
from bs4 import BeautifulSoup
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

def extraer_dormitorios(url_original):
    respuesta = requests.get(
        url_original,
        headers=CABECERAS,
        timeout= 15,
    )
    #Devuelve el sstado de la request
    respuesta.raise_for_status()

    #Beautiful Soup extrae datos de páginas web en formato HTML o XML
    documento = BeautifulSoup(respuesta.text, "html.parser")

    for detalle in documento.select(".ficha_detalle_item"):
        etiqueta = detalle.select_one("b")

        if not etiqueta:
            continue

        nombre = etiqueta.get_text("", strip = True)

        if nombre.casefold() != "dormitorios":
            continue

        textos = list(detalle.stripped_strings)

        if len(textos) < 2:
            return None

        valor = textos[1]

        try:
            return int(valor)
        except ValueError as error:
            raise ValueError(
                f"Cantidad de dormitorios inválida: {valor}"
            ) from error
    return None

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

if __name__ == "__main__":
       for operacion in URLS_BUSQUEDA:
        propiedades = extraer_todas_las_paginas(operacion)

        print(
            f"{operacion.capitalize()}: "
            f"{len(propiedades)} propiedades encontradas"
        )

        for propiedad in propiedades[:3]:
            print(propiedad)