from django.db import models

# Tiene datos de cada propiedad
class Propiedad(models.Model):
        fuente = models.CharField(max_length=100)
        #es el prop-id del sitio original
        identificador_fuente = models.CharField(max_length=200)
        direccion = models .CharField(max_length=255, blank= True)
        tipo = models.CharField(max_length=50, blank= True)
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