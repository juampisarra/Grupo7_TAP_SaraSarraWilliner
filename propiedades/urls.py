from django.urls import path

from . import views


app_name = "propiedades"

urlpatterns = [
    path("", views.lista_propiedades, name="lista"),
]