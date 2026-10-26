from datetime import timedelta
import json
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.paginator import EmptyPage
from django.db import NotSupportedError
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods, require_safe, require_POST
from django.views.decorators.cache import never_cache
from django.utils.crypto import salted_hmac

from .busqueda.cliente import BusquedaNoDisponible
from .busqueda.texto import buscar_ids
from .consultas import CAMPOS_CONSULTA, consultar_propiedades
from .coordenadas import informacion_ubicacion
from .models import Comentario, Propiedad
from .comparacion import ErrorComparacion, ids_desde_query, preparar_comparacion
from .comparacion_ia import analizar_comparacion
from .llm.cliente import LLMNoDisponible, configurado as ia_configurada


def cookie_visitante(request, response):
    if not request.get_signed_cookie("comparador_visitante", default="", salt="comparacion", max_age=86400):
        response.set_signed_cookie("comparador_visitante", uuid.uuid4().hex, salt="comparacion",
                                   max_age=86400, httponly=True, secure=not settings.DEBUG, samesite="Lax")
    return response


def error_comparacion(error):
    response = JsonResponse({"error": str(error), "codigo": error.codigo,
                             "ids": getattr(error, "ids", [])}, status=error.status)
    if error.status == 429:
        response["Retry-After"] = "60"
    return response


@never_cache
@require_safe
def api_comparacion(request):
    try:
        datos = preparar_comparacion(ids_desde_query(request.GET), request.GET.get("operacion"))
    except ErrorComparacion as error:
        return error_comparacion(error)
    datos["ia_disponible"] = ia_configurada()
    return cookie_visitante(request, JsonResponse(datos, json_dumps_params={"ensure_ascii": False}))


@never_cache
@require_POST
def api_analisis_comparacion(request):
    try:
        if request.content_type != "application/json" or len(request.body) > 4096:
            raise ErrorComparacion("Enviá un objeto JSON de hasta 4096 bytes.")
        try:
            entrada = json.loads(request.body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, RecursionError):
            raise ErrorComparacion("El JSON enviado no es válido.") from None
        if not isinstance(entrada, dict) or set(entrada) != {"ids", "operacion", "firma"}:
            raise ErrorComparacion("Enviá únicamente ids, operacion y firma de la tabla.")
        datos = preparar_comparacion(entrada["ids"], entrada["operacion"])
        if entrada["firma"] != datos["firma"]:
            raise ErrorComparacion("Los datos cambiaron. Actualizá la tabla antes de generar el análisis.",
                                   status=409, codigo="datos_cambiaron")
        visitante = request.get_signed_cookie("comparador_visitante", default="", salt="comparacion", max_age=86400)
        # Sin cookie válida se limita por la conexión; no confiar en X-Forwarded-For.
        visitante = salted_hmac("comparacion-visitante", visitante or request.META.get("REMOTE_ADDR", "")).hexdigest()
        resultado = analizar_comparacion(datos, visitante)
        # La ingesta puede cambiar los datos mientras Gemini responde.
        actuales = preparar_comparacion(entrada["ids"], entrada["operacion"])
        if actuales["firma"] != datos["firma"]:
            raise ErrorComparacion("Los datos cambiaron durante el análisis. Actualizá la tabla.",
                                   status=409, codigo="datos_cambiaron")
        return JsonResponse({**resultado, "firma": datos["firma"]}, json_dumps_params={"ensure_ascii": False})
    except (ErrorComparacion, LLMNoDisponible) as error:
        return error_comparacion(error)


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


def serializar_comentario(comentario):
    return {
        "id": comentario.id,
        "propiedad_id": comentario.propiedad_id,
        "autor": comentario.autor or "Anónimo",
        "texto": comentario.texto,
        "creado_en": comentario.creado_en.isoformat(),
    }


def extraer_datos_comentario(request):
    tipo_contenido = (request.content_type or "").lower()
    if tipo_contenido.startswith("application/json"):
        if len(request.body) > 8192:
            raise ValueError("El cuerpo de la solicitud es demasiado grande.")
        try:
            datos = json.loads(request.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("El formato JSON enviado no es válido.") from error
        if not isinstance(datos, dict):
            raise ValueError("Se esperaba un objeto JSON con los datos del comentario.")
        return datos.get("autor", ""), datos.get("texto")
    if "autor" in request.POST and len(request.POST.getlist("autor")) > 1:
        raise ValueError("El parámetro autor no puede repetirse.")
    if "texto" in request.POST and len(request.POST.getlist("texto")) > 1:
        raise ValueError("El parámetro texto no puede repetirse.")
    return request.POST.get("autor", ""), request.POST.get("texto")


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


@require_http_methods(["GET", "HEAD", "POST"])
def api_comentarios_propiedad(request, propiedad_id):
    if not Propiedad.objects.filter(pk=propiedad_id).exists():
        return JsonResponse({"error": "La propiedad solicitada no existe."}, status=404)

    if request.method in ("GET", "HEAD"):
        activos = Comentario.objects.filter(propiedad_id=propiedad_id, activo=True)
        total = activos.count()
        comentarios = [serializar_comentario(c) for c in activos.order_by("-creado_en", "-id")[:50]]
        return JsonResponse({
            "propiedad_id": propiedad_id,
            "total": total,
            "comentarios": comentarios,
        }, json_dumps_params={"ensure_ascii": False})

    try:
        autor, texto = extraer_datos_comentario(request)
    except ValueError as error:
        return JsonResponse({"error": str(error)}, status=400)

    if autor is None:
        autor = ""
    comentario = Comentario(propiedad_id=propiedad_id, autor=autor, texto=texto)
    try:
        comentario.clean()
    except ValidationError as error:
        mensajes = []
        for lista in error.message_dict.values():
            mensajes.extend(lista)
        return JsonResponse({"error": mensajes[0] if mensajes else "Datos de comentario inválidos."}, status=400)

    ventana_reciente = timezone.now() - timedelta(seconds=60)
    duplicado = Comentario.objects.filter(
        propiedad_id=propiedad_id,
        autor=comentario.autor,
        texto=comentario.texto,
        activo=True,
        creado_en__gte=ventana_reciente,
    ).exists()
    if duplicado:
        return JsonResponse(
            {"error": "Este comentario ya fue publicado recientemente. Esperá un momento antes de volver a enviarlo."},
            status=429,
        )

    comentario.save()
    return JsonResponse(
        {"comentario": serializar_comentario(comentario)},
        status=201,
        json_dumps_params={"ensure_ascii": False},
    )


@require_safe
@ensure_csrf_cookie
def mapa_propiedades(request):
    # Disponibilidad por operación en todo el catálogo, sin depender de los resultados.
    tipos = list(Propiedad.objects.filter(Q(en_venta=True) | Q(en_alquiler=True)).exclude(
        tipo="").order_by("tipo").values("tipo").annotate(
            alquiler=Count("id", filter=Q(en_alquiler=True)),
            venta=Count("id", filter=Q(en_venta=True)),
        ))
    response = render(request, "propiedades/mapa.html", {
        "tipos_propiedad": tipos,
        "hay_tipos_alquiler": any(tipo["alquiler"] for tipo in tipos),
        "map_config": {"maptilerApiKey": settings.MAPTILER_API_KEY},
    })
    return cookie_visitante(request, response)
