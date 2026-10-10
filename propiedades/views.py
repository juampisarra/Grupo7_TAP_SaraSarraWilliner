from django.shortcuts import render
from django.http import JsonResponse
from django.db import NotSupportedError
from .models import Propiedad
from .geografia import aplicar_filtros_geograficos
from .busqueda.cliente import BusquedaNoDisponible
from .busqueda.texto import buscar_ids, combinar_resultados

def lista_propiedades(request):
   operacion = request.GET.get("operacion", "alquiler")


   propiedades = Propiedad.objects.all()

   if (operacion == "venta"):
        propiedades= propiedades.filter(en_venta = True)
   else:
        operacion = "alquiler"
        propiedades= propiedades.filter(en_alquiler = True)

   try:
        propiedades = aplicar_filtros_geograficos(propiedades, request.GET)
   except ValueError as error:
        return JsonResponse({"error": str(error)}, status=400)
   except NotSupportedError as error:
        return JsonResponse({"error": str(error)}, status=503)

   propiedades = propiedades.order_by("-actualizada_en")
   texto = request.GET.get("q", "").strip()
   if texto:
        try:
            propiedades = combinar_resultados(propiedades, buscar_ids(texto))
        except ValueError as error:
            return JsonResponse({"error": str(error)}, status=400)
        except BusquedaNoDisponible as error:
            return JsonResponse({"error": str(error)}, status=503)

   contexto = {
      "propiedades": propiedades,
      "operacion": operacion,
      "texto_busqueda": texto,
      "filtros_geograficos": {
          campo: request.GET[campo]
          for campo in ("latitud", "longitud", "radio_m", "oeste", "sur", "este", "norte", "incluir_aproximadas")
          if campo in request.GET
      },
      "filtra_centros_aproximados": request.GET.get("incluir_aproximadas") == "1"
          and any(c in request.GET for c in ("radio_m", "oeste")),
   }

   return render(
      request,
      "propiedades/lista.html",
      contexto,
   )
