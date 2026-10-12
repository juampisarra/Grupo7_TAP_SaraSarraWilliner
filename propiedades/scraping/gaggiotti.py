"""Adaptador del servicio público utilizado por la web de Gaggiotti.

Los listados completos se consultan con POST (solo lectura). GET queda como
respaldo para pedir una ficha directamente, fuera de una extracción de listados.
No utiliza credenciales ni accede a la base de datos o a Elasticsearch.
"""

import html
import logging
import math
import re
import time
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

import requests
from bs4 import BeautifulSoup

from .contratos import DetallesPropiedad, PublicacionNormalizada


URL_BASE = "https://www.gaggiotti.com.ar"
URL_API = f"{URL_BASE}/api/Property"
OPERACIONES = {"venta": (1, "Compra-Venta"), "alquiler": (2, "Alquiler")}
CABECERAS = {"User-Agent": "Grupo7-TAP/0.1 (proyecto academico)"}
TAMANO_PAGINA = 20
MAX_PAGINAS = 50
logger = logging.getLogger(__name__)


def texto(valor):
    if valor is None:
        return ""
    if not isinstance(valor, str):
        raise ValueError("Gaggiotti: se esperaba un campo de texto")
    documento = BeautifulSoup(html.unescape(valor), "html.parser")
    for elemento in documento.select("script, style"):
        elemento.decompose()
    return " ".join(documento.get_text(" ", strip=True).split())


def cantidad(valor):
    """No convertir ausencia en cero, ni aceptar negativos/fracciones/bools."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, bool) or not re.fullmatch(r"\d+", str(valor)):
        raise ValueError("Gaggiotti: cantidad inválida")
    numero = int(valor)
    if numero > 32767:
        raise ValueError("Gaggiotti: cantidad fuera de rango")
    return numero


def identificador(dato):
    valor = dato.get("id") if isinstance(dato, dict) else None
    if isinstance(valor, bool) or not re.fullmatch(r"[1-9]\d*", str(valor)):
        raise ValueError("Gaggiotti: publicación sin identificador válido")
    return str(valor)


def leer_precio(dato, operacion):
    operaciones = dato.get("operations")
    if not isinstance(operaciones, list) or any(not isinstance(o, dict) for o in operaciones):
        raise ValueError("Gaggiotti: operaciones inválidas")
    nombre = OPERACIONES[operacion][1].casefold()
    coincidentes = [o for o in operaciones if texto(o.get("operationType")).casefold() == nombre]
    if len(coincidentes) != 1:
        raise ValueError(f"Gaggiotti: operación {operacion} ausente o ambigua")
    # La web solo muestra precios cuando webPrice es true; no exponer los ocultos.
    if dato.get("webPrice") is not True:
        return None, ""
    precios = coincidentes[0].get("prices")
    if not isinstance(precios, list):
        raise ValueError("Gaggiotti: estructura de precios inválida")
    if not precios:
        return None, ""
    # El frontend muestra el primer precio de cada operación, sin convertir monedas.
    precio = precios[0]
    if not isinstance(precio, dict):
        raise ValueError("Gaggiotti: precio inválido")
    moneda = texto(precio.get("currency")).upper()
    if moneda not in ("ARS", "USD") or str(precio.get("period")) != "0":
        logger.warning("Gaggiotti %s: moneda o período no soportado; precio omitido", identificador(dato))
        return None, ""
    valor = precio.get("price")
    if valor is None or valor == "":
        return None, moneda
    try:
        numero = Decimal(str(valor))
        if not numero.is_finite() or numero < 0 or numero >= Decimal("10000000000000"):
            raise ValueError("fuera de rango")
        if numero != numero.quantize(Decimal("0.01")):
            raise ValueError("más de dos decimales")
    except (InvalidOperation, ValueError):
        raise ValueError("Gaggiotti: importe inválido") from None
    return numero, moneda


def leer_ubicacion(dato):
    """Jerarquía observada: país | provincia | departamento | ciudad | barrio."""
    ubicacion = dato.get("location")
    if ubicacion is None:
        return {}
    if not isinstance(ubicacion, dict):
        raise ValueError("Gaggiotti: ubicación inválida")
    ruta = ubicacion.get("fullLocation")
    if not ruta:
        return {}
    if not isinstance(ruta, str):
        raise ValueError("Gaggiotti: jerarquía de ubicación inválida")
    partes = [texto(p) for p in ruta.split("|")]
    if not 2 <= len(partes) <= 5 or partes[0].casefold() != "argentina" or not all(partes):
        logger.warning("Gaggiotti %s: jerarquía de ubicación desconocida", identificador(dato))
        return {}
    return {
        "provincia": partes[1],
        "ciudad": partes[3] if len(partes) >= 4 else None,
        "zona": partes[4] if len(partes) == 5 else None,
    }


def leer_coordenadas(dato):
    par = (dato.get("geoLatitude"), dato.get("geoLongitude"))
    if all(v is None or v == "" for v in par):
        return {}
    try:
        if any(isinstance(v, bool) for v in par):
            raise ValueError
        latitud, longitud = map(float, par)
        if not (math.isfinite(latitud) and math.isfinite(longitud)
                and -90 <= latitud <= 90 and -180 <= longitud <= 180):
            raise ValueError
    except (TypeError, ValueError, OverflowError):
        logger.warning("Gaggiotti %s: coordenadas incompletas o inválidas", identificador(dato))
        return {}
    # El mapa usa un marcador sin radio. gmLocationType describe su obtención,
    # pero no garantiza precisión del aviso: no extrapolar la decisión de Avantix.
    return dict(latitud=latitud, longitud=longitud, ubicacion_aproximada=None, radio_ubicacion_m=None)


def leer_caracteristicas(dato):
    resultado = []
    for campo in ("tags", "customTags"):
        for etiqueta in dato.get(campo) or []:
            if not isinstance(etiqueta, dict):
                raise ValueError("Gaggiotti: característica inválida")
            nombre = texto(etiqueta.get("name"))
            if nombre:
                resultado.append(nombre)
    for atributo in dato.get("extraAttributes") or []:
        if not isinstance(atributo, dict):
            raise ValueError("Gaggiotti: atributo inválido")
        nombre, valor = texto(atributo.get("name")), texto(atributo.get("value"))
        if nombre and valor:
            resultado.append(f"{nombre}: {valor}")
    cocheras = cantidad(dato.get("parkingLotAmount"))
    if cocheras:
        resultado.append(f"Cocheras: {cocheras}")
    return "; ".join(dict.fromkeys(resultado)) or None


def leer_detalles(dato):
    identificador(dato)
    return DetallesPropiedad(
        titulo=texto(dato.get("publicationTitle")) or None,
        descripcion=texto(dato.get("description")) or texto(dato.get("richDescription")) or None,
        caracteristicas=leer_caracteristicas(dato),
        dormitorios=cantidad(dato.get("suiteAmount")),
        ambientes=cantidad(dato.get("roomAmount")),
        banos=cantidad(dato.get("bathroomAmount")),
        **leer_ubicacion(dato), **leer_coordenadas(dato),
    )


def leer_publicacion(dato, operacion):
    clave = identificador(dato)
    precio, moneda = leer_precio(dato, operacion)
    tipo = dato.get("type")
    if tipo is not None and not isinstance(tipo, dict):
        raise ValueError("Gaggiotti: tipo de inmueble inválido")
    ruta_operacion = OPERACIONES[operacion][1].lower()
    # Ruta de ficha del router público; el slug del título es opcional.
    return PublicacionNormalizada(
        identificador_fuente=clave,
        url_original=f"{URL_BASE}/propiedad/{ruta_operacion}/{clave}/",
        # El frontend muestra realAddress; address se conserva como respaldo público.
        direccion=texto(dato.get("realAddress")) or texto(dato.get("address")),
        tipo=texto((tipo or {}).get("name")),
        precio=precio, moneda=moneda,
        en_venta=operacion == "venta", en_alquiler=operacion == "alquiler",
    )


def leer_respuesta(respuesta):
    respuesta.raise_for_status()
    cuerpo = respuesta.json()
    if not isinstance(cuerpo, dict) or cuerpo.get("communicationStatus") != 200:
        raise ValueError("Gaggiotti: respuesta del servicio inválida")
    datos = cuerpo.get("response")
    if not isinstance(datos, dict):
        raise ValueError("Gaggiotti: respuesta sin datos válidos")
    return datos


class AdaptadorGaggiotti:
    nombre = "Gaggiotti"
    operaciones = ("venta", "alquiler")

    def __init__(self):
        # Search devuelve la ficha completa. Reutilizarla solo dentro de esta
        # instancia/ejecución, sin otra solicitud por cada aviso ni caché persistente.
        self._fichas = {}

    def extraer(self, operacion):
        if operacion not in OPERACIONES:
            raise ValueError(f"Operación desconocida: {operacion}")
        publicaciones, vistos, fichas = [], set(), {}
        offset, total = 0, None
        for _ in range(MAX_PAGINAS):
            datos = leer_respuesta(requests.post(
                f"{URL_API}/Search", headers=CABECERAS, timeout=15,
                json={
                    "operationTypes": [OPERACIONES[operacion][0]],
                    "propertyTypes": [], "roomTypes": [], "withParking": None,
                    "sortProperty": "id", "order": "desc",
                    "localizationType": 3, "localizationIds": [None],
                    "limit": TAMANO_PAGINA, "offset": offset,
                },
            ))
            lote, pagina = datos.get("properties"), datos.get("pagination")
            if not isinstance(lote, list) or not isinstance(pagina, dict):
                raise ValueError("Gaggiotti: listado o paginación inválidos")
            for campo in ("limit", "offset", "totalCount", "remaining"):
                if type(pagina.get(campo)) is not int or pagina[campo] < 0:
                    raise ValueError("Gaggiotti: contadores de paginación inválidos")
            if (pagina["offset"] != offset or not pagina["limit"]
                    or len(lote) > pagina["limit"]
                    or pagina["remaining"] != pagina["totalCount"] - offset - len(lote)):
                raise ValueError("Gaggiotti: paginación inconsistente")
            if total is not None and pagina["totalCount"] != total:
                raise ValueError("Gaggiotti: el listado cambió durante la extracción; reintentar")
            total = pagina["totalCount"]
            for dato in lote:
                publicacion = leer_publicacion(dato, operacion)
                if publicacion.identificador_fuente in vistos:
                    raise ValueError("Gaggiotti: IDs repetidos durante la paginación")
                vistos.add(publicacion.identificador_fuente)
                publicaciones.append(publicacion)
                fichas[publicacion.url_original] = dato
            if pagina["remaining"] == 0:
                # No reutilizar datos de una extracción incompleta o fallida.
                prefijo = f"{URL_BASE}/propiedad/{OPERACIONES[operacion][1].lower()}/"
                self._fichas = {url: dato for url, dato in self._fichas.items() if not url.startswith(prefijo)}
                self._fichas.update(fichas)
                return publicaciones
            if not lote:
                raise ValueError("Gaggiotti: página vacía antes de completar el listado")
            offset += len(lote)
            time.sleep(0.5)
        raise RuntimeError(f"Gaggiotti: se alcanzó el límite de {MAX_PAGINAS} páginas")

    def extraer_detalles(self, url_original):
        url = urlsplit(url_original)
        coincidencia = re.fullmatch(r"/propiedad/(?:compra-venta|alquiler)/([1-9]\d*)/", url.path)
        if (url.scheme != "https" or url.netloc != "www.gaggiotti.com.ar"
                or url.query or url.fragment or not coincidencia):
            raise ValueError("Gaggiotti: URL de ficha inválida")
        clave = coincidencia[1]
        dato = self._fichas.get(url_original)
        if dato is None:
            dato = leer_respuesta(requests.get(
                f"{URL_API}/{clave}", headers=CABECERAS, timeout=15,
            ))
        if identificador(dato) != clave:
            raise ValueError("Gaggiotti: la ficha no corresponde al aviso solicitado")
        return leer_detalles(dato)
