"""Caché y cuotas compartidas. Nunca se mantiene un bloqueo durante HTTP."""

from datetime import timedelta
import uuid

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .comparacion import datos_para_llm, firma_datos
from .llm.cliente import configurado, generar_analisis, LLMNoDisponible
from .llm.prompts import VERSION_PROMPT
from .models import ComparacionGenerada, UsoComparacion


def consumir_cuota(visitante, ahora):
    minuto = int(ahora.timestamp()) // 60
    dia = ahora.date().isoformat()
    ventanas = [
        (f"visitante:{visitante}:{minuto}", settings.COMPARACION_LIMITE_VISITANTE, ahora + timedelta(minutes=2)),
        (f"global:minuto:{minuto}", settings.COMPARACION_LIMITE_MINUTO, ahora + timedelta(minutes=2)),
        (f"global:dia:{dia}", settings.COMPARACION_LIMITE_DIA, ahora + timedelta(days=2)),
    ]
    with transaction.atomic():
        for clave, limite, vence in ventanas:
            contador, _ = UsoComparacion.objects.get_or_create(clave=clave, defaults={"vence_en": vence})
            # UPDATE condicional atómico, también sin select_for_update en SQLite.
            if not UsoComparacion.objects.filter(pk=contador.pk, solicitudes__lt=limite).update(
                    solicitudes=F("solicitudes") + 1):
                raise LLMNoDisponible("Se alcanzó el límite de análisis. Esperá antes de reintentar.",
                                      status=429, codigo="limite_analisis")


def analizar_comparacion(datos, visitante):
    if not configurado():
        raise LLMNoDisponible("El análisis con IA todavía no está configurado. Podés usar la tabla comparativa.")
    ahora = timezone.now()
    entrada = datos_para_llm(datos)
    clave = firma_datos([VERSION_PROMPT, settings.GEMINI_MODEL, entrada])
    reserva = uuid.uuid4()
    # Limpieza de registros vencidos, sin tareas externas o crecimiento indefinido.
    UsoComparacion.objects.filter(vence_en__lt=ahora).delete()
    ComparacionGenerada.objects.filter(vence_en__lt=ahora - timedelta(days=1)).delete()
    cache, creada = ComparacionGenerada.objects.get_or_create(clave=clave, defaults={
        "modelo": settings.GEMINI_MODEL, "reserva": reserva,
        "vence_en": ahora + timedelta(seconds=60),
    })
    if not creada:
        if cache.vence_en > ahora:
            if cache.resultado:
                return {"analisis": cache.resultado, "reutilizado": True,
                        "generado_en": cache.creada_en.isoformat(), "modelo": cache.modelo}
            raise LLMNoDisponible("Este análisis ya se está generando. Esperá unos segundos y reintentá.",
                                  status=409, codigo="analisis_en_curso")
        reservada = ComparacionGenerada.objects.filter(pk=cache.pk, vence_en__lte=ahora).update(
            reserva=reserva, resultado={}, creada_en=ahora, vence_en=ahora + timedelta(seconds=60))
        if not reservada:
            raise LLMNoDisponible("Este análisis ya se está generando. Reintentá en unos segundos.",
                                  status=409, codigo="analisis_en_curso")
    try:
        consumir_cuota(visitante, ahora)
        resultado = generar_analisis(entrada)
        ComparacionGenerada.objects.filter(clave=clave, reserva=reserva).update(
            resultado=resultado, vence_en=timezone.now() + timedelta(hours=24))
    except Exception:
        ComparacionGenerada.objects.filter(clave=clave, reserva=reserva).delete()
        raise
    return {"analisis": resultado, "reutilizado": False,
            "generado_en": ahora.isoformat(), "modelo": settings.GEMINI_MODEL}
