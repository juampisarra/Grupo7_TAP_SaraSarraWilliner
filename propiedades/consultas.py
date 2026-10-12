"""Contrato compartido de filtros y paginación para HTML y JSON."""

import re
from dataclasses import dataclass
from decimal import Decimal

from django.core.paginator import Paginator

from .geografia import aplicar_filtros_geograficos
from .models import Propiedad


CAMPOS_GEOGRAFICOS = (
    "latitud", "longitud", "radio_m", "oeste", "sur", "este", "norte", "incluir_aproximadas",
)
CAMPOS_FILTROS = ("operacion", "tipo", "dormitorios", "moneda", "precio_min", "precio_max", "q")
CAMPOS_CONSULTA = (*CAMPOS_FILTROS, *CAMPOS_GEOGRAFICOS, "pagina", "por_pagina")
AVISO_PRECISION = (
    "El filtro utiliza los puntos publicados, incluidos centros de áreas aproximadas "
    "y ubicaciones de precisión desconocida. No garantiza que cada inmueble esté dentro del área buscada."
)


def entero(valor, campo, minimo, maximo):
    if not re.fullmatch(r"[0-9]{1,10}", valor):
        raise ValueError(f"{campo} debe ser un entero entre {minimo} y {maximo}")
    numero = int(valor)
    if not minimo <= numero <= maximo:
        raise ValueError(f"{campo} debe estar entre {minimo} y {maximo}")
    return numero


def importe(valor, campo):
    # Decimales con punto, sin notación científica ni separadores de miles.
    if not re.fullmatch(r"[0-9]{1,13}(?:\.[0-9]{1,2})?", valor):
        raise ValueError(f"{campo} debe ser un importe no negativo con hasta dos decimales y punto decimal")
    return Decimal(valor)


@dataclass(frozen=True)
class Filtros:
    operacion: str
    tipo: str
    dormitorios: int | None
    moneda: str
    precio_min: Decimal | None
    precio_max: Decimal | None
    texto: str
    pagina: int
    por_pagina: int

    @classmethod
    def leer(cls, parametros):
        for campo in CAMPOS_CONSULTA:
            if len(parametros.getlist(campo)) > 1:
                raise ValueError(f"{campo} no admite valores repetidos")
        operacion = parametros.get("operacion", "alquiler").strip()
        if operacion not in ("venta", "alquiler"):
            raise ValueError("operacion debe ser venta o alquiler")
        tipo = parametros.get("tipo", "").strip()
        if len(tipo) > 50:
            raise ValueError("tipo admite hasta 50 caracteres")
        dorm = parametros.get("dormitorios", "").strip()
        dormitorios = entero(dorm, "dormitorios", 0, 32767) if dorm else None
        moneda = parametros.get("moneda", "").strip().upper()
        if moneda and moneda not in ("ARS", "USD"):
            raise ValueError("moneda debe ser ARS o USD")
        minimo, maximo = (parametros.get(c, "").strip() for c in ("precio_min", "precio_max"))
        if (moneda or minimo or maximo) and "operacion" not in parametros:
            raise ValueError("Para filtrar precios o moneda indicar operacion explícitamente")
        if (minimo or maximo) and not moneda:
            raise ValueError("Para filtrar precios indicar moneda")
        precio_min = importe(minimo, "precio_min") if minimo else None
        precio_max = importe(maximo, "precio_max") if maximo else None
        if precio_min is not None and precio_max is not None and precio_min > precio_max:
            raise ValueError("precio_min no puede superar precio_max")
        texto = parametros.get("q", "").strip()
        if len(texto) > 300:
            raise ValueError("El texto debe tener entre 1 y 300 caracteres")
        return cls(
            operacion, tipo, dormitorios, moneda, precio_min, precio_max, texto,
            entero(parametros.get("pagina", "1"), "pagina", 1, 2147483647),
            entero(parametros.get("por_pagina", "20"), "por_pagina", 1, 100),
        )

    def aplicar(self, queryset):
        queryset = queryset.filter(**{f"en_{self.operacion}": True})
        if self.tipo:
            queryset = queryset.filter(tipo__iexact=self.tipo)
        if self.dormitorios is not None:
            queryset = queryset.filter(dormitorios=self.dormitorios)
        if self.moneda:
            queryset = queryset.filter(**{f"moneda_{self.operacion}": self.moneda})
        for limite, valor in (("gte", self.precio_min), ("lte", self.precio_max)):
            if valor is not None:
                queryset = queryset.filter(**{f"precio_{self.operacion}__{limite}": valor})
        return queryset


def consultar_propiedades(parametros, *, buscar):
    filtros = Filtros.leer(parametros)
    queryset = aplicar_filtros_geograficos(filtros.aplicar(Propiedad.objects.all()), parametros)
    scores = {}
    if filtros.texto:
        # Paginar después de filtrar: los primeros hits pueden no cumplir los filtros SQL.
        coincidencias = buscar(filtros.texto)
        ids = list(dict.fromkeys(pk for pk, _ in coincidencias))
        permitidos = set()
        for inicio in range(0, len(ids), 500):
            permitidos.update(queryset.filter(pk__in=ids[inicio:inicio + 500]).values_list("pk", flat=True))
        ordenados = [pk for pk in ids if pk in permitidos]
        pagina = Paginator(ordenados, filtros.por_pagina).page(filtros.pagina)
        objetos = queryset.in_bulk(pagina.object_list)
        pagina.object_list = [objetos[pk] for pk in pagina.object_list if pk in objetos]
        scores = {pk: score for pk, score in coincidencias if pk in objetos}
    else:
        pagina = Paginator(queryset.order_by("-actualizada_en", "-pk"), filtros.por_pagina).page(filtros.pagina)
    advertencias = []
    if parametros.get("incluir_aproximadas") == "1" and any(c in parametros for c in ("radio_m", "oeste")):
        advertencias.append(AVISO_PRECISION)
    return filtros, pagina, scores, advertencias
