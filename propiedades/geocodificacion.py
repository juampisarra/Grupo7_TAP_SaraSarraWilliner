"""Enriquecimiento explícito por dirección, con caché y aceptación conservadora."""

from datetime import timedelta
import re

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from geopy.exc import GeocoderServiceError

from .coordenadas import direccion_completa, firma_ubicacion, huella, par_valido, punto_publicado
from .enriquecimiento import normalizar_nombre
from .models import ConsultaDireccion, Propiedad
from .scraping.geocoding import consultar_direccion

VERSION = 1


def normalizar_calle(nombre):
    nombre = normalizar_nombre(nombre).replace(".", "")
    for corto, largo in (("bv", "bulevar"), ("bvar", "bulevar"), ("av", "avenida"),
                         ("gral", "general"), ("sta", "santa"), ("sto", "santo")):
        nombre = re.sub(rf"\b{corto}\b", largo, nombre)
    return re.sub(r"^calle\s+", "", nombre)


def validar_resultados(resultados, consulta):
    if resultados is None or resultados == []:
        return "sin_resultado", {}
    if not isinstance(resultados, list) or len(resultados) >= 5:
        return "ambiguo", {}
    validos = []
    for resultado in resultados:
        raw = getattr(resultado, "raw", None)
        if not isinstance(raw, dict):
            continue
        direccion = raw.get("address")
        if not isinstance(direccion, dict) or direccion.get("country_code") != "ar":
            continue
        if not (raw.get("addresstype") in {"house", "building"} or raw.get("type") == "house"
                or raw.get("class") == "building" or raw.get("category") == "building"):
            continue
        ciudades = [direccion[k] for k in ("city", "town", "village") if direccion.get(k)]
        if not ciudades or any(not isinstance(c, str) or normalizar_nombre(c) != normalizar_nombre(consulta["ciudad"]) for c in ciudades):
            continue
        provincia = direccion.get("state")
        if consulta["provincia"] and (not isinstance(provincia, str) or normalizar_nombre(provincia) != normalizar_nombre(consulta["provincia"])):
            continue
        calle = direccion.get("road")
        if not isinstance(calle, str) or normalizar_calle(calle) != normalizar_calle(consulta["calle"]):
            continue
        if str(direccion.get("house_number", "")) != consulta["altura"]:
            continue
        try:
            lat, lon = float(raw["lat"]), float(raw["lon"])
            if isinstance(raw["lat"], bool) or isinstance(raw["lon"], bool) or not par_valido(lat, lon):
                continue
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        validos.append({"latitud": lat, "longitud": lon, "osm_type": raw.get("osm_type"),
                        "osm_id": raw.get("osm_id"), "tipo": raw.get("type"),
                        "precision": "geocodificada_direccion"})
    return ("aceptado", validos[0]) if len(validos) == 1 else ("ambiguo", {})


def resolver_direccion(propiedad):
    consulta = direccion_completa(propiedad)
    if consulta is None:
        return None
    # Cambiar proveedor o validador no reutiliza resultados de otro contrato.
    identidad = {"version": VERSION, "proveedor": settings.NOMINATIM_DOMAIN,
                 "direccion": {k: normalizar_nombre(v) for k, v in consulta.items()}}
    clave = huella(identidad)
    cache = ConsultaDireccion.objects.filter(clave=clave).first()
    vigencia = timedelta(hours=24) if cache and cache.estado == "error" else timedelta(days=30)
    if cache and cache.consultada_en > timezone.now() - vigencia:
        return cache
    try:
        resultados = consultar_direccion(
            {"street": f'{consulta["altura"]} {consulta["calle"]}',
             "city": consulta["ciudad"], "state": consulta["provincia"], "country": "Argentina"},
            country_codes="ar", addressdetails=True, exactly_one=False,
            limit=5, language="es", timeout=10,
        )
        estado, resultado = validar_resultados(resultados, consulta)
    except (GeocoderServiceError, ValueError, TypeError) as error:
        # No guardar textos de excepciones que puedan incluir credenciales del proveedor.
        estado, resultado = "error", {"error_tipo": type(error).__name__}
    cache, _ = ConsultaDireccion.objects.update_or_create(
        clave=clave, defaults={"consulta": identidad, "estado": estado, "resultado": resultado})
    return cache


def aplicar_resultado(propiedad, cache):
    """Revalida tras el HTTP y bloquea solamente durante la escritura breve."""
    if cache is None or cache.estado != "aceptado":
        return False
    firma, original = firma_ubicacion(propiedad), punto_publicado(propiedad)
    with transaction.atomic():
        actual = Propiedad.objects.select_for_update().get(pk=propiedad.pk)
        if (not (actual.en_venta or actual.en_alquiler) or actual.geocodificacion
                or actual.actualizada_en != propiedad.actualizada_en
                or firma_ubicacion(actual) != firma or punto_publicado(actual) != original):
            return False
        consulta_actual = direccion_completa(actual)
        if (consulta_actual is None or cache.consulta.get("version") != VERSION
                or cache.consulta.get("direccion") != {k: normalizar_nombre(v) for k, v in consulta_actual.items()}):
            return False
        datos = cache.resultado
        if not par_valido(datos.get("latitud"), datos.get("longitud")):
            return False
        actual.coordenadas_fuente = original
        actual.geocodificacion = {
            **datos, "firma": firma, "original": original,
            "consulta_clave": cache.clave, "proveedor": cache.consulta["proveedor"],
            "version": VERSION, "aplicada_en": timezone.now().isoformat(),
        }
        actual.latitud, actual.longitud = datos["latitud"], datos["longitud"]
        # Coincidir en una dirección no garantiza la puerta real del inmueble.
        actual.ubicacion_aproximada, actual.radio_ubicacion_m = None, None
        actual.save(update_fields=["coordenadas_fuente", "geocodificacion", "latitud", "longitud",
                                   "ubicacion_aproximada", "radio_ubicacion_m", "actualizada_en"])
    return True


def restaurar_original(pk):
    """Revierte únicamente la mejora aplicada; conserva la evidencia de fuente."""
    with transaction.atomic():
        actual = Propiedad.objects.select_for_update().get(pk=pk)
        original = actual.coordenadas_fuente
        if not actual.geocodificacion or not par_valido(original.get("latitud"), original.get("longitud")):
            return False
        for campo in ("latitud", "longitud", "ubicacion_aproximada", "radio_ubicacion_m"):
            setattr(actual, campo, original.get(campo))
        actual.geocodificacion = {}
        actual.save(update_fields=["latitud", "longitud", "ubicacion_aproximada", "radio_ubicacion_m",
                                   "geocodificacion", "actualizada_en"])
    return True
