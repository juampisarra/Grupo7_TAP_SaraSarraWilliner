from django.contrib import admin
from django.urls import include, path
from .views import health
from propiedades.views import api_comentarios_propiedad, api_propiedades, api_comparacion, api_analisis_comparacion



urlpatterns = [
    path("health/", health, name="health"),
    path("admin/", admin.site.urls),
    path("propiedades/", include("propiedades.urls")),
    path("api/propiedades/", api_propiedades, name="api_propiedades"),
    path("api/propiedades/comparacion/", api_comparacion, name="api_comparacion"),
    path("api/propiedades/comparacion/analisis/", api_analisis_comparacion, name="api_analisis_comparacion"),
    path("api/propiedades/<int:propiedad_id>/comentarios/", api_comentarios_propiedad, name="api_comentarios_propiedad"),
]
