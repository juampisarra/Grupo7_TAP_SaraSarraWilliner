from django.contrib import admin

from .models import Comentario, Propiedad


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


@admin.register(Comentario)
class ComentarioAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "propiedad",
        "autor",
        "resumen_texto",
        "activo",
        "creado_en",
    )
    list_filter = (
        "activo",
        "creado_en",
        "propiedad__fuente",
    )
    search_fields = (
        "autor",
        "texto",
        "propiedad__direccion",
        "propiedad__identificador_fuente",
    )
    list_editable = ("activo",)

    @admin.display(description="Comentario")
    def resumen_texto(self, obj):
        texto = (obj.texto or "").strip()
        return texto[:60] + ("…" if len(texto) > 60 else "")
