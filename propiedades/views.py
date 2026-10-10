from django.shortcuts import render
from django.http import JsonResponse
from django.db import NotSupportedError
from .models import Propiedad
from .geografia import aplicar_filtros_geograficos

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

   contexto = {
      "propiedades": propiedades,
      "operacion": operacion,
      "filtra_centros_aproximados": request.GET.get("incluir_aproximadas") == "1"
          and any(c in request.GET for c in ("radio_m", "oeste")),
   }

   return render(
      request,
      "propiedades/lista.html",
      contexto,
   )
