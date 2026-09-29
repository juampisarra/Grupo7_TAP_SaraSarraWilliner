from django.shortcuts import render
from .models import Propiedad

def lista_propiedades(request):
   operacion = request.GET.get("operacion", "alquiler")


   propiedades = Propiedad.objects.all()

   if (operacion == "venta"):
        propiedades= propiedades.filter(en_venta = True)
   else:
        operacion = "alquiler"
        propiedades= propiedades.filter(en_alquiler = True)

   propiedades = propiedades.order_by("-actualizada_en")

   contexto = {
      "propiedades": propiedades,
      "operacion": operacion
   }

   return render(
      request,
      "propiedades/lista.html",
      contexto,
   )
