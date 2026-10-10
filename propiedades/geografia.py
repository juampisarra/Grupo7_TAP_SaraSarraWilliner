"""Filtros espaciales exclusivamente PostGIS; Python solo valida las entradas.

La columna ubicacion es generada por PostgreSQL (migración 0011). Se conserva
el modelo portátil con latitud/longitud para desarrollo y pruebas en SQLite.
"""

import math

from django.db import connections, NotSupportedError
from django.db.models.expressions import RawSQL


def numero(valor, nombre, minimo, maximo):
    try:
        resultado = float(valor)
    except (ValueError, TypeError, OverflowError):
        raise ValueError(f"{nombre} debe ser un número finito") from None
    if not math.isfinite(resultado) or not minimo <= resultado <= maximo:
        raise ValueError(f"{nombre} debe estar entre {minimo} y {maximo}")
    return resultado


def _contexto(queryset):
    conexion = connections[queryset.db]
    if conexion.vendor != "postgresql":
        raise NotSupportedError("Los filtros geográficos requieren PostgreSQL con PostGIS")
    with conexion.cursor() as cursor:
        cursor.execute("""
            SELECT n.nspname FROM pg_extension e
            JOIN pg_namespace n ON n.oid = e.extnamespace WHERE e.extname = 'postgis'
        """)
        fila = cursor.fetchone()
    if not fila:
        raise NotSupportedError("PostGIS no está instalado; ejecutar las migraciones")
    return conexion.ops.quote_name(fila[0]), conexion.ops.quote_name(queryset.model._meta.db_table)


def _filtrar(queryset, tabla, condicion, parametros, incluir_aproximadas):
    # Solo una ubicación explícitamente exacta se considera exacta. NULL es desconocida.
    if not incluir_aproximadas:
        queryset = queryset.filter(ubicacion_aproximada=False)
    return queryset.filter(pk__in=RawSQL(
        f'SELECT id FROM {tabla} WHERE ubicacion IS NOT NULL AND {condicion}',
        parametros,
    ))


def filtrar_radio(queryset, latitud, longitud, radio_m, *, incluir_aproximadas=False):
    latitud = numero(latitud, "latitud", -90, 90)
    longitud = numero(longitud, "longitud", -180, 180)
    radio_m = numero(radio_m, "radio_m", 0, 20_000_000)
    schema, tabla = _contexto(queryset)
    return _filtrar(queryset, tabla,
        f'{schema}.ST_DWithin(ubicacion, {schema}.ST_SetSRID('
        f'{schema}.ST_MakePoint(%s, %s), 4326)::{schema}.geography, %s)',
        (longitud, latitud, radio_m), incluir_aproximadas)


def filtrar_area(queryset, oeste, sur, este, norte, *, incluir_aproximadas=False):
    oeste = numero(oeste, "oeste", -180, 180)
    este = numero(este, "este", -180, 180)
    sur = numero(sur, "sur", -90, 90)
    norte = numero(norte, "norte", -90, 90)
    if oeste >= este or sur >= norte:
        raise ValueError("El área requiere oeste < este y sur < norte; no admite cruzar el antimeridiano")
    schema, tabla = _contexto(queryset)
    return _filtrar(queryset, tabla,
        f'{schema}.ST_Covers({schema}.ST_MakeEnvelope(%s, %s, %s, %s, 4326), '
        f'ubicacion::{schema}.geometry)',
        (oeste, sur, este, norte), incluir_aproximadas)


def aplicar_filtros_geograficos(queryset, parametros):
    radio = ("latitud", "longitud", "radio_m")
    area = ("oeste", "sur", "este", "norte")
    tiene_radio = any(c in parametros for c in radio)
    tiene_area = any(c in parametros for c in area)
    if tiene_radio and tiene_area:
        raise ValueError("Elegir radio o área en una misma consulta")
    incluir = parametros.get("incluir_aproximadas", "0")
    if incluir not in ("0", "1"):
        raise ValueError("incluir_aproximadas debe ser 0 o 1")
    campos = radio if tiene_radio else area if tiene_area else ()
    if not campos:
        return queryset
    if not all(c in parametros for c in campos):
        raise ValueError("El filtro requiere: " + ", ".join(campos))
    funcion = filtrar_radio if tiene_radio else filtrar_area
    return funcion(queryset, *(parametros[c] for c in campos), incluir_aproximadas=incluir == "1")
