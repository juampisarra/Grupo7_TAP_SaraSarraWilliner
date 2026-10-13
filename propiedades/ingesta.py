"""Flujo común: consolidación, detalles y persistencia de cualquier adaptador.

No conoce selectores HTML ni fuentes concretas. La indexación automática durante
la ingesta sigue pendiente; por ahora reconstruir_indice carga lo guardado en la base.
"""

import time
import math
from dataclasses import asdict, dataclass

import requests
from django.db import transaction
from django.utils import timezone

from propiedades.models import Propiedad
from propiedades.enriquecimiento import ORIGEN_INVERSA, completar_localidad
from propiedades.scraping.contratos import AdaptadorFuente
from propiedades.scraping.geocoding import obtener_coordenadas
from propiedades.coordenadas import conciliar_coordenadas


@dataclass
class ResumenIngesta:
    procesadas: int = 0
    creadas: int = 0
    actualizadas: int = 0
    omitidas: int = 0
    detalles_solicitados: int = 0
    detalles_verificados: int = 0
    errores_detalle: int = 0
    localidades_completadas: int = 0
    bajas_venta: int = 0
    bajas_alquiler: int = 0
    bajas_omitidas: int = 0


def guardar_publicacion(fuente, identificador, valores):
    """Único punto de persistencia, reutilizable por todas las fuentes."""
    return Propiedad.objects.update_or_create(
        fuente=fuente, identificador_fuente=identificador, defaults=valores,
    )


def importar_fuente(adaptador: AdaptadorFuente, informar=lambda mensaje: None, completar_ubicacion=False):
    resumen = ResumenIngesta()
    publicaciones = {}
    operaciones = tuple(adaptador.operaciones)
    if not operaciones or len(set(operaciones)) != len(operaciones):
        raise ValueError("La fuente debe declarar operaciones únicas y no vacías")
    vistos = {operacion: set() for operacion in operaciones}
    # Descargar todos los listados antes de comenzar a guardar.
    for operacion in operaciones:
        if operacion not in ("venta", "alquiler"):
            raise ValueError(f"Operación desconocida: {operacion}")
        informar(f"Iniciando extracción de {operacion} ({adaptador.nombre})...")
        datos = adaptador.extraer(operacion)
        informar(f"Se encontraron {len(datos)} propiedades de {operacion}.")
        for dato in datos:
            if not dato.identificador_fuente or not dato.url_original:
                resumen.omitidas += 1
                continue
            vistos[operacion].add(dato.identificador_fuente)
            valores = publicaciones.setdefault(
                dato.identificador_fuente,
                {
                    "direccion": "", "tipo": "", "url_original": dato.url_original,
                },
            )
            if dato.direccion:
                valores["direccion"] = dato.direccion
            if dato.tipo:
                valores["tipo"] = dato.tipo
            for campo in (
                "titulo", "descripcion", "caracteristicas", "ciudad", "provincia",
                "zona", "ambientes", "banos", "latitud", "longitud",
                "ubicacion_aproximada", "radio_ubicacion_m",
            ):
                valor = getattr(dato, campo)
                if valor is not None:
                    valores[campo] = valor
            # La pertenencia al listado de la operación es la evidencia de vigencia.
            # No desactivar otra operación hasta terminar correctamente la fuente.
            valores[f"en_{operacion}"] = True
            valores[f"precio_{operacion}"] = dato.precio
            valores[f"moneda_{operacion}"] = dato.moneda

    for identificador, valores in publicaciones.items():
        informar(f"Procesando propiedad {identificador}...")
        existente = Propiedad.objects.filter(
            fuente=adaptador.nombre, identificador_fuente=identificador,
        ).first()
        resumen.detalles_solicitados += 1
        try:
            detalles = adaptador.extraer_detalles(valores["url_original"])
        except (requests.RequestException, ValueError) as error:
            resumen.errores_detalle += 1
            informar(f"No se pudieron obtener los detalles de {identificador}: {error}")
        else:
            for campo, valor in asdict(detalles).items():
                # Ausencia de información nueva no borra un dato ya guardado.
                if valor is not None:
                    valores[campo] = valor
            valores["dormitorios_verificados"] = True
            resumen.detalles_verificados += 1
        finally:
            time.sleep(0.5)

        ubicacion = {
            campo: valores.get(campo, getattr(existente, campo, None))
            for campo in ("ciudad", "provincia")
        }
        # No usar nombres inferidos para volver a geocodificar una dirección.
        for campo in ("ciudad", "provincia"):
            if (
                existente and not valores.get(campo)
                and getattr(existente, f"{campo}_origen") == ORIGEN_INVERSA
            ):
                ubicacion[campo] = None
        direccion_cambio = existente is not None and any(
            getattr(existente, campo) != valores.get(campo, getattr(existente, campo))
            for campo in ("direccion", "ciudad", "provincia", "zona")
        )
        coordenadas_completas = (
            existente is not None
            and existente.latitud is not None
            and existente.longitud is not None
        )
        latitud = valores.get("latitud")
        longitud = valores.get("longitud")
        coordenadas_fuente = (
            latitud is not None and longitud is not None
            and math.isfinite(latitud) and math.isfinite(longitud)
            and -90 <= latitud <= 90 and -180 <= longitud <= 180
        )
        if coordenadas_fuente:
            # La ubicación publicada tiene prioridad sobre inferirla de la dirección.
            valores["ubicacion_aproximada"] = valores.get("ubicacion_aproximada")
            valores["radio_ubicacion_m"] = valores.get("radio_ubicacion_m")
        else:
            # Un par parcial/inválido no debe mezclarse con coordenadas anteriores.
            for campo in ("latitud", "longitud", "ubicacion_aproximada", "radio_ubicacion_m"):
                valores.pop(campo, None)
        if not coordenadas_fuente and (direccion_cambio or not coordenadas_completas):
            # Nunca asociar coordenadas de la dirección anterior a la nueva.
            valores["latitud"] = None
            valores["longitud"] = None
            valores["ubicacion_aproximada"] = None
            valores["radio_ubicacion_m"] = None
            if valores["direccion"] and ubicacion["ciudad"]:
                latitud, longitud = obtener_coordenadas(
                    valores["direccion"], **ubicacion,
                )
                if latitud is not None and longitud is not None:
                    valores["latitud"] = latitud
                    valores["longitud"] = longitud

        if completar_localidad(valores, existente, habilitado=completar_ubicacion):
            resumen.localidades_completadas += 1
        # Refrescar la mejora bajo bloqueo: pudo aplicarse durante el HTTP de ficha.
        # No realizar consultas externas dentro de esta transacción corta.
        with transaction.atomic():
            actual = Propiedad.objects.select_for_update().filter(
                fuente=adaptador.nombre, identificador_fuente=identificador).first()
            cambio_actual = actual is not None and any(
                getattr(actual, campo) != valores.get(campo, getattr(actual, campo))
                for campo in ("direccion", "ciudad", "provincia", "zona"))
            conciliar_coordenadas(valores, actual, coordenadas_fuente=coordenadas_fuente,
                                 direccion_cambio=cambio_actual)
            _, creada = guardar_publicacion(adaptador.nombre, identificador, valores)
        resumen.procesadas += 1
        if creada:
            resumen.creadas += 1
        else:
            resumen.actualizadas += 1
    if resumen.omitidas:
        # Una tarjeta inválida puede ser un aviso vigente que no pudimos identificar.
        resumen.bajas_omitidas = 1
        informar("No se aplican bajas: el listado contiene publicaciones omitidas.")
    else:
        # Solo después de descargar y persistir toda la fuente. Una interrupción o
        # error fatal anterior conserva la vigencia previa de los avisos ausentes.
        # Ambas operaciones se concilian juntas; se conservan precios y fichas.
        with transaction.atomic():
            for operacion, identificadores in vistos.items():
                ausentes = Propiedad.objects.filter(
                    fuente=adaptador.nombre, **{f"en_{operacion}": True},
                ).exclude(identificador_fuente__in=identificadores)
                bajas = ausentes.update(**{
                    f"en_{operacion}": False, "actualizada_en": timezone.now(),
                })
                setattr(resumen, f"bajas_{operacion}", bajas)
    return resumen
