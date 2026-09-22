from django.contrib import admin

from .models import Propiedad
# Register your models here.

@admin.register(Propiedad)
class PropiedadAdmin(admin.ModelAdmin):
    list_display = (
           "fuente",
    "identificador_fuente",
    "direccion",
    "tipo",
    "en_venta",
    "precio_venta",
    "moneda_venta",
    "en_alquiler",
    "precio_alquiler",
    "moneda_alquiler",
    "url_original",
    "actualizada_en",
    )
    search_fields = (
        "direccion",
        "identificador_fuente",
    )
    list_filter =(
       "fuente",
    "tipo",
    "en_venta",
    "en_alquiler",
    "moneda_venta",
    "moneda_alquiler",
    )