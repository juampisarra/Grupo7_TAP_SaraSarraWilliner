from django.db import models

# Tiene datos de cada propiedad
class Propiedad(models.Model):
        fuente = models.CharField(max_length=100)
        #es el prop-id del sitio original
        identificador_fuente = models.CharField(max_length=200)
        direccion = models .CharField(max_length=255, blank= True)
        tipo = models.CharField(max_length=50, blank= True)
        titulo = models.CharField(max_length=500, blank=True)
        descripcion = models.TextField(blank=True)
        caracteristicas = models.TextField(blank=True)
        ciudad = models.CharField(max_length=150, blank=True)
        provincia = models.CharField(max_length=150, blank=True)
        ciudad_origen = models.CharField(max_length=30, blank=True)
        provincia_origen = models.CharField(max_length=30, blank=True)
        # Texto de ubicación de la fuente; puede ser barrio o localidad.
        zona = models.CharField(max_length=255, blank=True)
        ambientes = models.PositiveSmallIntegerField(null=True, blank=True)
        banos = models.PositiveSmallIntegerField(null=True, blank=True)
        dormitorios = models.PositiveSmallIntegerField(
                null = True,
                blank= True,
        )
        dormitorios_verificados=  models.BooleanField(default= False)
        #acepta nul xq puede ser desconocido
     
        precio_venta = models.DecimalField(
                max_digits=15,
                decimal_places=2,
                null=True,
                blank=True,
                    )
        moneda_venta=models.CharField(max_length=10, blank=True)
        
        precio_alquiler = models.DecimalField(
                max_digits=15,
                decimal_places=2,
                null=True,
                blank=True,
                    )
        moneda_alquiler = models.CharField(max_length=10, blank = True)
     
        url_original = models.URLField(max_length=1000)
        en_venta = models.BooleanField(default=False)
        en_alquiler = models.BooleanField(default=False)
        actualizada_en = models.DateTimeField(auto_now = True)
        
        latitud = models.FloatField(null=True, blank=True)
        longitud = models.FloatField(null=True, blank=True)
        # En PostgreSQL, 0011 genera la columna espacial `ubicacion` a partir
        # de estos dos campos. No se escribe desde el ORM; ver geografia.py.
        # None: precisión desconocida; True: la fuente publica un área aproximada.
        ubicacion_aproximada = models.BooleanField(null=True, blank=True)
        radio_ubicacion_m = models.FloatField(null=True, blank=True)

        #No se puede repetir fuente | identificador_fuente
        #Se puede Brega | 123, Avantix | 123
        #No se puede Brega | 123 , Brega | 123
        class Meta:
                constraints = [
                        models.UniqueConstraint(
                                fields=["fuente", "identificador_fuente"],
                                name="propiedad_unicar_por_fuente"
                        )
                ]

        def __str__(self):
                return f"{self.fuente}: {self.direccion or self.identificador_fuente}"


class ConsultaLocalidad(models.Model):
    """Caché persistente de Nominatim; no modifica la ubicación de la propiedad."""

    latitud = models.FloatField()
    longitud = models.FloatField()
    ciudad = models.CharField(max_length=150, blank=True)
    provincia = models.CharField(max_length=150, blank=True)
    estado = models.CharField(max_length=20)
    consultada_en = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=["latitud", "longitud"], name="consulta_localidad_por_coordenadas",
        )]
