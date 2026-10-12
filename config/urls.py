from django.contrib import admin
from django.urls import include, path
from .views import health
from propiedades.views import api_propiedades



urlpatterns = [
    path("health/", health, name="health"),
    path("admin/", admin.site.urls),
    path("propiedades/", include("propiedades.urls")),
    path("api/propiedades/", api_propiedades, name="api_propiedades"),
]

