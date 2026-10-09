"""Contrato de adaptadores, independiente de Django y del HTML de cada sitio."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class PublicacionNormalizada:
    """Un aviso en el listado de una operación; localidad solo si es explícita."""

    identificador_fuente: str | None
    url_original: str | None
    direccion: str = ""
    tipo: str = ""
    precio: Decimal | None = None
    moneda: str = ""
    en_venta: bool = False
    en_alquiler: bool = False
    ciudad: str | None = None
    provincia: str | None = None
    titulo: str | None = None
    descripcion: str | None = None
    caracteristicas: str | None = None
    zona: str | None = None
    ambientes: int | None = None
    banos: int | None = None
    latitud: float | None = None
    longitud: float | None = None
    ubicacion_aproximada: bool | None = None
    radio_ubicacion_m: float | None = None


@dataclass(frozen=True)
class DetallesPropiedad:
    """Datos opcionales de una ficha leída correctamente; errores se propagan."""

    dormitorios: int | None = None
    titulo: str | None = None
    descripcion: str | None = None
    caracteristicas: str | None = None
    ciudad: str | None = None
    provincia: str | None = None
    zona: str | None = None
    ambientes: int | None = None
    banos: int | None = None
    latitud: float | None = None
    longitud: float | None = None
    ubicacion_aproximada: bool | None = None
    radio_ubicacion_m: float | None = None


class AdaptadorFuente(Protocol):
    nombre: str
    operaciones: tuple[str, ...]

    def extraer(self, operacion: str) -> list[PublicacionNormalizada]: ...

    def extraer_detalles(self, url_original: str) -> DetallesPropiedad:
        """Una sola solicitud por ficha; campos ausentes: None; errores se propagan."""
        ...
