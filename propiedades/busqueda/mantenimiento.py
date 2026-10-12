"""Retención de versiones: vista previa por defecto, nombres concretos al borrar."""

import re
from dataclasses import dataclass

from elasticsearch import ApiError
from elastic_transport import TransportError

from .cliente import BusquedaNoDisponible, crear_cliente, nombre_indice


@dataclass(frozen=True)
class PlanLimpieza:
    activo: str
    anteriores: tuple[str, ...]
    conservar: tuple[str, ...]
    candidatos: tuple[str, ...]
    advertencia: str = ""


def planificar_limpieza(cliente, alias):
    activos = cliente.indices.get_alias(name=alias)
    if len(activos) != 1:
        raise BusquedaNoDisponible("La limpieza requiere exactamente un índice activo en el alias")
    activo = next(iter(activos))
    patron = rf"{re.escape(alias)}-([0-9]{{14}})-[0-9a-f]{{8}}"
    coincidencia = re.fullmatch(patron, activo)
    if not coincidencia:
        raise BusquedaNoDisponible("El índice activo no tiene el formato de versiones del proyecto")
    inventario = cliente.indices.get_alias(index=f"{alias}-*", expand_wildcards="all")
    mapping = cliente.indices.get_mapping(index=activo)
    meta = mapping.get(activo, {}).get("mappings", {}).get("_meta", {}).get("grupo7", {})
    anteriores = meta.get("anteriores")
    if (meta.get("alias") != alias or meta.get("completo") is not True
            or not isinstance(anteriores, list)
            or any(not isinstance(i, str) or not re.fullmatch(patron, i) for i in anteriores)):
        return PlanLimpieza(activo, (), tuple(sorted(inventario)), (),
            "El índice activo no registra su versión anterior. Reconstruir con el código nuevo antes de limpiar.")
    if any(indice not in inventario for indice in anteriores):
        return PlanLimpieza(activo, tuple(anteriores), tuple(sorted(inventario)), (),
            "Falta una versión anterior registrada; revisar el inventario antes de limpiar.")
    protegidos = {activo, *anteriores}
    candidatos = []
    for indice, datos in inventario.items():
        version = re.fullmatch(patron, indice)
        # Proteger cualquier alias, formatos ajenos y versiones posteriores o
        # del mismo segundo (podrían pertenecer a otra reconstrucción en curso).
        if (indice not in protegidos and version and version[1] < coincidencia[1]
                and not datos.get("aliases")):
            candidatos.append(indice)
    return PlanLimpieza(activo, tuple(anteriores),
        tuple(sorted(set(inventario) - set(candidatos))), tuple(sorted(candidatos)))


def limpiar_indices(*, aplicar=False, informar=lambda mensaje: None):
    alias = nombre_indice()
    eliminados = []
    try:
        with crear_cliente() as cliente:
            plan = planificar_limpieza(cliente, alias)
            informar(f"Activo: {plan.activo}")
            informar(f"Conservar: {', '.join(plan.conservar)}")
            informar(f"Candidatos a eliminar: {', '.join(plan.candidatos) or 'ninguno'}")
            if plan.advertencia:
                informar(plan.advertencia)
                if aplicar:
                    raise BusquedaNoDisponible(plan.advertencia)
            if not aplicar:
                informar("Vista previa: no se borró ningún índice. Usar --aplicar para ejecutar el plan.")
                return plan, eliminados
            for indice in plan.candidatos:
                # Revisar otra vez alias, metadatos y protecciones antes de cada
                # borrado. Actions excluye concurrencia; no ejecutar en paralelo local.
                actual = planificar_limpieza(cliente, alias)
                if (actual.activo != plan.activo or actual.anteriores != plan.anteriores
                        or indice not in actual.candidatos):
                    raise BusquedaNoDisponible("Cambió el estado de los índices; se detuvo la limpieza. Revisar la vista previa")
                respuesta = cliente.indices.delete(index=indice)
                if not respuesta.get("acknowledged", False):
                    raise BusquedaNoDisponible("No se confirmó el borrado; revisar inventario antes de repetir")
                eliminados.append(indice)
                informar(f"Eliminado: {indice}")
            return plan, eliminados
    except (ApiError, TransportError):
        raise BusquedaNoDisponible(
            "No se completó la limpieza. Revisar permisos, conexión e inventario; los borrados previos no se revierten"
        ) from None
