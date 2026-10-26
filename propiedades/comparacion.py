"""Comparación de publicaciones guardadas; no ejecuta búsquedas ni ingesta."""

from decimal import Decimal
import hashlib
import json
import re

from django.utils.html import strip_tags

from .coordenadas import informacion_ubicacion
from .models import Propiedad

MAX_PROPIEDADES = 4


class ErrorComparacion(ValueError):
    def __init__(self, mensaje, *, status=400, codigo="seleccion_invalida", ids=None):
        super().__init__(mensaje)
        self.status = status
        self.codigo = codigo
        self.ids = ids or []


def validar_seleccion(ids, operacion):
    if operacion not in ("venta", "alquiler"):
        raise ErrorComparacion("Elegí venta o alquiler para comparar.")
    if not isinstance(ids, list) or not 2 <= len(ids) <= MAX_PROPIEDADES:
        raise ErrorComparacion("Seleccioná entre 2 y 4 publicaciones.")
    if any(type(pid) is not int or not 0 < pid <= 9223372036854775807 for pid in ids):
        raise ErrorComparacion("Los IDs deben ser números enteros positivos.")
    if len(set(ids)) != len(ids):
        raise ErrorComparacion("Una publicación no puede repetirse en la comparación.")


def ids_desde_query(parametros):
    if any(len(parametros.getlist(campo)) != 1 for campo in ("ids", "operacion")):
        raise ErrorComparacion("Indicá ids y operacion una sola vez.")
    texto = parametros["ids"]
    if len(texto) > 100 or not re.fullmatch(r"[0-9]+(?:,[0-9]+){1,3}", texto):
        raise ErrorComparacion("Indicá entre 2 y 4 IDs separados por comas.")
    return [int(pid) for pid in texto.split(",")]


def firma_datos(datos):
    return hashlib.sha256(json.dumps(datos, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":")).encode()).hexdigest()


def preparar_comparacion(ids, operacion):
    validar_seleccion(ids, operacion)
    por_id = Propiedad.objects.in_bulk(ids)
    ausentes = [pid for pid in ids if pid not in por_id]
    if ausentes:
        raise ErrorComparacion("Hay publicaciones que ya no existen. Quitalas de la selección.",
                               status=404, codigo="publicaciones_ausentes", ids=ausentes)
    retiradas = [pid for pid in ids if not getattr(por_id[pid], f"en_{operacion}")]
    if retiradas:
        raise ErrorComparacion("Hay publicaciones que ya no están disponibles para esta operación. Quitalas de la selección.",
                               status=409, codigo="publicaciones_retiradas", ids=retiradas)
    propiedades = []
    for pid in ids:
        p = por_id[pid]
        dato = {campo: getattr(p, campo) for campo in (
            "id", "fuente", "titulo", "tipo", "direccion", "zona", "ciudad", "provincia",
            "dormitorios", "dormitorios_verificados", "ambientes", "banos", "caracteristicas",
            "url_original",
        )}
        precio = getattr(p, f"precio_{operacion}")
        dato.update(
            foto_portada=p.foto_portada,
            precio=format(precio, ".2f") if precio is not None else None,
            moneda=getattr(p, f"moneda_{operacion}") or None,
            actualizada_en=p.actualizada_en.isoformat(),
            precision=(informacion_ubicacion(p)["precision"] if p.latitud is not None and p.longitud is not None
                       else "sin_coordenadas"),
        )
        propiedades.append(dato)
    # Solo se calculan diferencias con precio y moneda conocidos en todo el grupo.
    comparables = all(p["precio"] is not None and p["moneda"] for p in propiedades)
    comparables = bool(comparables and len({p["moneda"] for p in propiedades}) == 1)
    minimo = min(Decimal(p["precio"]) for p in propiedades) if comparables else None
    for p in propiedades:
        p["diferencia_con_menor_precio"] = (
            format(Decimal(p["precio"]) - minimo, ".2f") if comparables else None)
    datos = {"operacion": operacion, "propiedades": propiedades, "precios_comparables": comparables}
    # El orden visual no cambia la identidad de una comparación.
    datos["firma"] = firma_datos({**datos, "propiedades": sorted(propiedades, key=lambda p: p["id"])})
    return datos


def datos_para_llm(datos):
    """Lista permitida: nunca comentarios, fotos, contactos o coordenadas."""
    return {
        "operacion": datos["operacion"], "precios_comparables": datos["precios_comparables"],
        "propiedades": [
            {**{campo: p[campo] for campo in (
                "id", "tipo", "ciudad", "dormitorios", "dormitorios_verificados", "ambientes", "banos",
                "precio", "moneda", "precision", "diferencia_con_menor_precio",
            )}, "caracteristicas_publicadas": limpiar_caracteristicas(p["caracteristicas"])}
            for p in sorted(datos["propiedades"], key=lambda p: p["id"])
        ],
    }


def limpiar_caracteristicas(texto):
    texto = strip_tags(texto[:5000])
    texto = re.sub(r"https?://\S+|www\.\S+|[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}", "[contacto omitido]", texto)
    texto = re.sub(r"(?<!\w)\+?\d[\d ()-]{6,}\d(?!\w)", "[número de contacto omitido]", texto)
    return texto[:1600]
