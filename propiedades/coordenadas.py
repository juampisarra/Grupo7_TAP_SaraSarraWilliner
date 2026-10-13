"""Evidencia de ubicación y diagnóstico; no calcula distancias ni filtros espaciales."""

from collections import defaultdict
import hashlib
import json
import math
import re

from django.db.models import Q

from .enriquecimiento import ORIGEN_INVERSA, normalizar_nombre
from .models import Propiedad

METODOS_SOSPECHOSOS = {"APPROXIMATE", "GEOMETRIC_CENTER"}


def par_valido(latitud, longitud):
    return all(type(v) in (int, float) and math.isfinite(v) for v in (latitud, longitud)) and (
        -90 <= latitud <= 90 and -180 <= longitud <= 180
    )


def huella(valor):
    return hashlib.sha256(json.dumps(valor, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def firma_ubicacion(propiedad):
    return huella([normalizar_nombre(getattr(propiedad, campo) or "")
                   for campo in ("direccion", "ciudad", "provincia", "zona")])


def punto_publicado(propiedad):
    if propiedad.coordenadas_fuente:
        return propiedad.coordenadas_fuente
    # Filas anteriores a 0013: evidencia histórica, no precisión nueva.
    return dict(latitud=propiedad.latitud, longitud=propiedad.longitud,
                ubicacion_aproximada=propiedad.ubicacion_aproximada,
                radio_ubicacion_m=propiedad.radio_ubicacion_m,
                metodo=propiedad.metodo_ubicacion_fuente)


def direccion_completa(propiedad):
    """Criterio deliberadamente conservador; no adivina alturas ni localidades."""
    if not propiedad.ciudad.strip() or propiedad.ciudad_origen == ORIGEN_INVERSA:
        return None
    if propiedad.provincia_origen == ORIGEN_INVERSA:
        return None
    texto = propiedad.direccion.strip()
    # 'al 100', esquinas, rutas, lotes y referencias no identifican una puerta.
    if re.search(r"\b(al|altura|aprox|aproximadamente|esq|esquina|entre|casi|ruta|km|lote|manzana|edificio|cochera)\b|s/n|[/&-]|\s+y\s+", texto, re.I):
        return None
    # Unidades explícitas no modifican la puerta. Los sufijos no reconocidos se rechazan.
    texto = re.split(r"\s+(?:piso|dpto\.?|depto\.?|departamento|oficina|ofic\.?|local|pb)\b", texto, maxsplit=1, flags=re.I)[0]
    texto = re.sub(r"\s+\d+[º°]$", "", texto)
    match = re.fullmatch(r"(.+?)\s+(?:N[º°]\s*)?([1-9]\d{0,5})", texto, re.I)
    if not match or not re.search(r"[^\W\d_]", match[1], re.UNICODE):
        return None
    calle, altura = match.groups()
    # '9 de Julio' no tiene altura; '9 de Julio 142' sí.
    return {"calle": calle.strip(), "altura": altura, "ciudad": propiedad.ciudad.strip(),
            "provincia": propiedad.provincia.strip(), "pais": "Argentina"}


def diagnosticar(*, fuente=None, umbral=5):
    if umbral < 2:
        raise ValueError("El umbral debe ser al menos 2")
    consulta = Propiedad.objects.filter(Q(en_venta=True) | Q(en_alquiler=True)).order_by("pk")
    if fuente:
        consulta = consulta.filter(fuente__iexact=fuente)
    propiedades = list(consulta)
    grupos = defaultdict(list)
    for p in propiedades:
        punto = punto_publicado(p)
        lat, lon = punto.get("latitud"), punto.get("longitud")
        if par_valido(lat, lon):
            clave = (p.fuente, normalizar_nombre(p.ciudad), normalizar_nombre(p.provincia), lat, lon)
            grupos[clave].append(p)
    repetidos, motivos = [], {}
    for clave, avisos in grupos.items():
        # Varias unidades de una misma puerta cuentan como una sola dirección.
        direcciones = set()
        for p in avisos:
            completa = direccion_completa(p)
            if completa:
                direcciones.add((normalizar_nombre(completa["calle"]), completa["altura"]))
        if len(avisos) >= umbral and len(direcciones) >= umbral:
            repetidos.append(dict(fuente=clave[0], ciudad=clave[1], latitud=clave[3],
                                  longitud=clave[4], publicaciones=len(avisos),
                                  puertas_distintas=len(direcciones), ids=[p.pk for p in avisos]))
            for p in avisos:
                motivos[p.pk] = ["punto_repetido_en_direcciones_distintas"]
    for p in propiedades:
        if punto_publicado(p).get("metodo") in METODOS_SOSPECHOSOS:
            motivos.setdefault(p.pk, []).append("metodo_fuente_aproximado")
    candidatos = []
    for p in propiedades:
        if p.pk not in motivos:
            continue
        direccion = direccion_completa(p)
        candidatos.append(dict(id=p.pk, fuente=p.fuente, direccion=p.direccion,
                               motivos=motivos[p.pk], elegible=direccion is not None,
                               ya_enriquecida=bool(p.geocodificacion)))
    return {"vigentes": len(propiedades), "umbral": umbral, "grupos": repetidos,
            "candidatos": candidatos}


def conciliar_coordenadas(valores, existente, *, coordenadas_fuente, direccion_cambio):
    """Preserva una mejora solo si siguen vigentes dirección y evidencia original."""
    anterior = existente.coordenadas_fuente if existente else {}
    original = anterior
    if coordenadas_fuente:
        original = {campo: valores.get(campo) for campo in (
            "latitud", "longitud", "ubicacion_aproximada", "radio_ubicacion_m")}
        original["metodo"] = valores.get("metodo_ubicacion_fuente", getattr(existente, "metodo_ubicacion_fuente", ""))
    elif direccion_cambio:
        original = {}
    valores["coordenadas_fuente"] = original
    mejora = existente.geocodificacion if existente else {}
    if not mejora:
        return
    from types import SimpleNamespace
    futura = SimpleNamespace(**{campo: valores.get(campo, getattr(existente, campo))
                               for campo in ("direccion", "ciudad", "provincia", "zona")})
    campos_punto = ("latitud", "longitud", "ubicacion_aproximada", "radio_ubicacion_m")
    previo = mejora.get("original", {})
    if (mejora.get("firma") == firma_ubicacion(futura)
            # Conocer por primera vez gmLocationType no cambia el punto original.
            and all(previo.get(campo) == original.get(campo) for campo in campos_punto)
            and par_valido(mejora.get("latitud"), mejora.get("longitud"))):
        valores.update(latitud=mejora["latitud"], longitud=mejora["longitud"],
                       ubicacion_aproximada=None, radio_ubicacion_m=None)
    else:
        valores["geocodificacion"] = {}


def informacion_ubicacion(propiedad):
    mejora = propiedad.geocodificacion
    return {
        "origen": "nominatim_direccion" if mejora else "fuente_o_historica",
        "precision": "geocodificada_direccion" if mejora else (
            "exacta_segun_fuente" if propiedad.ubicacion_aproximada is False else
            "aproximada" if propiedad.ubicacion_aproximada else "desconocida"),
        "metodo_fuente": propiedad.metodo_ubicacion_fuente or None,
        "punto_original": propiedad.coordenadas_fuente or None,
        "atribucion": "© OpenStreetMap contributors" if mejora else None,
    }
