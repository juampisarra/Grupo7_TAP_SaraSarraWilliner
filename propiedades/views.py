from django.core.paginator import EmptyPage
from django.db import NotSupportedError
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_safe

from .busqueda.cliente import BusquedaNoDisponible
from .busqueda.texto import buscar_ids
from .consultas import CAMPOS_CONSULTA, consultar_propiedades
from .coordenadas import informacion_ubicacion
from .models import Propiedad


def enlace_pagina(request, numero):
    parametros = request.GET.copy()
    parametros["pagina"] = numero
    return f"{request.path}?{parametros.urlencode()}"


def serializar_propiedad(propiedad, score):
    campos = (
        "id", "fuente", "identificador_fuente", "url_original", "tipo", "titulo",
        "descripcion", "caracteristicas", "direccion", "ciudad", "provincia", "zona",
        "ciudad_origen", "provincia_origen", "dormitorios", "dormitorios_verificados",
        "ambientes", "banos", "latitud", "longitud", "ubicacion_aproximada", "radio_ubicacion_m",
    )
    datos = {campo: getattr(propiedad, campo) for campo in campos}
    datos["actualizada_en"] = propiedad.actualizada_en.isoformat()
    datos["relevancia"] = score
    datos["fotos"] = propiedad.fotos
    datos["foto_portada"] = propiedad.foto_portada
    datos["ubicacion_info"] = informacion_ubicacion(propiedad)
    for operacion in ("venta", "alquiler"):
        precio = getattr(propiedad, f"precio_{operacion}")
        datos[operacion] = {
            "disponible": getattr(propiedad, f"en_{operacion}"),
            "precio": format(precio, ".2f") if precio is not None else None,
            "moneda": getattr(propiedad, f"moneda_{operacion}") or None,
        }
    return datos


def responder_consulta(request, *, json):
    try:
        filtros, pagina, scores, advertencias = consultar_propiedades(request.GET, buscar=buscar_ids)
    except ValueError as error:
        return JsonResponse({"error": str(error)}, status=400)
    except EmptyPage:
        return JsonResponse({"error": "La página solicitada no existe"}, status=404)
    except (NotSupportedError, BusquedaNoDisponible) as error:
        return JsonResponse({"error": str(error)}, status=503)
    siguiente = enlace_pagina(request, pagina.next_page_number()) if pagina.has_next() else None
    anterior = enlace_pagina(request, pagina.previous_page_number()) if pagina.has_previous() else None
    if json:
        return JsonResponse({
            "total": pagina.paginator.count,
            "pagina": pagina.number,
            "por_pagina": pagina.paginator.per_page,
            "total_paginas": pagina.paginator.num_pages,
            "siguiente": siguiente,
            "anterior": anterior,
            "operacion": filtros.operacion,
            "orden": "relevancia" if filtros.texto else "actualizacion",
            "advertencias": advertencias,
            "resultados": [serializar_propiedad(p, scores.get(p.pk)) for p in pagina],
        }, json_dumps_params={"ensure_ascii": False})
    return render(request, "propiedades/lista.html", {
        "propiedades": pagina.object_list,
        "pagina": pagina,
        "total": pagina.paginator.count,
        "siguiente": siguiente,
        "anterior": anterior,
        "operacion": filtros.operacion,
        "texto_busqueda": filtros.texto,
        "filtros_conservados": {
            c: request.GET[c] for c in CAMPOS_CONSULTA
            if c not in ("operacion", "q", "pagina") and c in request.GET
        },
        "filtra_centros_aproximados": bool(advertencias),
    })


@require_safe
def lista_propiedades(request):
    return responder_consulta(request, json=False)


@require_safe
def api_propiedades(request):
    return responder_consulta(request, json=True)


@require_safe
def mapa_propiedades(request):
    # Catálogo completo, independiente de la página de resultados del mapa.
    tipos = Propiedad.objects.filter(Q(en_venta=True) | Q(en_alquiler=True)).exclude(
        tipo="").order_by("tipo").values_list("tipo", flat=True).distinct()
    return render(request, "propiedades/mapa.html", {"tipos_propiedad": tipos})
